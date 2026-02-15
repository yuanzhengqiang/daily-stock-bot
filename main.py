import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests

def get_indices_stocks():
    """获取成分股列表"""
    indices = {"上证50": "000016", "沪深300": "000300", "科创50": "000688"}
    all_stocks = {}
    print("正在获取成分股列表...")
    for name, code in indices.items():
        try:
            df = ak.index_stock_cons(symbol=code)
            if not df.empty:
                for _, row in df.iterrows():
                    all_stocks[row['品种代码']] = row['品种名称']
            time.sleep(0.5)
        except Exception as e:
            print(f"获取 {name} 失败: {e}")
    return all_stocks

def calculate_logic(df):
    """
    通用指标计算逻辑，适用于日线或周线数据
    """
    try:
        if len(df) < 65: return False, False
        close = df['收盘'].astype(float)
        high = df['最高'].astype(float)
        low = df['最低'].astype(float)

        def ema(series, n): return series.ewm(span=n, adjust=False).mean()
        def sma_tdx(series, n): return series.ewm(alpha=1/n, adjust=False).mean()

        # 1. 主图逻辑: 金钻趋势
        ma_h = ema(ema(high, 25), 25)
        ma_l = ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        is_yellow = low <= trend_line

        # 2. 副图逻辑: 散户线 + 股价趋势
        hhv_60 = high.rolling(60).max()
        llv_60 = low.rolling(60).min()
        retail_line = 100 * (hhv_60 - close) / (hhv_60 - llv_60)
        pink_1 = (retail_line.shift(1) >= 90) & (retail_line < 90)

        stoch_27 = 100 * (close - low.rolling(27).min()) / (high.rolling(27).max() - low.rolling(27).min())
        sma_5 = sma_tdx(stoch_27, 5)
        sma_3 = sma_tdx(sma_5, 3)
        price_trend = 3 * sma_5 - 2 * sma_3
        pink_2 = price_trend <= 10

        return is_yellow.iloc[-1], (pink_1.iloc[-1] or pink_2.iloc[-1])
    except:
        return False, False

def send_wechat(content):
    """微信推送"""
    token = os.environ.get('PUSHPLUS_TOKEN')
    if not token: return
    url = "http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": f"🔔 日周共振超强信号 - {datetime.date.today()}",
        "content": content.replace("\n", "<br>"),
        "template": "html"
    }
    requests.post(url, json=data)

def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动日周线共振扫描...")
    stock_dict = get_indices_stocks()
    if not stock_dict: return

    all_codes = list(stock_dict.keys())
    total = len(all_codes)
    
    super_resonance = [] # 日周共振
    daily_only = []      # 仅日线符合

    for idx, code in enumerate(all_codes):
        if (idx + 1) % 50 == 0: print(f"扫描进度: {idx+1}/{total}...")
        
        try:
            # 1. 抓取日线数据
            df_d = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            d_yellow, d_pink = calculate_logic(df_d)
            
            # 如果日线都不符合，就不浪费时间抓周线了
            if not (d_yellow and d_pink):
                continue
            
            # 2. 抓取周线数据 (只有日线符合了才看周线)
            time.sleep(0.1) # 稍微延迟防封
            df_w = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
            w_yellow, w_pink = calculate_logic(df_w)
            
            stock_info = f"{code}-{stock_dict[code]}"
            
            if w_yellow and w_pink:
                print(f"💎 [日周共振] {stock_info}")
                super_resonance.append(stock_info)
            else:
                print(f"✅ [仅日线符合] {stock_info}")
                daily_only.append(stock_info)
                
        except Exception as e:
            continue

    # 构造推送报告
    report = f"📅 日期: {datetime.date.today()}\n"
    report += "## 💎 日周线双重共振 (极高成功率)\n"
    report += "\n".join([f"- {s}" for s in super_resonance]) if super_resonance else "今日无共振信号。"
    
    report += "\n\n### 🟢 仅日线符合 (波段机会)\n"
    report += "\n".join([f"- {s}" for s in daily_only[:15]]) if daily_only else "无。"
    if len(daily_only) > 15: report += f"\n...等共 {len(daily_only)} 只"

    print(report)
    send_wechat(report)

if __name__ == "__main__":
    main()
