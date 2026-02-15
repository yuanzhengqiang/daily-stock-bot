import akshare as ak
import pandas as pd
import datetime
import time
import os
import requests

# --- 之前定义的 get_indices_stocks 和 get_signals 函数保持不变 ---
# (为了节省篇幅，这里略过，请确保你代码里有这两个函数)

def send_wechat(content):
    """
    通过 PushPlus 发送微信通知
    """
    token = os.environ.get('PUSHPLUS_TOKEN')
    if not token:
        print("未配置 PushPlus Token，跳过微信推送。")
        return

    url = "http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": f"📈 股票共振推荐 - {datetime.date.today()}",
        "content": content.replace("\n", "<br>"), # 微信换行处理
        "template": "html"
    }
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            print("微信推送成功！")
        else:
            print(f"微信推送失败: {response.text}")
    except Exception as e:
        print(f"微信推送出错: {e}")

# 这里是 main 函数的结尾修改版
def main():
    print(f"[{datetime.datetime.now()}] 🚀 启动指数扫描...")
    
    # 获取代码 (代码同上)
    stock_dict = get_indices_stocks()
    if not stock_dict: return

    res_resonance = []
    res_yellow = []
    
    # 扫描逻辑 (代码同上)
    all_codes = list(stock_dict.keys())
    for idx, code in enumerate(all_codes):
        try:
            time.sleep(0.2)
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            if df is None or df.empty: continue
            yellow, pink = get_signals(df)
            if yellow and pink:
                res_resonance.append(f"🔥 [共振] {code} - {stock_dict[code]}")
            elif yellow:
                res_yellow.append(f"🟡 [触底] {code} - {stock_dict[code]}")
        except: continue

    # 1. 构造报告内容
    report_header = f"📅 扫描日期: {datetime.date.today()}\n"
    report_header += f"✅ 范围: 上证50/沪深300/科创50\n\n"
    
    body = "### 💎 强力推荐 (双重共振)\n"
    if res_resonance:
        for r in res_resonance: body += f"{r}\n"
    else:
        body += "今日暂无共振信号。\n"

    body += "\n### 🟡 关注名单 (主图触底)\n"
    if res_yellow:
        for r in res_yellow[:20]: body += f"{r}\n"
        if len(res_yellow) > 20: body += f"...等共 {len(res_yellow)} 只\n"
    
    # 2. 打印到控制台 (为了让 GitHub Issue 也能收到)
    full_report = report_header + body
    print(full_report)

    # 3. 发送微信推送
    send_wechat(full_report)

# ... 别忘了调用 main()
if __name__ == "__main__":
    main()
