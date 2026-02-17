import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests

# ==========================================
# 1. 核心筛选逻辑 (你原有的日周月共振)
# ==========================================

def calculate_indicator(df):
    """计算金钻+粉色指标，返回是否符合信号"""
    try:
        if df is None or len(df) < 60: return False
        df.columns = [str(c).lower() for c in df.columns]
        df = df.rename(columns={'收盘': 'close', '最高': 'high', '最低': 'low'})
        close, high, low = df['close'].astype(float), df['high'].astype(float), df['low'].astype(float)

        def ema(s, n): return s.ewm(span=n, adjust=False).mean()
        def sma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()

        # 主图金钻
        ma_h, ma_l = ema(ema(high, 25), 25), ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        
        # 副图粉色
        hhv_60, llv_60 = high.rolling(60).max(), low.rolling(60).min()
        retail = 100 * (hhv_60 - close) / (hhv_60 - llv_60)
        stoch = 100 * (close - low.rolling(27).min()) / (high.rolling(27).max() - low.rolling(27).min())
        price_trend = 3 * sma(stoch, 5) - 2 * sma(sma(stoch, 5), 3)

        # 判断：价格在趋势线下 且 (散户线超卖 或 趋势线超卖)
        cond = (low <= trend_line) & ((retail > 85) | (price_trend < 15))
        return cond.tail(3).any()
    except: return False

# ==========================================
# 2. 深度分析逻辑 (参考 ZhuLinsen/daily_stock_analysis)
# ==========================================

def perform_deep_analysis(df, code, name):
    """
    参考 fork 项目的逻辑：综合 RSI, MA, 乖离率和成交量进行评分
    返回：评分(0-100) + 投资建议
    """
    try:
        df.columns = [str(c).lower() for c in df.columns]
        df = df.rename(columns={'收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'volume'})
        close = df['close'].astype(float)
        
        score = 60 # 基础分 (因为能过筛选逻辑，本身已经有60分基础)
        reasons = []

        # 1. 检查 RSI (判断是否过度杀跌后开始回升)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        if 30 < current_rsi < 50:
            score += 15
            reasons.append("RSI从超卖区回升，具备反弹动力")
        
        # 2. 均线系统 (检查是否站上5日线)
        ma5 = close.rolling(5).mean()
        if close.iloc[-1] > ma5.iloc[-1]:
            score += 10
            reasons.append("股价站上5日均线，短线走强")
        
        # 3. 成交量检查 (是否有放量迹象)
        vol_ma5 = df['volume'].rolling(5).mean()
        if df['volume'].iloc[-1] > vol_ma5.iloc[-1] * 1.2:
            score += 10
            reasons.append("成交量较均值放量，资金介入明显")
        
        # 4. 乖离率检查 (防范二次杀跌)
        bias = (close.iloc[-1] - close.rolling(20).mean().iloc[-1]) / close.rolling(20).mean().iloc[-1] * 100
        if bias < -10:
            score += 5
            reasons.append("偏离20日均线过远，存在估值修复空间")

        # 投资结论
        if score >= 85:
            verdict = "🌟 强烈建议关注 (Strong Buy)"
        elif score >= 75:
            verdict = "💎 建议关注 (Buy)"
        else:
            verdict = "🟢 观望/试探 (Watch)"

        analysis_report = f"【技术评分: {score}分】\n"
        analysis_report += f"📊 结论: {verdict}\n"
        analysis_report += "📝 理由: " + "；".join(reasons)
        return analysis_report
    except:
        return "⚠️ 分析模型计算异常"

# ==========================================
# 3. 主流程
# ==========================================

def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动 A 股全维度‘筛选+分析’系统...")
    
    # 获取成分股 (上证50, 沪深300, 中证1000, 科创50)
    stocks = {}
    indices = {"上证50": "000016", "沪深300": "000300", "中证1000": "000852", "科创50": "000688"}
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            for _, row in df.iterrows(): stocks[row['品种代码']] = row['品种名称']
        except: continue

    all_codes = list(stocks.keys())
    total = len(all_codes)
    
    triple_match, double_match, daily_match = [], [], []
    last_date = "未知"

    for idx, code in enumerate(all_codes):
        if (idx+1) % 200 == 0: print(f"进度: {idx+1}/{total}")
        try:
            # 1. 基础筛选 (日线)
            df_d = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if df_d is None or df_d.empty: continue
            if last_date == "未知": last_date = df_d.iloc[-1]['日期']
            
            if calculate_indicator(df_d):
                # 只有日线符合，才进行更高级别的周线、月线检查
                time.sleep(0.1)
                df_w = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
                df_m = ak.stock_zh_a_hist(symbol=code, period="monthly", adjust="qfq")
                
                res_w = calculate_indicator(df_w)
                res_m = calculate_indicator(df_m)
                
                # 运行来自 fork 项目的深度分析逻辑
                analysis_detail = perform_deep_analysis(df_d, code, stocks[code])
                stock_report = f"📌 {code}-{stocks[code]}\n{analysis_detail}"
                
                if res_w and res_m:
                    triple_match.append(stock_report)
                elif res_w:
                    double_match.append(stock_report)
                else:
                    daily_match.append(f"📌 {code}-{stocks[code]} (短线复苏信号)")
        except: continue

    # 报告构造
    final_content = f"📅 报告日期: {datetime.date.today()}\n📊 数据截止: {last_date}\n\n"
    
    if triple_match:
        final_content += "🔥 [极品共振 - 三期合一]\n" + "\n\n".join(triple_match) + "\n\n"
    
    if double_results := double_match:
        final_content += "💎 [强化推荐 - 日周共振]\n" + "\n\n".join(double_results) + "\n\n"
        
    if daily_results := daily_match:
        final_content += "🟢 [基础信号 - 日线超跌]\n" + "\n".join(daily_results[:20]) + "\n"
        if len(daily_results) > 20: final_content += f"...等共 {len(daily_results)} 只\n"

    print(final_content)

    # 微信推送 (PushPlus)
    token = os.environ.get('PUSHPLUS_TOKEN')
    if token:
        requests.post("http://www.pushplus.plus/send", json={
            "token": token,
            "title": f"今日股票深度筛选报告",
            "content": final_content.replace("\n", "<br>"),
            "template": "html"
        })

if __name__ == "__main__":
    main()
