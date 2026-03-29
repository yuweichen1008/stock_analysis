import os
import logging
import pandas as pd
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from tws.models import StockAI
from tws.core import TaiwanStockEngine
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 基礎設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# 載入數據引擎與 Mapping
engine = TaiwanStockEngine(BASE_DIR)
MAPPING_FILE = os.path.join(BASE_DIR, "data/company/company_mapping.csv")

# Lazy broker manager — instantiated on first broker command
_broker_manager = None


def _get_broker_manager():
    """Return a connected BrokerManager, instantiated on first use."""
    global _broker_manager
    if _broker_manager is None:
        from brokers.manager import BrokerManager
        _broker_manager = BrokerManager()
        _broker_manager.connect_all()
    return _broker_manager

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


# ---------------------------------------------------------------------------
# Broker commands
# ---------------------------------------------------------------------------

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/balance — Show account cash and net value across all connected brokers."""
    await update.message.reply_text("⏳ Fetching account balance…")
    try:
        mgr  = _get_broker_manager()
        text = mgr.balance_report()
    except Exception as e:
        logger.exception("cmd_balance error: %s", e)
        text = "⚠️ Failed to fetch balance. Check broker connections."
    await update.message.reply_text(text, parse_mode='Markdown')


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/positions — List all open holdings across connected brokers."""
    await update.message.reply_text("⏳ Fetching positions…")
    try:
        mgr  = _get_broker_manager()
        text = mgr.positions_report()
    except Exception as e:
        logger.exception("cmd_positions error: %s", e)
        text = "⚠️ Failed to fetch positions. Check broker connections."
    await update.message.reply_text(text, parse_mode='Markdown')


async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/orders — Show orders from the last 7 days across connected brokers."""
    await update.message.reply_text("⏳ Fetching recent orders…")
    try:
        days = 7
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError:
                pass
        mgr  = _get_broker_manager()
        text = mgr.orders_report(days=days)
    except Exception as e:
        logger.exception("cmd_orders error: %s", e)
        text = "⚠️ Failed to fetch orders. Check broker connections."
    await update.message.reply_text(text, parse_mode='Markdown')


if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("balance",   cmd_balance))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("orders",    cmd_orders))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🤖 Telegram Bot 互動模式啟動中…")
    print("Commands: /balance  /positions  /orders [days]  or send a 4-digit stock code")
    app.run_polling()