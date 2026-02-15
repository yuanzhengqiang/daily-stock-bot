import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests

def get_indices_stocks():
    """获取上证50、沪深300、科创50的成分股并去重"""
    indices = {
        "上证50": "000016",
        "沪深300": "000300",
        "科创50": "000688"
    }
    all_stocks = {}
    print("正在获取成分股列表...")
    for name, code in indices.items():
        try:
            print(f"正在抓取 {name} ({code})...")
            df = ak.index_stock_cons(symbol=code)
            if not df.empty:
                for _, row in df.iterrows():
                    all_stocks[row['品种代码']] = row['品种名称']
            time.sleep(1)
        except Exception as e:
            print(f"获取 {name} 失败: {e}")
    return all_stocks

def get_signals(df):
    """纯 pandas 计算指标逻辑 (主图金钻 + 副图粉色)"""
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
        main_yellow = low <= trend_line

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

        return main_yellow.iloc[-1], (pink_1.iloc[-1] or pink_2.iloc[-1])
    except:
        return False, False

def send_wechat(content):
    """通过 PushPlus 发送微信通知"""
    token = os.environ.get('PUSHPLUS_TOKEN')
    if not token:
        print("未配置 PUSHPLUS_TOKEN，跳过微信推送。")
        return

    url = "http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": f"📈 股票共振推荐 - {datetime.date.today()}",
        "content": content.replace("\n", "<br>"),
        "template": "html"
    }
    try:
        res = requests.post(url, json=data)
        print(f"微信推送结果: {res.text}")
    except Exception as e:
        print(f"微信推送出错: {e}")

def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动精选指数扫描...")
    
    stock_dict = get_indices_stocks()
    if not stock_dict:
        print("❌ 错误: 无法获取成分股列表。")
        return

    all_codes = list(stock_dict.keys())
    total = len(all_codes)
    print(f"去重后共计 {total} 只股票。开始扫描...")

    res_resonance = []
    res_yellow = []

    for idx, code in enumerate(all_codes):
        if (idx + 1) % 50 == 0:
            print(f"进度: {idx+1}/{total}...")

        try:
            time.sleep(0.2)
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if df is None or df.empty: continue
            
            yellow, pink = get_signals(df)
            if yellow and pink:
                res_resonance.append(f"🔥 [共振] {code}-{stock_dict[code]}")
            elif yellow:
                res_yellow.append(f"🟡 [触底] {code}-{stock_dict[code]}")
        except:
            continue

    # 构造报告
    report = f"📅 日期: {datetime.date.today()}\n"
    report += "### 💎 强力推荐 (共振)\n"
    report += "\n".join(res_resonance) if res_resonance else "今日无共振信号。"
    report += "\n\n### 🟡 关注 (主图触底)\n"
    report += "\n".join(res_yellow[:20]) if res_yellow else "无。"
    
    print(report)
    send_wechat(report)

if __name__ == "__main__":
    main()
