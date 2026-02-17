import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests

def get_indices_stocks():
    """
    获取上证50、沪深300、中证1000、科创50 (A股) 
    以及 恒生科技 (港股) 的成分股并去重
    """
    # A股指数映射
    a_indices = {
        "上证50": "000016",
        "沪深300": "000300",
        "中证1000": "000852",
        "科创50": "000688"
    }
    all_stocks = {} # {代码: [名称, 类型]}

    print("正在抓取各指数成分股列表...")
    
    # 1. 抓取 A 股成分股
    for name, code in a_indices.items():
        try:
            print(f"正在读取 {name}...")
            df = ak.index_stock_cons(symbol=code)
            if not df.empty:
                for _, row in df.iterrows():
                    all_stocks[row['品种代码']] = [row['品种名称'], 'A']
            time.sleep(0.5)
        except Exception as e:
            print(f"获取 {name} 失败: {e}")

    # 2. 抓取 恒生科技 (港股)
    try:
        print("正在读取 恒生科技 (港股)...")
        # 恒生科技成分股接口
        df_hk = ak.stock_hk_index_daily_sina(symbol="HSTECH") 
        # 注意：这里为了稳定，通常建议手动维护或通过实时接口拿到代码
        # 备用：直接抓取港股实时行情中的前30-50只核心科技股
        hk_spot = ak.stock_hk_spot_em()
        # 简单处理：选取恒生科技相关的核心标的（演示逻辑）
        # 如果需要精准成分股，此处可根据 AkShare 更新后的接口调整
        count = 0
        for _, row in hk_spot.head(80).iterrows(): # 扫描港股前80只活跃股
            if "科技" in row['名称'] or row['代码'] in ['00700', '03690', '09988', '09888', '01810']:
                all_stocks[row['代码']] = [row['名称'], 'HK']
                count += 1
        print(f"港股相关标的抓取完成，共计 {count} 只。")
    except Exception as e:
        print(f"获取港股列表失败: {e}")
            
    return all_stocks

def calculate_logic(df):
    """三周期核心指标计算逻辑"""
    try:
        if len(df) < 65: return False, False
        # 统一列名（处理港股和A股列名差异）
        if '收盘' in df.columns:
            close, high, low = df['收盘'], df['最高'], df['最低']
        else:
            close, high, low = df['close'], df['high'], df['low']
            
        close, high, low = close.astype(float), high.astype(float), low.astype(float)

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

def get_history(code, period, stock_type):
    """根据股票类型选择不同接口获取数据"""
    if stock_type == 'A':
        return ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
    else:
        # 港股接口，默认返回最近的数据
        return ak.stock_hk_hist(symbol=code, period=period, adjust="qfq")

def send_wechat(content):
    token = os.environ.get('PUSHPLUS_TOKEN')
    if not token: return
    url = "http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": f"🌟 股票多指数共振报告 - {datetime.date.today()}",
        "content": content.replace("\n", "<br>"),
        "template": "html"
    }
    requests.post(url, json=data)

def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动 A+H 多指数多周期扫描...")
    stock_dict = get_indices_stocks()
    if not stock_dict: return

    all_codes = list(stock_dict.keys())
    total = len(all_codes)
    print(f"去重后扫描总量: {total} 只。预计耗时 20-40 分钟。")
    
    triple_match, double_match, daily_only = [], [], []

    for idx, code in enumerate(all_codes):
        stock_name = stock_dict[code][0]
        stock_type = stock_dict[code][1]
        
        if (idx + 1) % 100 == 0: print(f"进度: {idx+1}/{total}...")
        
        try:
            # 1. 检查日线
            df_d = get_history(code, "daily", stock_type)
            d_yellow, d_pink = calculate_logic(df_d)
            if not (d_yellow and d_pink): continue
            
            # 2. 检查周线
            time.sleep(0.15)
            df_w = get_history(code, "weekly", stock_type)
            w_yellow, w_pink = calculate_logic(df_w)
            
            stock_info = f"{code}-{stock_name}({stock_type})"
            
            if w_yellow and w_pink:
                # 3. 检查月线
                time.sleep(0.15)
                df_m = get_history(code, "monthly", stock_type)
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

    # 获取数据截止日期
    try:
        sample_df = ak.stock_zh_a_hist(symbol="000300", period="daily")
        last_date = sample_df.iloc[-1]['日期']
    except: last_date = "未知"

    # 构造微信报告
    report = f"📅 报告日期: {datetime.date.today()}\n"
    report += f"📊 数据截止: {last_date} (非交易日不更新)\n"
    report += f"🔍 范围: 50/300/1000/科50/港科\n"
    report += f"✅ 扫描总量: {total} 只\n\n"
    
    report += "### 🌟 终极推荐 (日+周+月)\n"
    report += "\n".join([f"- {s}" for s in triple_match]) if triple_match else "今日无。\n"
    
    report += "\n### 💎 强化推荐 (日+周)\n"
    report += "\n".join([f"- {s}" for s in double_match]) if double_match else "今日无。\n"
    
    report += "\n### 🟢 标准关注 (日线)\n"
    if daily_only:
        report += "\n".join([f"- {s}" for s in daily_only[:20]])
        if len(daily_only) > 20: report += f"\n...等共 {len(daily_only)} 只"
    else: report += "无。"

    print(report)
    send_wechat(report)

if __name__ == "__main__":
    main()
