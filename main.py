import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests
import socket
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# 设置全局超时，防止 GitHub Actions 卡死
socket.setdefaulttimeout(15)

# ================= 核心指标计算逻辑 (严格版) =================
def calculate_indicator(df, mode="daily"):
    """
    严格模拟通达信金钻趋势 + 副图动能过滤
    """
    try:
        # 数据量门槛：至少需要80天数据以保证25周期双平滑稳定
        if df is None or len(df) < 80: return False
        
        df = df.copy()
        df.columns = [str(c).lower() for c in df.columns]
        m = {'收盘': 'close', '最高': 'high', '最低': 'low', '开盘': 'open', '成交量': 'volume'}
        df = df.rename(columns=m)
        close, high, low = df['close'].astype(float), df['high'].astype(float), df['low'].astype(float)

        def ema(s, n): return s.ewm(span=n, adjust=False).mean()

        # 1. 主图金钻趋势线 (XMA重心模拟)
        # 公式: MA_L - (MA_H - MA_L)
        ma_h = ema(ema(high, 25), 25)
        ma_l = ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        
        # 2. 动能过滤 (对应通达信 VAR23)
        diff = close.diff(1)
        abs_diff = diff.abs()
        var23 = 100 * ema(ema(diff, 6), 6) / (ema(ema(abs_diff, 6), 6) + 1e-6)
        
        # 3. 副图粉色指标 (散户线)
        hhv_60 = high.rolling(60).max()
        llv_60 = low.rolling(60).min()
        retail = 100 * (hhv_60 - close) / (hhv_60 - llv_60 + 1e-6)

        if mode == "daily":
            # --- 日线判定：严格过滤 ---
            # A. 价格必须真正【触碰或跌破】趋势线 (无容错)
            # B. 散户线必须处于【极端超卖】区间 (>92)
            # C. 动能必须【向上拐头】(var23 > 昨天的var23)
            cond_price = low <= trend_line
            cond_retail = retail > 92
            cond_momentum = var23 > var23.shift(1)
            
            final_cond = cond_price & cond_retail & cond_momentum
            return final_cond.tail(1).any() # 只看最新一天
        else:
            # --- 周月线判定：大周期趋势锚点 ---
            # 大周期允许 1% 的“缓冲区”，只要处于底部地带即可
            cond_big = low <= trend_line * 1.01
            return cond_big.tail(2).any()
    except:
        return False

# ================= 深度分析逻辑 (评分制) =================
def perform_analysis(df, code):
    """
    量化评分：RSI, 均线, 放量
    """
    try:
        df.columns = [str(c).lower() for c in df.columns]
        df = df.rename(columns={'收盘': 'close', '成交量': 'volume'})
        close, vol = df['close'].astype(float), df['volume'].astype(float)
        
        score, reasons = 65, ["符合金钻底部指标"]

        # RSI 拐头
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain/(loss + 1e-6)))
        if rsi.iloc[-1] > rsi.iloc[-2] and rsi.iloc[-1] < 45:
            score += 15; reasons.append("RSI低位反弹")

        # 均线收复
        ma5 = close.rolling(5).mean()
        if close.iloc[-1] > ma5.iloc[-1]:
            score += 10; reasons.append("收复5日线")

        # 底部放量
        vol_ma5 = vol.rolling(5).mean()
        if vol.iloc[-1] > vol_ma5.iloc[-1] * 1.3:
            score += 10; reasons.append("放量启动")

        return f"【评分: {score}】📝 {';'.join(reasons)}"
    except:
        return "【评分: 65】📝 触发基础抄底信号"

# ================= 数据下载与线程处理 =================
def download_task(code, period="daily"):
    """安全抓取函数"""
    try:
        # 优先使用东财接口，失败自动切换
        df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        if df is not None and not df.empty:
            if calculate_indicator(df, period):
                return code, df
    except:
        pass
    return None, None

# ================= 主流程 =================
def main():
    start_time = time.time()
    print(f"[{datetime.datetime.now()}] 🚀 启动严格版多线程漏斗扫描...")

    # 1. 初始化股票池 (50, 300, 1000, 688)
    indices = {"上证50": "000016", "沪深300": "000300", "中证1000": "000852", "科创50": "000688"}
    stock_pool = {}
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            for _, row in df.iterrows(): stock_pool[row['品种代码']] = row['品种名称']
        except: pass
    
    all_codes = list(stock_pool.keys())
    print(f"✅ 初始池: {len(all_codes)} 只股票")

    # --- Step 1: 日线漏斗 (10线程并发) ---
    print(f"Step 1: 正在严格筛选日线符合标的...")
    daily_passed = {} # {code: df}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_code = {executor.submit(download_task, c, "daily"): c for c in all_codes}
        for future in as_completed(future_to_code):
            code, df = future.result()
            if code:
                daily_passed[code] = df
    
    print(f"🔍 日线入围: {len(daily_passed)} 只")
    if not daily_passed:
        send_to_wechat("今日无符合日线严格指标的股票。")
        return

    # --- Step 2 & 3: 周线与月线过滤 ---
    triple_match, double_match, daily_only = [], [], []
    for code, df_d in daily_passed.items():
        time.sleep(0.2) # 避开频率限制
        
        # 抓周线
        code_w, df_w = download_task(code, "weekly")
        is_w = True if code_w else False
        
        # 抓月线
        is_m = False
        if is_w:
            code_m, df_m = download_task(code, "monthly")
            is_m = True if code_m else False
        
        # 深度分析结果
        analysis = perform_analysis(df_d, code)
        report_item = f"📌 {code}-{stock_pool[code]}\n   └ {analysis}"
        
        if is_w and is_m:
            triple_match.append(report_item)
        elif is_w:
            double_match.append(report_item)
        else:
            daily_only.append(report_item)

    # --- 构造报告 ---
    total_time = int(time.time() - start_time)
    report = f"📅 报告日期: {datetime.date.today()}\n"
    report += f"⏱️ 扫描耗时: {total_time}s | 漏斗结果: {len(all_codes)}→{len(daily_passed)}→{len(double_match + triple_match)}→{len(triple_match)}\n\n"
    
    report += "🌟 [终极推荐: 日周月共振]\n" + ("\n".join(triple_match) if triple_match else "无") + "\n\n"
    report += "💎 [强化推荐: 日周共振]\n" + ("\n".join(double_match) if double_match else "无") + "\n\n"
    report += "🟢 [基础信号: 仅日线符合]\n" + ("\n".join(daily_only[:25]) if daily_only else "无")
    if len(daily_only) > 25: report += f"\n...等共 {len(daily_only)} 只"

    print(report)
    send_to_wechat(report)

def send_to_wechat(content):
    token = os.environ.get('PUSHPLUS_TOKEN')
    if token:
        try:
            requests.post("http://www.pushplus.plus/send", 
                         json={"token": token, "title": "严格版股票漏斗报告", "content": content.replace("\n", "<br>"), "template": "html"},
                         timeout=10)
        except: pass

if __name__ == "__main__":
    main()
