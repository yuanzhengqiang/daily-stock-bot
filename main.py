import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制缩短全局超时，防止死等
socket.setdefaulttimeout(7)

def calculate_logic(df, mode="daily"):
    """指标计算核心逻辑"""
    try:
        if df is None or len(df) < 60: return False
        df.columns = [str(c).lower() for c in df.columns]
        m = {'收盘': 'close', '最高': 'high', '最低': 'low'}
        df = df.rename(columns=m)
        close, high, low = df['close'].astype(float), df['high'].astype(float), df['low'].astype(float)

        def ema(s, n): return s.ewm(span=n, adjust=False).mean()
        ma_h = ema(ema(high, 25), 25)
        ma_l = ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        
        hhv_60 = high.rolling(60).max()
        llv_60 = low.rolling(60).min()
        retail = 100 * (hhv_60 - close) / (hhv_60 - llv_60)

        if mode == "daily":
            # 日线：价格触底 + 能量超跌
            cond = (low <= trend_line * 1.005) & (retail > 85)
            return cond.tail(2).any()
        else:
            # 周月线：大趋势处于底部区域
            cond = low <= trend_line * 1.02
            return cond.tail(3).any()
    except:
        return False

def download_and_check(code, period="daily"):
    """单只股票的下载与检测任务"""
    try:
        # 尝试从东财抓取
        df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        if df is not None and not df.empty:
            if calculate_logic(df, period):
                return code
    except:
        pass
    return None

def main():
    start_time = time.time()
    print(f"[{datetime.datetime.now()}] 🚀 启动多线程漏斗筛选系统...")

    # 1. 获取初始池 (约 1400 只)
    indices = {"上证50": "000016", "沪深300": "000300", "中证1000": "000852", "科创50": "000688"}
    stock_pool = {}
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            for _, row in df.iterrows(): stock_pool[row['品种代码']] = row['品种名称']
        except: pass
    
    all_codes = list(stock_pool.keys())
    print(f"✅ 初始池: {len(all_codes)} 只股票")

    # --- Step 1: 多线程扫描日线 (最耗时的一步) ---
    print(f"Step 1: 正在多线程并发扫描日线 (线程数: 10)...")
    daily_passed = []
    
    # 使用线程池加速
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_code = {executor.submit(download_and_check, code, "daily"): code for code in all_codes}
        for future in as_completed(future_to_code):
            res = future.result()
            if res:
                daily_passed.append(res)
    
    print(f"🔍 日线符合: {len(daily_passed)} 只")
    if not daily_passed:
        send_report("今日全市场无符合日线指标的股票。", 0)
        return

    # --- Step 2: 过滤周线 (仅针对日线通过的，数量少，可以单线程) ---
    print("Step 2: 正在扫描周线...")
    weekly_passed = []
    for code in daily_passed:
        if download_and_check(code, "weekly"):
            weekly_passed.append(code)
            time.sleep(0.2)
    
    # --- Step 3: 过滤月线 ---
    print("Step 3: 正在扫描月线...")
    monthly_passed = []
    for code in weekly_passed:
        if download_and_check(code, "monthly"):
            monthly_passed.append(code)
            time.sleep(0.2)

    # --- 构造报告 ---
    res_3 = [f"📌 {c}-{stock_pool[c]}" for c in monthly_passed]
    res_2 = [f"📌 {c}-{stock_pool[c]}" for c in weekly_passed if c not in monthly_passed]
    res_1 = [f"📌 {c}-{stock_pool[c]}" for c in daily_passed if c not in weekly_passed]

    report = f"📅 日期: {datetime.date.today()}\n"
    report += f"⏱️ 总耗时: {int(time.time() - start_time)}s | 漏斗结果: {len(all_codes)}→{len(daily_passed)}→{len(weekly_passed)}→{len(monthly_passed)}\n\n"
    
    report += "🌟 [终极推荐: 日周月共振]\n" + ("\n".join(res_3) if res_3 else "无") + "\n\n"
    report += "💎 [强化推荐: 日周共振]\n" + ("\n".join(res_2) if res_2 else "无") + "\n\n"
    report += "🟢 [基础信号: 仅日线符合]\n" + ("\n".join(res_1[:30]) if res_1 else "无")
    if len(res_1) > 30: report += f"\n...等共 {len(res_1)} 只"

    print(report)
    send_report(report)

def send_report(content, count=0):
    token = os.environ.get('PUSHPLUS_TOKEN')
    if token:
        try:
            requests.post("http://www.pushplus.plus/send", 
                         json={"token": token, "title": "多线程股票漏斗报告", "content": content.replace("\n", "<br>"), "template": "html"},
                         timeout=10)
        except: pass

if __name__ == "__main__":
    main()
