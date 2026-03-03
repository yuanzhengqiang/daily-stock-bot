import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制设置超时，防止请求挂起
socket.setdefaulttimeout(15)

def calculate_indicator(df):
    """
    严格按照通达信逻辑判断：当前最后一个交易日是否为“黄线”
    逻辑：金钻趋势线 > 最低价
    """
    try:
        if df is None or len(df) < 80: return False
        
        # 统一格式
        df = df.copy()
        df.columns = [str(c).lower() for c in df.columns]
        m = {'收盘': 'close', '最高': 'high', '最低': 'low', '日期': 'date'}
        df = df.rename(columns=m)
        
        close = df['close'].astype(float)
        high = df['high'].astype(float)
        low = df['low'].astype(float)

        def ema(s, n): return s.ewm(span=n, adjust=False).mean()

        # 1. 计算金钻趋势线 (XMA重心平滑模拟)
        ma_h = ema(ema(high, 25), 25)
        ma_l = ema(ema(low, 25), 25)
        # 金钻趋势线公式
        trend_line = ma_l - (ma_h - ma_l)
        
        # 2. 计算副图指标 (散户线)
        hhv_60 = high.rolling(60).max()
        llv_60 = low.rolling(60).min()
        retail = 100 * (hhv_60 - close) / (hhv_60 - llv_60 + 1e-6)

        # 3. 核心判定 (严格只看最后一根K线)
        # 条件A：趋势线在最低价上方 (这是出现黄线的根本原因)
        is_yellow = trend_line > low
        # 条件B：散户线处于超卖高位 (增加准确度，过滤高位回调)
        is_oversold = retail > 85
        
        # 最终信号：最后一根K线必须同时满足
        last_signal = is_yellow.iloc[-1] and is_oversold.iloc[-1]
        
        return last_signal
    except:
        return False

def download_and_check(code, period="daily"):
    """抓取数据并检测"""
    try:
        # 默认使用东财接口，这是目前最准的
        df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        if df is not None and not df.empty:
            if calculate_indicator(df):
                return code
    except:
        pass
    return None

def main():
    start_time = time.time()
    print(f"[{datetime.datetime.now()}] 🚀 启动严格实时信号扫描...")

    # 1. 获取股票池
    indices = {"上证50": "000016", "沪深300": "000300", "中证1000": "000852", "科创50": "000688"}
    stock_pool = {}
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            for _, row in df.iterrows(): stock_pool[row['品种代码']] = row['品种名称']
        except: pass
    
    all_codes = list(stock_pool.keys())
    print(f"✅ 初始池: {len(all_codes)} 只 | 模式: 仅扫描当前交易日信号")

    # --- Step 1: 扫描日线 (多线程) ---
    daily_hits = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(download_and_check, c, "daily"): c for c in all_codes}
        for future in as_completed(futures):
            res = future.result()
            if res: daily_hits.append(res)
    
    print(f"🔍 日线黄线触发: {len(daily_hits)} 只")
    if not daily_hits:
        send_to_wechat("今日扫描完毕，无符合指标的黄线股票。")
        return

    # --- Step 2 & 3: 漏斗过滤周月线 (仅对日线符合的) ---
    triple_match, double_match, daily_only = [], [], []
    for code in daily_hits:
        time.sleep(0.2)
        # 查周线
        is_w = True if download_and_check(code, "weekly") else False
        
        # 查月线
        is_m = False
        if is_w:
            is_m = True if download_and_check(code, "monthly") else False
        
        tag = f"📌 {code}-{stock_pool[code]}"
        if is_w and is_m:
            triple_match.append(tag)
        elif is_w:
            double_match.append(tag)
        else:
            daily_only.append(tag)

    # --- 构造报告 ---
    duration = int(time.time() - start_time)
    report = f"📅 报告日期: {datetime.date.today()}\n"
    report += f"⏱️ 耗时: {duration}s | 状态: 仅限今日触发信号\n\n"
    
    report += "🌟 [日周月三期共振]\n" + ("\n".join(triple_match) if triple_match else "无") + "\n\n"
    report += "💎 [日周双期共振]\n" + ("\n".join(double_match) if double_match else "无") + "\n\n"
    report += "🟢 [今日日线触发黄线]\n" + ("\n".join(daily_only) if daily_only else "无")

    print(report)
    send_to_wechat(report)

def send_to_wechat(content):
    token = os.environ.get('PUSHPLUS_TOKEN')
    if token:
        try:
            requests.post("http://www.pushplus.plus/send", 
                         json={"token": token, "title": "实时黄线扫描报告", "content": content.replace("\n", "<br>"), "template": "html"},
                         timeout=10)
        except: pass

if __name__ == "__main__":
    main()
