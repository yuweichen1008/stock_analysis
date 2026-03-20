import requests
import xml.etree.ElementTree as ET
import os

class TelegramTool:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send_markdown(self, text):
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            requests.post(self.api_url, json=payload, timeout=10)
        except Exception as e:
            print(f"Telegram send error: {e}")

    @staticmethod
    def fetch_google_news(ticker, name):
        query = f"{ticker} {name} 股價"
        url = f"https://news.google.com/rss/search?q={query}+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        try:
            res = requests.get(url, timeout=5)
            root = ET.fromstring(res.content)
            items = root.findall('.//item')
            if items:
                return items[0].find('title').text.split(' - ')[0]
        except:
            pass
        return "今日暫無重大新聞"