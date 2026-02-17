import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests

def get_a_indices_stocks():
    """获取上证50、沪深300、中证1000、科创50成分股并去重"""
    indices = {
        "上证50": "000016",
        "沪深300": "000300",
        "中证1000": "000852",
        "科创50": "000688"
    }
    all_stocks = {}
    print("正在获取 A 股核心指数成分股列表...")
    for name, code in indices.items():
        try:
            print(f"正在读取 {name}...")
            df = ak.index_stock_cons(symbol=code)
            if not df.empty:
                for _, row in df.iterrows():
                    # 建立 代码 -> 名称 的映射
                    all_stocks[row['品种代码']] = row['品种名称']
            time.sleep(0.5)
        except Exception as e:
            print(f"获取 {name} 失败: {e}")
    return all_stocks

def calculate_logic(df):
    """
    核心选股逻辑：金钻趋势线 + 副图粉色信号
    兼容新股：只要数据超过30条就尝试计算
    """
    try:
        if df is None or len(df) < 30: 
            return False
        
        # 确保列名正确（兼容处理）
        m = {'收盘': 'close', '最高': 'high', '最低': 'low', '日期': 'date'}
        df = df.rename(columns=m)
        
        close = df['close'].astype(float)
        high = df['high'].astype(float)
        low = df['low'].astype(float)

        def ema(s, n): return s.ewm(span=n, adjust=False).mean()
        def sma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()

        # 1. 主图金钻趋势线 (双重 EMA)
        ma_h = ema(ema(high, 25), 25)
        ma_l = ema(ema(low, 25), 25)
        trend_line = ma_l - (ma_h - ma_l)
        
        # 2. 副图指标
        # 散户线 (60日高低点，若数据不足则用全部)
        window_60 = min(len(df), 60)
        hhv_60 = high.rolling(window=window_60).max()
        llv_60 = low.rolling(window=window_60).min()
        retail = 100 * (hhv_60 - close) / (hhv_60 - llv_60)
        
        # 价格趋势 (27日)
        window_27 = min(len(df), 27)
        stoch = 100 * (close - low.rolling(window=window_27).min()) / (high.rolling(window=window_27).max() - low.rolling(window=window_27).min())
        sma_5 = sma(stoch, 5)
        price_trend = 3 * sma_5 - 2 * sma(sma_5, 3)

        # 判定条件：
        # 价格低于趋势线 且 (散户线在超卖高位 或 趋势指标在低位)
        # 判断最近 2 根 K 线（包含今天和昨天），增加容错
        cond = (low <= trend_line) & ((retail > 85) | (price_trend < 15))
        
        return cond.tail(2).any()
    except:
        return False

def send_wechat(content):
    """通过 PushPlus 推送"""
    token = os.environ.get('PUSHPLUS_TOKEN')
    if not token: 
        return
    url = "http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": f"📈 A股多周期扫描报告 - {datetime.date.today()}",
        "content": content.replace("\n", "<br>"),
        "template": "html"
    }
    requests.post(url, json=data)

def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动 A 股精选池深度扫描...")
    stock_dict = get_a_indices_stocks()
    if not stock_dict: return

    all_codes = list(stock_dict.keys())
    total = len(all_codes)
    print(f"去重后共计 {total} 只股票。开始扫描...")

    triple_list, double_list, daily_list = [], [], []
    last_date = "未知"

    for idx, code in enumerate(all_codes):
        if (idx + 1) % 200 == 0:
            print(f"进度: {idx+1}/{total}...")

        try:
            # 1. 检查日线
            df_d = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if df_d is None or df_d.empty: continue
            
            if last_date == "未知":
                last_date = df_d.iloc[-1]['日期']

            if calculate_logic(df_d):
                tag = f"{code}-{stock_dict[code]}"
                
                # 2. 日线符合，检查周线
                time.sleep(0.1)
                df_w = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
                if calculate_logic(df_w):
                    # 3. 周线符合，检查月线
                    df_m = ak.stock_zh_a_hist(symbol=code, period="monthly", adjust="qfq")
                    if calculate_logic(df_m):
                        triple_list.append(tag)
                    else:
                        double_list.append(tag)
                else:
                    daily_list.append(tag)
        except:
            continue

    # 构造报告
    report = f"📅 报告日期: {datetime.date.today()}\n"
    report += f"📊 数据截止: {last_date}\n"
    report += f"✅ 扫描范围: A股核心指数 ({total}只)\n\n"
    
    report += "### 🌟 [日周月] 三期共振 (罕见大底)\n"
    report += "\n".join([f"- {s}" for s in triple_list]) if triple_list else "今日无。\n"
    
    report += "\n### 💎 [日周] 共振 (强化买点)\n"
    report += "\n".join([f"- {s}" for s in double_list]) if double_list else "今日无。\n"
    
    report += "\n### 🟢 [日线] 符合 (基础信号)\n"
    if daily_list:
        report += "\n".join([f"- {s}" for s in daily_list[:30]])
        if len(daily_list) > 30: report += f"\n...等共 {len(daily_list)} 只"
    else:
        report += "今日无。"

    print(report)
    send_wechat(report)

if __name__ == "__main__":
    main()
