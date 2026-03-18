import os
import pandas as pd
import requests
from dotenv import load_dotenv #
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Get parameterized values
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Path parameters
TRENDING_FILE = "current_trending.csv"
MAPPING_FILE = "data/company/company_mapping.csv"

def send_telegram_msg(text):
    if not TOKEN or not CHAT_ID:
        print("[X] Error: Telegram credentials not found in .env")
        return False
        
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except:
        return False

def get_latest_news(ticker, name):
    """抓取 Google News 該股票的最新標題"""
    try:
        search_query = f"{ticker} {name}"
        url = f"https://news.google.com/rss/search?q={search_query}+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.content)
        # 取得第一條新聞標題
        for item in root.findall('.//item'):
            return item.find('title').text.split(' - ')[0] # 移除媒體名稱
    except:
        return "暫無今日即時新聞"
    return "暫無今日即時新聞"

def send_telegram_top10():
    """發送 Top 10 並附帶產業別與新聞快訊"""
    if not os.path.exists(TRENDING_FILE) or not os.path.exists(MAPPING_FILE):
        print("缺少數據文件，請先運行 fetch 腳本")
        return

    # 載入數據
    df = pd.read_csv(TRENDING_FILE, dtype={'ticker': str}).head(10)
    mapping = pd.read_csv(MAPPING_FILE, dtype={'ticker': str}).set_index('ticker').to_dict('index')

    header = f"🚀 **台股強勢股 Top 10 & 漲因快訊** ({datetime.now().strftime('%Y-%m-%d')})\n\n"
    body = header

    for _, row in df.iterrows():
        t = row['ticker'].zfill(4)
        info = mapping.get(t, {})
        name = info.get('name', '未知名稱')
        industry = info.get('industry', '未知產業')
        news = get_latest_news(t, name)

        body += (
            f"🏢 **{name}** (`{t}`)\n"
            f"📂 **產業**: {industry} | **PE**: {info.get('pe_ratio', 'N/A')}\n"
            f"💰 **現價**: ${row['price']:.2f} (MA5/20 黃金交叉)\n"
            f"📰 **快訊**: {news}\n"
            f"────────────────────\n"
        )

    # 投資紀律提醒
    body += "\n💡 **紀律**: 只做上升通道，跌破生死線(120MA)堅決不看！"

    # 發送訊息
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                  json={"chat_id": CHAT_ID, "text": body, "parse_mode": "Markdown"})
    print("[✓] Top 10 快訊報表已送出。")

if __name__ == "__main__":
    send_telegram_top10()