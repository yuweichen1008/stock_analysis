import os
from datetime import datetime
from dotenv import load_dotenv

# 統一模組化導入
from tws.core import TaiwanStockEngine
from tws.taiwan_trending import run_taiwan_trending
from tws.telegram_notifier import send_stock_report, send_market_overview

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def main():
    start_time = datetime.now()
    engine = TaiwanStockEngine(BASE_DIR)

    print(f"🚀 TWS 自動化流程啟動: {start_time}")

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

    print(f"✅ 流程完成。耗時: {datetime.now() - start_time}")

if __name__ == "__main__":
    main()