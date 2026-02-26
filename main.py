import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests
import random

def get_indices_stocks():
    """获取精选成分股"""
    indices = {"上证50": "000016", "沪深300": "000300", "中证1000": "000852", "科创50": "000688"}
    all_stocks = {}
    print("正在抓取成分股列表...")
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            if not df.empty:
                for _, row in df.iterrows():
                    all_stocks[row['品种代码']] = row['品种名称']
            time.sleep(0.5)
        except: pass
    return all_stocks

def calculate_indicator(df):
    """
    核心指标计算逻辑
    """
    try:
        if df is None or len(df) < 35: return False
        df.columns = [str(c).lower() for c in df.columns]
        # 兼容东财和新浪的列名
        m = {'收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'volume'}
        df = df.rename(columns=m)
        close, high, low = df['close'].astype(float), df['high'].astype(float), df['low'].astype(float)

        def ema(s, n): return s.ewm(span=n, adjust=False).mean()
        def sma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()

        # 金钻趋势线
        ma_h, ma_l = ema(ema(high, 25), 25) , ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        
        # 副图粉色指标
        hhv_60 = high.rolling(window=min(len(df), 60)).max()
        llv_60 = low.rolling(window=min(len(df), 60)).min()
        retail = 100 * (hhv_60 - close) / (hhv_60 - llv_60)
        stoch = 100 * (close - low.rolling(window=min(len(df), 27)).min()) / (high.rolling(window=min(len(df), 27)).max() - low.rolling(window=min(len(df), 27)).min())
        price_trend = 3 * sma(stoch, 5) - 2 * sma(sma(stoch, 5), 3)

        # 核心：价格在趋势线下 且 处于超卖区间
        cond = (low <= trend_line) & ((retail > 85) | (price_trend < 15))
        return cond.tail(2).any()
    except: return False

def perform_deep_analysis(df, code):
    """深度量化评分 (基于日线数据)"""
    try:
        df.columns = [str(c).lower() for c in df.columns]
        df = df.rename(columns={'收盘': 'close', '成交量': 'volume'})
        close, vol = df['close'].astype(float), df['volume'].astype(float)
        score, reasons = 65, ["符合基础抄底指标"]

        # RSI回升
        delta = close.diff()
        gain, loss = (delta.where(delta > 0, 0)).rolling(14).mean(), (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain/loss))
        if rsi.iloc[-1] > rsi.iloc[-2] and rsi.iloc[-1] < 45:
            score += 10; reasons.append("RSI低位拐头")
        # 5日线
        if close.iloc[-1] > close.rolling(5).mean().iloc[-1]:
            score += 10; reasons.append("站上5日线")
        # 放量
        if vol.iloc[-1] > vol.rolling(5).mean().iloc[-1] * 1.2:
            score += 10; reasons.append("底部温和放量")

        return f"【评分: {score}】📝 {';'.join(reasons)}"
    except: return "【评分: 65】📝 基础指标触发"

def fetch_history_with_fallback(code, period="daily"):
    """
    抓取历史数据的双重保险，修复了 period 参数无效的 Bug
    """
    # 策略1: 东财 (支持 daily, weekly, monthly)
    try:
        df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        if df is not None and not df.empty: return df
    except: pass
    
    # 策略2: 新浪 (备用，注意新浪接口对周月的支持有限，仅当日线失败时尝试)
    if period == "daily":
        try:
            prefix = "sh" if code.startswith("6") else "sz"
            df = ak.stock_zh_a_daily(symbol=f"{prefix}{code}", adjust="qfq")
            if df is not None and not df.empty:
                return df.rename(columns={'close':'收盘','high':'最高','low':'最低','volume':'成交量'})
        except: pass
    return None

def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动深度扫描系统...")
    
    # 1. 获取日期
    last_date = "获取中"
    try:
        test_df = ak.stock_zh_index_daily_em(symbol="sh000300")
        last_date = test_df.iloc[-1]['date']
    except: pass

    stock_dict = get_indices_stocks()
    all_codes = list(stock_dict.keys())
    
    triple_match, double_match, daily_match = [], [], []
    success_count = 0

    # 2. 核心扫描
    for idx, code in enumerate(all_codes):
        if (idx+1) % 150 == 0: print(f"进度: {idx+1}/{len(all_codes)} (已抓取: {success_count})")
        
        try:
            # 基础判断：日线
            df_d = fetch_history_with_fallback(code, "daily")
            if df_d is None or df_d.empty: continue
            
            success_count += 1
            if calculate_indicator(df_d):
                # 进阶判断：周线和月线
                time.sleep(0.1) # 避开频率限制
                df_w = fetch_history_with_fallback(code, "weekly")
                df_m = fetch_history_with_fallback(code, "monthly")
                
                is_w = calculate_indicator(df_w)
                is_m = calculate_indicator(df_m)
                
                # 深度分析
                analysis = perform_deep_analysis(df_d, code)
                report_item = f"📌 {code}-{stock_dict[code]}\n   └ {analysis}"
                
                if is_w and is_m:
                    triple_match.append(report_item)
                elif is_w:
                    double_match.append(report_item)
                else:
                    daily_match.append(report_item)
        except: continue

    # 3. 构造报告
    content = f"📅 报告日期: {datetime.date.today()}\n📊 数据截止: {last_date}\n"
    content += f"📈 尝试扫描: {len(all_codes)} 只 | 成功抓取: {success_count} 只\n\n"

    if triple_match:
        content += "🔥 [极品共振 - 日周月合力]\n" + "\n".join(triple_match) + "\n\n"
    else:
        content += "🔥 [极品共振]: 今日无\n\n"

    if double_match:
        content += "💎 [强化推荐 - 日周共振]\n" + "\n".join(double_match) + "\n\n"
    
    if daily_match:
        content += "🟢 [基础信号 - 仅日线符合]\n" + "\n".join(daily_match[:25]) + "\n"
        if len(daily_match) > 25: content += f"...等共 {len(daily_match)} 只\n"

    print(content)
    
    token = os.environ.get('PUSHPLUS_TOKEN')
    if token:
        requests.post("http://www.pushplus.plus/send", json={
            "token": token, "title": "修复版股票深度扫描报告", "content": content.replace("\n", "<br>"), "template": "html"
        })

if __name__ == "__main__":
    main()
