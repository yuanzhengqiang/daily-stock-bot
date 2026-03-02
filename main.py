import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests
import socket

# 强制设置全局超时，防止 GitHub Actions 卡死
socket.setdefaulttimeout(20)

def calculate_logic(df, mode="daily"):
    """
    严格匹配通达信公式的 Python 实现
    """
    try:
        if df is None or len(df) < 60: return False
        df.columns = [str(c).lower() for c in df.columns]
        m = {'收盘': 'close', '最高': 'high', '最低': 'low'}
        df = df.rename(columns=m)
        close, high, low = df['close'].astype(float), df['high'].astype(float), df['low'].astype(float)

        def ema(s, n): return s.ewm(span=n, adjust=False).mean()

        # 模拟通达信 XMA(XMA(L, 25), 25)
        ma_h = ema(ema(high, 25), 25)
        ma_l = ema(ema(low, 25), 25)
        
        # 金钻趋势线公式: ma_l - (ma_h - ma_l)
        trend_line = ma_l - (ma_h - ma_l)
        
        # 副图粉色指标 (能量超跌)
        hhv_60 = high.rolling(60).max()
        llv_60 = low.rolling(60).min()
        retail = 100 * (hhv_60 - close) / (hhv_60 - llv_60)

        if mode == "daily":
            # 日线必须精准：低点触碰趋势线 且 散户线处于高位(超卖)
            cond = (low <= trend_line * 1.005) & (retail > 85)
            return cond.tail(2).any() # 最近2日触发
        else:
            # 周线和月线作为趋势过滤：只要价格处于低位趋势带即可
            cond = low <= trend_line * 1.02 
            return cond.tail(3).any() # 最近3个周期内触发过
    except:
        return False

def safe_fetch(code, period):
    """带重试的历史数据抓取"""
    for _ in range(2):
        try:
            return ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        except:
            time.sleep(1)
    return None

def main():
    start_time = time.time()
    print(f"[{datetime.datetime.now()}] 🚀 开始漏斗式筛选任务...")

    # 1. 获取所有指数成分股并去重
    indices = {"上证50": "000016", "沪深300": "000300", "中证1000": "000852", "科创50": "000688"}
    stock_pool = {}
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            for _, row in df.iterrows(): stock_pool[row['品种代码']] = row['品种名称']
        except: pass
    
    all_codes = list(stock_pool.keys())
    print(f"✅ 初始池: {len(all_codes)} 只股票")

    # --- 第一层：全量扫描日线 ---
    print("Step 1: 正在扫描全量日线...")
    daily_passed = []
    for i, code in enumerate(all_codes):
        if (i+1) % 200 == 0: print(f"进度: {i+1}/{len(all_codes)}...")
        df = safe_fetch(code, "daily")
        if calculate_logic(df, "daily"):
            daily_passed.append(code)
    
    print(f"🔍 日线符合: {len(daily_passed)} 只")
    if not daily_passed:
        send_report("今日无符合日线指标的股票。", 0, 0, 0)
        return

    # --- 第二层：过滤周线 (仅对日线符合的股票) ---
    print("Step 2: 正在对符合日线的股票扫描周线...")
    weekly_passed = []
    for code in daily_passed:
        df = safe_fetch(code, "weekly")
        if calculate_logic(df, "weekly"):
            weekly_passed.append(code)
    
    print(f"🔍 日周共振: {len(weekly_passed)} 只")

    # --- 第三层：过滤月线 (仅对日周符合的股票) ---
    print("Step 3: 正在对符合日周的股票扫描月线...")
    monthly_passed = []
    for code in weekly_passed:
        df = safe_fetch(code, "monthly")
        if calculate_logic(df, "monthly"):
            monthly_passed.append(code)
    
    print(f"🔍 日周月共振: {len(monthly_passed)} 只")

    # --- 构造报告 ---
    total_time = int(time.time() - start_time)
    
    res_3 = [f"📌 {c}-{stock_pool[c]}" for c in monthly_passed]
    # 计算“仅日周”符合的：在 weekly 列表里但不在 monthly 里的
    res_2 = [f"📌 {c}-{stock_pool[c]}" for c in weekly_passed if c not in monthly_passed]
    # 计算“仅日线”符合的：在 daily 列表里但不在 weekly 里的
    res_1 = [f"📌 {c}-{stock_pool[c]}" for c in daily_passed if c not in weekly_passed]

    report = f"📅 日期: {datetime.date.today()}\n"
    report += f"⏱️ 耗时: {total_time}s | 漏斗结果: {len(daily_passed)}→{len(weekly_passed)}→{len(monthly_passed)}\n\n"
    
    report += "🌟 [终极推荐: 日周月共振]\n" + ("\n".join(res_3) if res_3 else "无") + "\n\n"
    report += "💎 [强化推荐: 日周共振]\n" + ("\n".join(res_2) if res_2 else "无") + "\n\n"
    report += "🟢 [基础信号: 仅日线符合]\n" + ("\n".join(res_1[:30]) if res_1 else "无")
    if len(res_1) > 30: report += f"\n...等共 {len(res_1)} 只"

    print(report)
    send_report(report)

def send_report(content, d=0, w=0, m=0):
    token = os.environ.get('PUSHPLUS_TOKEN')
    if token:
        try:
            requests.post("http://www.pushplus.plus/send", 
                         json={"token": token, "title": "股票漏斗扫描报告", "content": content.replace("\n", "<br>"), "template": "html"},
                         timeout=10)
        except: pass

if __name__ == "__main__":
    main()
