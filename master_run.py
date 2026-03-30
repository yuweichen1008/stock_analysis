import os
from datetime import datetime
from dotenv import load_dotenv

# 統一模組化導入
from tws.core import TaiwanStockEngine
from tws.taiwan_trending import run_taiwan_trending
from tws.telegram_notifier import send_stock_report, send_market_overview
from us.core import USStockEngine
from us.us_trending import run_us_trending

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def run_tws_pipeline():
    engine = TaiwanStockEngine(BASE_DIR)

    print(f"🚀 TWS 自動化流程啟動")

    # Step 1: 數據同步 (取代原本被刪除的 init_history_crawler)
    # 它會抓取今日 Top 20 並下載 K 線，存入 data/ohlcv
    engine.sync_daily_data()

    # Step 2: 執行趨勢篩選 (掃描 data/ohlcv 中的檔案)
    print("[Step 2] 執行台股趨勢分析...")
    run_taiwan_trending(BASE_DIR)

    # Step 3: 更新深度金融數據 (ROE, PE, 目標價...)
    print("[Step 3] 同步 Yahoo Finance 深度數據 (含過期檢查)...")
    engine.update_mapping_with_trending()

    # Step 4a: 全市場總覽 (漲跌停 + 產業排行 + 大盤熱力圖)
    print("[Step 4a] 發送市場總覽與熱力圖...")
    send_market_overview(BASE_DIR)

    # Step 4b: 訊號股個別分析報告
    print("[Step 4b] 執行 AI 分析並發送訊號股報告...")
    send_stock_report(BASE_DIR)

def run_us_pipeline():
    print(f"🚀 US 自動化流程啟動")
    us_engine = USStockEngine(BASE_DIR)

    # Step 1: Sync S&P 500 tickers and download historical data
    print("[Step 1] Syncing US stock data...")
    tickers = us_engine.sync_daily_data()

    # Step 2: Run trending analysis for US stocks
    print("[Step 2] Running US stock analysis...")
    run_us_trending(BASE_DIR)

    # Step 3: Update US company fundamentals (PE, ROE, sector…)
    print("[Step 3] Updating US company fundamentals...")
    try:
        from us.company_mapper import update_us_mapping
        update_us_mapping(BASE_DIR, tickers or [])
    except Exception as e:
        print(f"[!] US company mapping failed (non-fatal): {e}")


def main():
    start_time = datetime.now()
    
    run_tws_pipeline()
    run_us_pipeline()

    print(f"✅ 流程完成。耗時: {datetime.now() - start_time}")

if __name__ == "__main__":
    main()