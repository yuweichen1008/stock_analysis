import os
import pandas as pd
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from tws.models import StockAI
from tws.core import TaiwanStockEngine
from dotenv import load_dotenv

# 基礎設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# 載入數據引擎與 Mapping
engine = TaiwanStockEngine(BASE_DIR)
MAPPING_FILE = os.path.join(BASE_DIR, "data/company/company_mapping.csv")

def get_stock_detail(ticker):
    """查詢本地 Mapping 與即時預測"""
    if not os.path.exists(MAPPING_FILE):
        return "⚠️ 資料庫尚未建立，請先執行 master_run.py"
    
    df = pd.read_csv(MAPPING_FILE, dtype={'ticker': str})
    info = df[df['ticker'] == ticker.zfill(4)]
    
    if info.empty:
        return f"🔍 找不到 {ticker} 的基本面資料。但正在嘗試即時預測..."

    row = info.iloc[0]
    # 即時抓取價格做 AI 預測
    try:
        hist = yf.download(f"{ticker}.TW", period="60d", progress=False)[['Close']]
        curr_p, pred_p = StockAI.predict_target(hist)
        color = "🔴 (預期上漲)" if pred_p > curr_p else "🟢 (預期下跌)"
    except:
        curr_p, pred_p, color = "N/A", "N/A", "⚪"

    return (
        f"🏢 **{row['name']}** ({ticker})\n"
        f"📂 產業: {row['industry']}\n"
        f"📊 **財務體質**\n"
        f" ├ ROE: {row['roe']} | PE: {row['pe_ratio']}\n"
        f" └ 殖利率: {row['dividend_yield']} | 負債比: {row['debt_to_equity']}\n"
        f"🔮 **AI 預測** {color}\n"
        f" └ 現價: ${curr_p} | 5日目標: ${pred_p}\n"
    )

# --- 指令處理 ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 **TWS AI 助理已上線**\n請直接輸入股票代碼 (例如: 2330) 來獲取即時分析。")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.isdigit() and len(text) >= 4:
        await update.message.reply_text(f"⏳ 正在分析 {text}...")
        response = get_stock_detail(text)
        await update.message.reply_text(response, parse_mode='Markdown')
    else:
        await update.message.reply_text("請輸入正確的 4 位數股票代碼。")

if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("🤖 Telegram Bot 互動模式啟動中...")
    app.run_polling()