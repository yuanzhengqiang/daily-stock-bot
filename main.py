import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制全局超时，防止 GitHub Actions 挂起
socket.setdefaulttimeout(15)

def calculate_indicator(df, mode="daily"):
    """
    对标通达信：主图黄线 + 副图超跌
    """
    try:
        # 确保数据量，月线至少需要60个月
        min_len = 65 if mode == "monthly" else 80
        if df is None or len(df) < min_len: return None
        
        df = df.copy()
        df.columns = [str(c).lower() for c in df.columns]
        m = {'收盘': 'close', '最高': 'high', '最低': 'low'}
        df = df.rename(columns=m)
        
        close = df['close'].astype(float)
        high = df['high'].astype(float)
        low = df['low'].astype(float)

        def ema(s, n): return s.ewm(span=n, adjust=False).mean()

        # 1. 主图：金钻趋势线 (XMA 重心模拟)
        ma_h = ema(ema(high, 25), 25)
        ma_l = ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        
        # 2. 副图：散户线 (用于日线质量过滤)
        hhv_60 = high.rolling(window=min(len(df), 60)).max()
        llv_60 = low.rolling(window=min(len(df), 60)).min()
        retail = 100 * (hhv_60 - close) / (hhv_60 - llv_60 + 1e-6)

        # --- 判定逻辑 ---
        # 主图黄线：最低价触碰或低于趋势线
        # 由于 Python 无法预知未来，我们给大周期增加 1% 的容错缓冲区
        buffer = 1.01 if mode != "daily" else 1.0
        is_yellow = low <= trend_line * buffer
        
        # 副图信号：散户线超卖
        is_sub_signal = retail > 80

        return is_yellow, is_sub_signal
    except:
        return None

def download_task(code, period="daily"):
    """执行抓取与指标计算任务"""
    try:
        df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        if df is not None and not df.empty:
            result = calculate_indicator(df, period)
            if result:
                is_yellow, is_sub = result
                # 返回最后一天的判定结果
                return {
                    "code": code,
                    "yellow": is_yellow.iloc[-1],
                    "sub": is_sub.iloc[-1],
                    "any_yellow_recent": is_yellow.tail(2).any(), # 最近2根K线有黄线也算
                    "df_last": df.iloc[-1]
                }
    except: pass
    return None

def main():
    start_time = time.time()
    print(f"[{datetime.datetime.now()}] 🚀 启动 A+H 多周期精准共振扫描...")

    # 1. 初始化股票池
    indices = {"上证50": "000016", "沪深300": "000300", "中证1000": "000852", "科创50": "000688"}
    stock_pool = {}
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            for _, row in df.iterrows(): stock_pool[row['品种代码']] = row['品种名称']
        except: pass
    
    all_codes = list(stock_pool.keys())
    print(f"✅ 初始池: {len(all_codes)} 只 | 过滤逻辑: 日线(主+副) / 周月(主图黄线)")

    # 2. Step 1: 扫描日线 (全量多线程)
    daily_hits = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(download_task, c, "daily"): c for c in all_codes}
        for future in as_completed(futures):
            res = future.result()
            # 日线要求：必须变黄 且 副图出信号
            if res and res['yellow'] and res['sub']:
                daily_hits[res['code']] = res['df_last']
    
    print(f"🔍 日线高质量买点: {len(daily_hits)} 只")
    
    # 提取最近交易日
    last_date = "未知"
    if daily_hits:
        last_date = list(daily_hits.values())[0]['日期']

    if not daily_hits:
        send_report("今日扫描结束，无符合共振指标的股票。", "今日")
        return

    # 3. Step 2 & 3: 漏斗过滤周线、月线 (只看主图黄线)
    triple, double, daily_only = [], [], []
    for code in daily_hits.keys():
        time.sleep(0.15)
        # 周线判定：只要最近2周出现过主图黄线即可
        res_w = download_task(code, "weekly")
        is_w = res_w['any_yellow_recent'] if res_w else False
        
        tag = f"📌 {code}-{stock_pool[code]}"
        if is_w:
            # 月线判定
            res_m = download_task(code, "monthly")
            is_m = res_m['any_yellow_recent'] if res_m else False
            if is_m:
                triple.append(tag)
            else:
                double.append(tag)
        else:
            daily_only.append(tag)

    # 4. 构造报告
    report = f"📅 报告日期: {datetime.date.today()}\n"
    report += f"📊 数据截止: {last_date}\n"
    report += f"⏱️ 耗时: {int(time.time() - start_time)}s\n\n"
    
    report += "🌟 [日周月·三期大底共振]\n" + ("\n".join(triple) if triple else "今日无") + "\n\n"
    report += "💎 [日周·波段强力共振]\n" + ("\n".join(double) if double else "今日无") + "\n\n"
    report += "🟢 [仅日线·高质量买点]\n" + ("\n".join(daily_only) if daily_only else "无")

    print(report)
    send_report(report, last_date)

def send_report(content, date_info):
    token = os.environ.get('PUSHPLUS_TOKEN')
    if token:
        try:
            requests.post("http://www.pushplus.plus/send", 
                         json={"token": token, "title": f"黄线共振报告({date_info})", "content": content.replace("\n", "<br>"), "template": "html"},
                         timeout=10)
        except: pass

if __name__ == "__main__":
    main()
