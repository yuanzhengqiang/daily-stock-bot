import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests

def get_indices_stocks():
    """获取上证50、沪深300、科创50成分股"""
    indices = {"上证50": "000016", "沪深300": "000300", "科创50": "000688"}
    all_stocks = {}
    print("正在获取精选成分股列表...")
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            if not df.empty:
                for _, row in df.iterrows():
                    all_stocks[row['品种代码']] = row['品种名称']
            time.sleep(0.5)
        except: continue
    return all_stocks

def calculate_logic(df):
    """计算核心指标逻辑"""
    try:
        if len(df) < 65: return False, False
        close, high, low = df['收盘'].astype(float), df['最高'].astype(float), df['最低'].astype(float)

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

        return is_yellow.iloc[-1], (pink_1.iloc[-1] or pink_2.iloc[-1])
    except: return False, False

def send_wechat(content):
    """通过 PushPlus 推送微信通知"""
    token = os.environ.get('PUSHPLUS_TOKEN')
    if not token: return
    url = "http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": f"🌟 股票多周期扫描报告 - {datetime.date.today()}",
        "content": content.replace("\n", "<br>"),
        "template": "html"
    }
    requests.post(url, json=data)

def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动日/周/月多周期共振扫描...")
    stock_dict = get_indices_stocks()
    if not stock_dict: return

    all_codes = list(stock_dict.keys())
    
    triple_match = []  # 日+周+月
    double_match = []  # 日+周
    daily_only = []    # 仅日线

    for idx, code in enumerate(all_codes):
        if (idx + 1) % 50 == 0: print(f"进度: {idx+1}/{len(all_codes)}...")
        
        try:
            # 1. 检查日线 (基础条件)
            df_d = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            d_yellow, d_pink = calculate_logic(df_d)
            if not (d_yellow and d_pink): continue
            
            # 2. 检查周线
            time.sleep(0.1)
            df_w = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
            w_yellow, w_pink = calculate_logic(df_w)
            
            stock_info = f"{code}-{stock_dict[code]}"
            
            if w_yellow and w_pink:
                # 3. 检查月线
                time.sleep(0.1)
                df_m = ak.stock_zh_a_hist(symbol=code, period="monthly", adjust="qfq")
                m_yellow, m_pink = calculate_logic(df_m)
                
                if m_yellow and m_pink:
                    print(f"🌟 [三期共振] {stock_info}")
                    triple_match.append(stock_info)
                else:
                    print(f"💎 [日周共振] {stock_info}")
                    double_match.append(stock_info)
            else:
                print(f"✅ [仅日线符合] {stock_info}")
                daily_only.append(stock_info)
                
        except: continue

    # 构造微信报告
    report = f"📅 报告日期: {datetime.date.today()}\n\n"
    
    report += "### 🌟 终极推荐 (日+周+月共振)\n"
    report += "\n".join([f"- {s}" for s in triple_match]) if triple_match else "今日无三周期共振股票。\n"
    
    report += "\n### 💎 强化推荐 (日+周共振)\n"
    report += "\n".join([f"- {s}" for s in double_match]) if double_match else "今日无日周共振股票。\n"
    
    report += "\n### 🟢 标准关注 (仅日线符合)\n"
    if daily_only:
        report += "\n".join([f"- {s}" for s in daily_only[:15]])
        if len(daily_only) > 15: report += f"\n...等共 {len(daily_only)} 只"
    else:
        report += "无。"

    print(report)
    send_wechat(report)

if __name__ == "__main__":
    main()
