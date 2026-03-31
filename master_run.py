import argparse
import os
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# 統一模組化導入
from tws.core import TaiwanStockEngine
from tws.taiwan_trending import run_taiwan_trending
from tws.telegram_notifier import send_stock_report, send_market_overview
from tws.prediction_tracker import resolve_outcomes, save_predictions, prediction_summary
from us.core import USStockEngine
from us.us_trending import run_us_trending

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def run_tws_pipeline():
    engine = TaiwanStockEngine(BASE_DIR)

    print(f"🚀 TWS 自動化流程啟動")

    # Step 1: 數據同步 — downloads fresh OHLCV so outcome resolution has today's prices
    engine.sync_daily_data()

    # Step 1b: Resolve previous predictions now that OHLCV files are up to date
    print("[Step 1b] 驗證過去預測結果...")
    resolve_outcomes(BASE_DIR)

    # Step 2: 執行趨勢篩選 (掃描 data/ohlcv 中的檔案)
    print("[Step 2] 執行台股趨勢分析...")
    run_taiwan_trending(BASE_DIR)

    # Step 2b: Record today's signals as pending predictions
    trending_file = os.path.join(BASE_DIR, "current_trending.csv")
    if os.path.exists(trending_file):
        signals_df = pd.read_csv(trending_file, dtype={"ticker": str})
        save_predictions(BASE_DIR, signals_df, market="TW")
        summary = prediction_summary(BASE_DIR)
        if summary.get("total", 0) > 0:
            print(
                f"[Tracker] TW win rate — open: {summary['win_rate_open']}%  "
                f"close: {summary['win_rate_close']}%  "
                f"({summary['total']} resolved, {summary.get('pending', 0)} pending)"
            )

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

    # Step 1b: Resolve US predictions with fresh OHLCV
    resolve_outcomes(BASE_DIR)

    # Step 2: Run trending analysis for US stocks
    print("[Step 2] Running US stock analysis...")
    run_us_trending(BASE_DIR)

    # Step 2b: Record US predictions
    us_trending_file = os.path.join(BASE_DIR, "data_us", "current_trending.csv")
    if os.path.exists(us_trending_file):
        us_signals_df = pd.read_csv(us_trending_file, dtype={"ticker": str})
        save_predictions(BASE_DIR, us_signals_df, market="US")

    # Step 3: Update US company fundamentals (PE, ROE, sector…)
    print("[Step 3] Updating US company fundamentals...")
    try:
        from us.company_mapper import update_us_mapping
        update_us_mapping(BASE_DIR, tickers or [])
    except Exception as e:
        print(f"[!] US company mapping failed (non-fatal): {e}")


def _tw_session() -> bool:
    """True during Taiwan trading window (08:00–14:00 TST, Mon–Fri).

    08:00 covers pre-market data prep; 14:00 gives 30 min after close (13:30)
    for EOD data to settle.
    """
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    return now.weekday() < 5 and 8 <= now.hour < 14


def _us_eod_ready() -> bool:
    """True after US market close (16:00 ET, Mon–Fri)."""
    now = datetime.now(ZoneInfo("America/New_York"))
    return now.weekday() < 5 and now.hour >= 16


def main():
    """
    Auto scheduling rules (UTC+8 = TST):
      08:00–14:00 TST Mon–Fri  →  TW only   (market active / just closed)
      all other weekday times  →  TW + US   (TW EOD settled, US post-close)
      weekends                 →  nothing   (use --market to override)

    Override: --market TW | US | all
    """
    parser = argparse.ArgumentParser(
        description="Stock analysis pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python master_run.py              # auto schedule (see rules above)\n"
            "  python master_run.py --market TW  # force TW pipeline only\n"
            "  python master_run.py --market US  # force US pipeline only\n"
            "  python master_run.py --market all # force both pipelines\n"
        ),
    )
    parser.add_argument(
        "--market", choices=["TW", "US", "all"], default="auto",
        help="Which pipeline to run (default: auto-detect from current time)",
    )
    args = parser.parse_args()

    now_tst = datetime.now(ZoneInfo("Asia/Taipei"))
    now_et  = datetime.now(ZoneInfo("America/New_York"))
    is_weekday = now_tst.weekday() < 5

    if args.market == "auto":
        if not is_weekday:
            print(f"⏳ Weekend ({now_tst.strftime('%A %H:%M TST')}) — no auto run.")
            print("   Use --market TW|US|all to force.")
            return
        if _tw_session():
            # 08:00–14:00 TST: TW trading window — TW pipeline only
            run_tw, run_us = True, False
        else:
            # Outside TW window (evenings / early morning): US pipeline only
            run_tw, run_us = False, True
    else:
        run_tw = args.market in ("TW", "all")
        run_us = args.market in ("US", "all")

    start_time = datetime.now()
    print(f"[Time] TST {now_tst.strftime('%H:%M')} | ET {now_et.strftime('%H:%M')}")
    if run_tw:
        print("🇹🇼 Running TW pipeline")
        run_tws_pipeline()
    if run_us:
        print("🇺🇸 Running US pipeline")
        run_us_pipeline()
    print(f"✅ 流程完成。耗時: {datetime.now() - start_time}")

if __name__ == "__main__":
    main()