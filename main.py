import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests

def get_indices_stocks():
    """获取多指数成分股并去重"""
    indices = {"上证50": "000016", "沪深300": "000300", "中证1000": "000852", "科创50": "000688"}
    all_stocks = {}
    print("正在抓取成分股列表...")
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            if not df.empty:
                for _, row in df.iterrows():
                    all_stocks[row['品种代码']] = [row['品种名称'], 'A']
            time.sleep(0.5)
        except: continue
    
    # 港股部分 (增加稳定性处理)
    try:
        hk_spot = ak.stock_hk_spot_em()
        if not hk_spot.empty:
            # 筛选核心港股科技股 (前100名中包含特定关键词或代码的)
            for _, row in hk_spot.head(100).iterrows():
                if any(x in row['名称'] for x in ['科技', '网', '汽车', '核心']) or row['代码'] in ['00700', '03690', '09988', '09888', '01810', '01024', '09618']:
                    all_stocks[row['代码']] = [row['名称'], 'HK']
    except: pass
    return all_stocks

def calculate_logic(df):
    """三周期核心指标逻辑"""
    try:
        if df is None or len(df) < 70: return False, False
        
        # 统一列名
        df.columns = [c.lower() for c in df.columns]
        mapping = {'收盘': 'close', '最高': 'high', '最低': 'low', '开盘': 'open'}
        df = df.rename(columns=mapping)
        
        close, high, low = df['close'].astype(float), df['high'].astype(float), df['low'].astype(float)

        def ema(series, n): return series.ewm(span=n, adjust=False).mean()
        def sma_tdx(series, n): return series.ewm(alpha=1/n, adjust=False).mean()

        # 1. 主图金钻
        ma_h, ma_l = ema(ema(high, 25), 25), ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        is_yellow = low <= trend_line

        # 2. 副图粉色
        hhv_60, llv_60 = high.rolling(60).max(), low.rolling(60).min()
        retail_line = 100 * (hhv_60 - close) / (hhv_60 - llv_60)
        pink_1 = (retail_line.shift(1) >= 90) & (retail_line < 90)

        stoch_27 = 100 * (close - low.rolling(27).min()) / (high.rolling(27).max() - low.rolling(27).min())
        sma_5, sma_3 = sma_tdx(stoch_27, 5), sma_tdx(sma_5, 3)
        price_trend = 3 * sma_5 - 2 * sma_3
        pink_2 = price_trend <= 10

        # 返回最后一点的布尔值
        return is_yellow.iloc[-1], (pink_1.iloc[-1] or pink_2.iloc[-1])
    except Exception as e:
        return False, False

def get_history(code, period, stock_type):
    """抓取历史数据，确保非交易日也能拿到最后的数据"""
    try:
        if stock_type == 'A':
            # A股增加重试机制
            return ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        else:
            return ak.stock_hk_hist(symbol=code, period=period, adjust="qfq")
    except:
        return None

def send_wechat(content):
    token = os.environ.get('PUSHPLUS_TOKEN')
    if not token: return
    url = "http://www.pushplus.plus/send"
    data = {"token": token, "title": f"🌟 股票多周期共振报告", "content": content.replace("\n", "<br>"), "template": "html"}
    requests.post(url, json=data)

def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动扫描...")
    stock_dict = get_indices_stocks()
    if not stock_dict: return

    all_codes = list(stock_dict.keys())
    total = len(all_codes)
    
    triple_match, double_match, daily_only = [], [], []
    last_trading_date = "未知"

    for idx, code in enumerate(all_codes):
        stock_name, stock_type = stock_dict[code]
        if (idx + 1) % 150 == 0: print(f"进度: {idx+1}/{total}...")
        
        try:
            # 1. 检查日线
            df_d = get_history(code, "daily", stock_type)
            if df_d is None or df_d.empty: continue
            
            # 顺便提取一下最近的交易日期作为报表头
            if last_trading_date == "未知":
                last_trading_date = df_d.iloc[-1]['日期'] if '日期' in df_d.columns else df_d.iloc[-1].name

            d_yellow, d_pink = calculate_logic(df_d)
            if not (d_yellow and d_pink): continue
            
            # 2. 检查周线
            df_w = get_history(code, "weekly", stock_type)
            w_yellow, w_pink = calculate_logic(df_w)
            
            stock_info = f"{code}-{stock_name}({stock_type})"
            
            if w_yellow and w_pink:
                # 3. 检查月线
                df_m = get_history(code, "monthly", stock_type)
                m_yellow, m_pink = calculate_logic(df_m)
                if m_yellow and m_pink:
                    triple_match.append(stock_info)
                else:
                    double_match.append(stock_info)
            else:
                daily_only.append(stock_info)
            
            time.sleep(0.1)
        except: continue

    # 构造报告
    report = f"📅 报告日期: {datetime.date.today()}\n"
    report += f"📊 数据截止: {last_trading_date}\n"
    report += f"🔍 范围: 50/300/1000/科50/港科\n"
    report += f"✅ 扫描总量: {total} 只\n\n"
    
    report += "### 🌟 终极推荐 (日+周+月)\n"
    report += "\n".join([f"- {s}" for s in triple_match]) if triple_match else "今日无。\n"
    
    report += "\n### 💎 强化推荐 (日+周)\n"
    report += "\n".join([f"- {s}" for s in double_match]) if double_match else "今日无。\n"
    
    report += "\n### 🟢 标准关注 (日线)\n"
    if daily_only:
        report += "\n".join([f"- {s}" for s in daily_only[:25]])
        if len(daily_only) > 25: report += f"\n...等共 {len(daily_only)} 只"
    else: report += "无。"

    print(report)
    send_wechat(report)

if __name__ == "__main__":
    main()
