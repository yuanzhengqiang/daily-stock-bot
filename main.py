import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests
import random

def get_indices_stocks():
    """获取成分股列表"""
    indices = {"上证50": "000016", "沪深300": "000300", "中证1000": "000852", "科创50": "000688"}
    all_stocks = {}
    print("正在抓取成分股列表...")
    for name, code in indices.items():
        for _ in range(3): # 失败重试
            try:
                df = ak.index_stock_cons(symbol=code)
                if not df.empty:
                    for _, row in df.iterrows():
                        all_stocks[row['品种代码']] = row['品种名称']
                    break
            except:
                time.sleep(2)
    return all_stocks

def calculate_indicator(df):
    """核心指标计算"""
    try:
        if df is None or len(df) < 35: return False
        df.columns = [str(c).lower() for c in df.columns]
        m = {'收盘': 'close', '最高': 'high', '最低': 'low'}
        df = df.rename(columns=m)
        close, high, low = df['close'].astype(float), df['high'].astype(float), df['low'].astype(float)

        def ema(s, n): return s.ewm(span=n, adjust=False).mean()
        def sma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()

        ma_h, ma_l = ema(ema(high, 25), 25) , ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        
        hhv_60, llv_60 = high.rolling(window=min(len(df), 60)).max(), low.rolling(window=min(len(df), 60)).min()
        retail = 100 * (hhv_60 - close) / (hhv_60 - llv_60)
        stoch = 100 * (close - low.rolling(window=min(len(df), 27)).min()) / (high.rolling(window=min(len(df), 27)).max() - low.rolling(window=min(len(df), 27)).min())
        price_trend = 3 * sma(stoch, 5) - 2 * sma(sma(stoch, 5), 3)

        cond = (low <= trend_line) & ((retail > 85) | (price_trend < 15))
        return cond.tail(2).any()
    except: return False

def perform_deep_analysis(df, code, name):
    """深度量化评分"""
    try:
        df.columns = [str(c).lower() for c in df.columns]
        df = df.rename(columns={'收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'volume'})
        close, vol = df['close'].astype(float), df['volume'].astype(float)
        score, reasons = 65, ["符合金钻超跌指标"]

        # RSI
        delta = close.diff()
        gain, loss = (delta.where(delta > 0, 0)).rolling(14).mean(), (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain/loss))
        if rsi.iloc[-1] > rsi.iloc[-2] and rsi.iloc[-1] < 50:
            score += 10; reasons.append("RSI低位拐头")
        # 5日线
        if close.iloc[-1] > close.rolling(5).mean().iloc[-1]:
            score += 10; reasons.append("夺回5日线")
        # 放量
        if vol.iloc[-1] > vol.rolling(5).mean().iloc[-1] * 1.3:
            score += 10; reasons.append("底部放量")

        verdict = "🌟 强力" if score >= 90 else ("💎 关注" if score >= 80 else "🟢 基础")
        return f"【评分: {score} | {verdict}】\n📝: {';'.join(reasons)}"
    except: return "⚠️ 分析异常"

def main():
    print(f"[{datetime.datetime.now()}] 🚀 系统启动...")
    
    # --- 1. 强制获取日期预检 ---
    last_date = "未知"
    try:
        test_df = ak.stock_zh_index_daily_em(symbol="sh000300")
        last_date = test_df.iloc[-1]['date']
        print(f"✅ 预检成功，当前最新交易日: {last_date}")
    except:
        print("❌ 预检失败，数据源连接受阻")

    stock_dict = get_indices_stocks()
    all_codes = list(stock_dict.keys())
    
    triple_match, double_match, daily_match = [], [], []
    success_count = 0

    # --- 2. 扫描 ---
    for idx, code in enumerate(all_codes):
        if (idx+1) % 100 == 0: print(f"进度: {idx+1}/{len(all_codes)} (已成功抓取: {success_count})")
        
        try:
            # 增加随机延迟，降低被封风险
            if idx % 10 == 0: time.sleep(random.uniform(0.5, 1.5))
            
            df_d = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if df_d is None or df_d.empty: continue
            
            success_count += 1
            if calculate_indicator(df_d):
                analysis = perform_deep_analysis(df_d, code, stock_dict[code])
                report_item = f"📌 {code}-{stock_dict[code]}\n{analysis}"
                
                # 检查周月
                df_w = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
                df_m = ak.stock_zh_a_hist(symbol=code, period="monthly", adjust="qfq")
                if calculate_indicator(df_w) and calculate_indicator(df_m):
                    triple_match.append(report_item)
                elif calculate_indicator(df_w):
                    double_match.append(report_item)
                else:
                    daily_match.append(report_item)
        except: continue

    # --- 3. 报告内容 ---
    content = f"📅 报告日期: {datetime.date.today()}\n📊 数据截止: {last_date}\n"
    content += f"📈 尝试扫描: {len(all_codes)} 只 | 成功抓取: {success_count} 只\n"
    if success_count < (len(all_codes) * 0.5):
        content += "⚠️ 警告：大量数据抓取失败，可能由于 GitHub IP 被封锁，请尝试手动重新运行。\n"
    content += "\n"

    if triple_match: content += "🔥 [极品共振]\n" + "\n\n".join(triple_match) + "\n\n"
    if double_match: content += "💎 [日周共振]\n" + "\n\n".join(double_match) + "\n\n"
    if daily_match:
        content += "🟢 [基础信号]\n" + "\n\n".join(daily_match[:15]) + "\n"
        if len(daily_match) > 15: content += f"...等共 {len(daily_match)} 只\n"

    if not (triple_match or double_match or daily_match):
        content += "今日扫描范围内未发现符合信号的股票。"

    print(content)
    
    token = os.environ.get('PUSHPLUS_TOKEN')
    if token:
        requests.post("http://www.pushplus.plus/send", json={
            "token": token, "title": "股票深度筛选报告", "content": content.replace("\n", "<br>"), "template": "html"
        })

if __name__ == "__main__":
    main()
