import akshare as ak
import pandas as pd
import datetime
import time

def get_indices_stocks():
    """
    获取上证50、沪深300、科创50的成分股并去重
    """
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
            # 获取成分股
            df = ak.index_stock_cons(symbol=code)
            if not df.empty:
                # 建立 代码 -> 名称 的映射
                for _, row in df.iterrows():
                    all_stocks[row['品种代码']] = row['品种名称']
            time.sleep(1) # 稍微歇一下
        except Exception as e:
            print(f"获取 {name} 失败: {e}")
            
    return all_stocks

def get_signals(df):
    """
    纯 pandas 指标计算逻辑 (主图金钻 + 副图粉色)
    """
    try:
        if len(df) < 65: return False, False
        close = df['收盘'].astype(float)
        high = df['最高'].astype(float)
        low = df['最低'].astype(float)

        # 核心算法
        def ema(series, n): return series.ewm(span=n, adjust=False).mean()
        def sma_tdx(series, n): return series.ewm(alpha=1/n, adjust=False).mean()

        # 主图逻辑
        ma_h = ema(ema(high, 25), 25)
        ma_l = ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        main_yellow = low <= trend_line

        # 副图逻辑
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

def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动精选指数扫描 (50+300+科创50)...")
    
    stock_dict = get_indices_stocks()
    if not stock_dict:
        print("❌ 错误: 无法获取任何成分股列表。")
        return

    all_codes = list(stock_dict.keys())
    total = len(all_codes)
    print(f"去重后共计 {total} 只股票。开始深度扫描...")

    res_resonance = []
    res_yellow = []

    for idx, code in enumerate(all_codes):
        if (idx + 1) % 50 == 0:
            print(f"进度: {idx+1}/{total}...")

        try:
            # 即使股票少了，也建议保留微小延迟，模拟真实访问
            time.sleep(0.2) 
            
            # 获取历史行情
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if df is None or df.empty: continue
            
            yellow, pink = get_signals(df)
            
            if yellow and pink:
                msg = f"🔥 [双重共振] {code} - {stock_dict[code]}"
                print(msg)
                res_resonance.append(msg)
            elif yellow:
                res_yellow.append(f"🟡 [主图触底] {code} - {stock_dict[code]}")
        except Exception:
            continue

    # 打印最终报表
    print("\n" + "="*40)
    print(f"📅 扫描日期: {datetime.date.today()}")
    print(f"✅ 扫描范围: 上证50 / 沪深300 / 科创50")
    print("="*40)
    
    print("\n### 💎 强力推荐 (主副图双重共振)")
    if res_resonance:
        for r in res_resonance: print(f"- {r}")
    else:
        print("- 今日暂无共振买点。")

    print("\n### 🟡 关注名单 (仅主图触底)")
    if res_yellow:
        for r in res_yellow[:30]: print(f"- {r}")
        if len(res_yellow) > 30: print(f"- ...等共计 {len(res_yellow)} 只")
    else:
        print("- 无。")

    print("\n" + "="*40)

if __name__ == "__main__":
    main()
