import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests

# ==========================================
# 1. 核心筛选逻辑 (指标计算)
# ==========================================

def calculate_indicator(df):
    """计算金钻趋势线 + 副图粉色指标"""
    try:
        if df is None or len(df) < 35: return False
        df.columns = [str(c).lower() for c in df.columns]
        # 兼容处理
        m = {'收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'volume'}
        df = df.rename(columns=m)
        close, high, low = df['close'].astype(float), df['high'].astype(float), df['low'].astype(float)

        def ema(s, n): return s.ewm(span=n, adjust=False).mean()
        def sma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()

        # 主图金钻
        ma_h, ma_l = ema(ema(high, 25), 25) , ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        
        # 副图粉色
        hhv_60, llv_60 = high.rolling(window=min(len(df), 60)).max(), low.rolling(window=min(len(df), 60)).min()
        retail = 100 * (hhv_60 - close) / (hhv_60 - llv_60)
        stoch = 100 * (close - low.rolling(window=min(len(df), 27)).min()) / (high.rolling(window=min(len(df), 27)).max() - low.rolling(window=min(len(df), 27)).min())
        price_trend = 3 * sma(stoch, 5) - 2 * sma(sma(stoch, 5), 3)

        # 判定：价格在趋势线下 且 处于超卖区间
        # 增加容错：判断最近2天
        cond = (low <= trend_line) & ((retail > 85) | (price_trend < 15))
        return cond.tail(2).any()
    except: return False

# ==========================================
# 2. 深度分析逻辑 (参考 fork 项目思路优化)
# ==========================================

def perform_deep_analysis(df, code, name):
    """
    量化评分系统：RSI, 均线, 成交量, 乖离率
    """
    try:
        df.columns = [str(c).lower() for c in df.columns]
        df = df.rename(columns={'收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'volume'})
        close = df['close'].astype(float)
        vol = df['volume'].astype(float)
        
        score = 65 # 初始基础分
        reasons = ["符合金钻超跌及副图指标"] # 默认保底理由

        # 1. RSI指标
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        if rsi.iloc[-1] > rsi.iloc[-2] and rsi.iloc[-1] < 50:
            score += 10
            reasons.append("RSI指标低位拐头向上")

        # 2. 5日线夺回
        ma5 = close.rolling(5).mean()
        if close.iloc[-1] > ma5.iloc[-1]:
            score += 10
            reasons.append("股价夺回5日均线")

        # 3. 底部放量
        vol_ma5 = vol.rolling(5).mean()
        if vol.iloc[-1] > vol_ma5.iloc[-1] * 1.3:
            score += 10
            reasons.append("底部成交量明显放大")

        # 4. 20日线乖离
        ma20 = close.rolling(20).mean()
        bias = (close.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] * 100
        if bias < -12:
            score += 5
            reasons.append("超跌负乖离率大，存在修复需求")

        # 评级划分
        if score >= 90: verdict = "🌟 强烈建议关注"
        elif score >= 80: verdict = "💎 值得关注"
        else: verdict = "🟢 基础买点"

        # 构造分析文本
        analysis_report = f"【量化评分: {score}分 | {verdict}】\n"
        analysis_report += "📝 理由: " + "；".join(reasons)
        return analysis_report
    except:
        return "⚠️ 分析模型计算异常"

# ==========================================
# 3. 执行流程
# ==========================================

def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动 A 股全维度‘筛选+分析’系统...")
    
    # 扫描精选指数池
    indices = {"上证50": "000016", "沪深300": "000300", "中证1000": "000852", "科创50": "000688"}
    stock_dict = {}
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            for _, row in df.iterrows(): stock_dict[row['品种代码']] = row['品种名称']
        except: continue

    all_codes = list(stock_dict.keys())
    total = len(all_codes)
    print(f"成分股去重完毕，共计 {total} 只。开始逐一诊断...")

    triple_match, double_match, daily_match = [], [], []
    last_date = "未知"

    for idx, code in enumerate(all_codes):
        if (idx+1) % 200 == 0: print(f"扫描进度: {idx+1}/{total}")
        try:
            # 1. 获取日线数据
            df_d = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if df_d is None or df_d.empty: continue
            if last_date == "未知": last_date = df_d.iloc[-1]['日期']
            
            # 判断日线是否符合你的金钻指标
            if calculate_indicator(df_d):
                # 符合日线后，运行深度分析获取评分和理由
                analysis_detail = perform_deep_analysis(df_d, code, stock_dict[code])
                stock_report = f"📌 {code}-{stock_dict[code]}\n{analysis_detail}"
                
                # 2. 进阶检查周线、月线
                time.sleep(0.1)
                df_w = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
                df_m = ak.stock_zh_a_hist(symbol=code, period="monthly", adjust="qfq")
                
                if calculate_indicator(df_w) and calculate_indicator(df_m):
                    triple_match.append(stock_report)
                elif calculate_indicator(df_w):
                    double_match.append(stock_report)
                else:
                    daily_match.append(stock_report) # 日线股票现在也带详细理由了
        except: continue

    # 4. 构造微信报告
    final_content = f"📅 报告日期: {datetime.date.today()}\n📊 数据截止: {last_date}\n\n"
    
    if triple_match:
        final_content += "🔥 [极品共振 - 三期合一]\n" + "\n\n".join(triple_match) + "\n\n"
    
    if double_match:
        final_content += "💎 [强化推荐 - 日周共振]\n" + "\n\n".join(double_match) + "\n\n"
        
    if daily_match:
        final_content += "🟢 [基础信号 - 日线超跌]\n" + "\n\n".join(daily_match[:15]) + "\n"
        if len(daily_match) > 15: final_content += f"...等共 {len(daily_match)} 只\n"

    if not (triple_match or double_match or daily_match):
        final_content += "今日扫描范围内未发现符合信号的股票。"

    print(final_content)

    # 5. 推送微信
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
