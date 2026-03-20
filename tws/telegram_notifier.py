import os
import pandas as pd
import yfinance as yf
from tws.models import StockAI
from tws.utils import TelegramTool
from dotenv import load_dotenv

def clean_display(val, is_pct=False):
    if val is None or str(val) == "N/A" or pd.isna(val): return "N/A"
    try:
        f = float(val)
        if is_pct: f *= 100
        return f"{f:.2f}" + ("%" if is_pct else "")
    except: return "N/A"

def send_stock_report(base_dir):
    load_dotenv(os.path.join(base_dir, ".env"))
    mapping_file = os.path.join(base_dir, "data", "company", "company_mapping.csv")
    trending_file = os.path.join(base_dir, "current_trending.csv")
    
    mapping_df = pd.read_csv(mapping_file, dtype={'ticker': str})
    
    # 優先顯示今日熱門，若無則顯示 ROE 最強的前 5 檔
    if os.path.exists(trending_file):
        tickers = pd.read_csv(trending_file, dtype={'ticker': str})['ticker'].head(10).tolist()
    else:
        tickers = mapping_df[mapping_df['roe'] != 'N/A'].sort_values('roe', ascending=False)['ticker'].head(5).tolist()

    mapping = mapping_df.set_index('ticker').to_dict('index')
    tool = TelegramTool(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))
    report = f"🚀 **台股 AI 深度分析報告**\n"
    report += "--------------------------------\n"

    for t in tickers:
        info = mapping.get(t, {})
        # AI 預測
        try:
            hist = yf.download(f"{t}.TW", period="60d", progress=False)[['Close']]
            curr_p, pred_p = StockAI.predict_target(hist)
        except:
            curr_p, pred_p = "N/A", "N/A"

        # 🔴🟢 趨勢判定邏輯
        if curr_p != "N/A" and pred_p != "N/A":
            color = "🔴 (上漲預期)" if pred_p > curr_p else "🟢 (下跌預期)"
            price_line = f"${curr_p:.2f} | 🔮 目標: ${pred_p:.2f}"
        else:
            color = "⚪ (數據更新中)"
            price_line = "N/A"

        report += (
            f"🏢 **{info.get('name', '未知')}** ({t})\n"
            f"📂 產業: {info.get('industry', '未知')}\n"
            f"📊 **財務體質**\n"
            f" ├ ROE: {clean_display(info.get('roe'), True)} | 負債比: {clean_display(info.get('debt_to_equity'))}\n"
            f" └ 殖利率: {clean_display(info.get('dividend_yield'), True)} | PE: {clean_display(info.get('pe_ratio'))}\n"
            f"💡 **市場評價**\n"
            f" ├ 建議: {str(info.get('recommendation', 'N/A')).upper()}\n"
            f" └ 分析師目標價: ${clean_display(info.get('target_price'))}\n"
            f"🔮 **AI 預測 (Ledoit-Wolf)** {color}\n"
            f" └ 目前現價: {price_line}\n"
            f"--------------------------------\n"
        )
    
    tool.send_markdown(report)