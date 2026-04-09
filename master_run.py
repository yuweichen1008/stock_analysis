import argparse
import os
import requests
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

API_BASE = os.environ.get("ORACLE_API_BASE", "http://localhost:8000")


def _api_call(method: str, path: str, body: dict = None, timeout: int = 5):
    """Fire-and-forget API call. Non-fatal if the API server is unreachable."""
    try:
        url = f"{API_BASE}{path}"
        requests.request(method, url, json=body or {}, timeout=timeout)
    except Exception as e:
        print(f"[!] API call {path} failed (non-fatal): {e}")


def run_predict_step():
    """08:00 TST cron: compute Oracle prediction → Telegram → morning push."""
    print("🔮 [predict] 計算今日大盤預測...")
    from tws.index_tracker import compute_prediction, save_prediction
    from tws.telegram_notifier import send_market_prediction
    pred = compute_prediction(BASE_DIR)
    save_prediction(BASE_DIR, pred)
    send_market_prediction(BASE_DIR)
    print("[predict] 發送晨間推播 (Expo push + Telegram subscribers)...")
    _api_call("POST", "/api/notify/broadcast", {"type": "morning"})
    try:
        from tws.telegram_notifier import broadcast_to_subscribers
        n = broadcast_to_subscribers(BASE_DIR, "morning")
        if n:
            print(f"[predict] Telegram DM sent to {n} subscriber(s)")
    except Exception as e:
        print(f"[!] Telegram subscriber broadcast failed (non-fatal): {e}")
    print("✅ [predict] 完成")


def run_resolve_step():
    """14:05 TST cron: sync → resolve → settle bets → result push → signals → Telegram."""
    engine = TaiwanStockEngine(BASE_DIR)

    # Step 1: Download fresh OHLCV
    print("[resolve] 同步每日數據...")
    engine.sync_daily_data()

    # Step 1b: Resolve stock signal predictions
    print("[resolve] 驗證過去預測結果...")
    resolve_outcomes(BASE_DIR)

    # Step 1c: Resolve Oracle + settle bets + result push
    print("[resolve] 結算今日大盤預測...")
    try:
        from tws.index_tracker import resolve_today_prediction
        from tws.telegram_notifier import send_market_result
        if resolve_today_prediction(BASE_DIR):
            send_market_result(BASE_DIR)
            _api_call("POST", "/api/sandbox/settle", {})
            _api_call("POST", "/api/notify/broadcast", {"type": "result"})
            try:
                from tws.telegram_notifier import broadcast_to_subscribers
                n = broadcast_to_subscribers(BASE_DIR, "result")
                if n:
                    print(f"[resolve] Telegram DM sent to {n} subscriber(s)")
            except Exception as e:
                print(f"[!] Telegram subscriber broadcast failed (non-fatal): {e}")
    except Exception as e:
        print(f"[!] Oracle resolution failed (non-fatal): {e}")

    # Step 2: TW signal scan
    print("[resolve] 執行台股趨勢分析...")
    run_taiwan_trending(BASE_DIR)

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

    # Step 3: Update fundamentals
    print("[resolve] 同步 Yahoo Finance 深度數據...")
    engine.update_mapping_with_trending()

    # Step 4: Telegram reports
    print("[resolve] 發送市場總覽與熱力圖...")
    send_market_overview(BASE_DIR)
    print("[resolve] 執行 AI 分析並發送訊號股報告...")
    send_stock_report(BASE_DIR)

    print("✅ [resolve] 完成")


def run_tws_pipeline():
    """Legacy: full TW pipeline in one shot (kept for --market TW manual runs)."""
    print("🚀 TWS 自動化流程啟動")
    run_predict_step()
    run_resolve_step()

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

    # Step 4: Settle pending stock bets now that US market has closed
    print("[Step 4] Settling stock bets...")
    _api_call("POST", "/api/stocks/settle", {})

    # Step 5: Send US Telegram report (signals or watch-list)
    print("[Step 5] Sending US Telegram report...")
    try:
        from us.us_notifier import send_us_report
        send_us_report(BASE_DIR)
    except Exception as e:
        print(f"[!] US Telegram report failed (non-fatal): {e}")


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
    Cron-oriented steps (preferred):
      --step predict   08:00 TST Mon–Fri  →  Oracle predict + Telegram + morning push
      --step resolve   14:05 TST Mon–Fri  →  sync + resolve + settle + push + signals

    Legacy manual override:
      --market TW | US | all
    """
    parser = argparse.ArgumentParser(
        description="Stock analysis pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python master_run.py --step predict   # 08:00 cron\n"
            "  python master_run.py --step resolve   # 14:05 cron\n"
            "  python master_run.py --market US      # force US pipeline\n"
            "  python master_run.py --market all     # force both pipelines\n"
        ),
    )
    parser.add_argument(
        "--step", choices=["predict", "resolve"],
        help="Run a specific pipeline step (cron mode)",
    )
    parser.add_argument(
        "--market", choices=["TW", "US", "all"], default="auto",
        help="Which pipeline to run (default: auto-detect from current time)",
    )
    args = parser.parse_args()

    start_time = datetime.now()
    now_tst = datetime.now(ZoneInfo("Asia/Taipei"))
    now_et  = datetime.now(ZoneInfo("America/New_York"))
    print(f"[Time] TST {now_tst.strftime('%H:%M')} | ET {now_et.strftime('%H:%M')}")

    # --step takes priority over --market
    if args.step == "predict":
        run_predict_step()
        print(f"✅ 流程完成。耗時: {datetime.now() - start_time}")
        return
    if args.step == "resolve":
        run_resolve_step()
        print(f"✅ 流程完成。耗時: {datetime.now() - start_time}")
        return

    # Legacy --market logic
    is_weekday = now_tst.weekday() < 5
    if args.market == "auto":
        if not is_weekday:
            print(f"⏳ Weekend ({now_tst.strftime('%A %H:%M TST')}) — no auto run.")
            print("   Use --market TW|US|all or --step predict|resolve to force.")
            return
        if _tw_session():
            run_tw, run_us = True, False
        else:
            run_tw, run_us = False, True
    else:
        run_tw = args.market in ("TW", "all")
        run_us = args.market in ("US", "all")

    if run_tw:
        print("🇹🇼 Running TW pipeline")
        run_tws_pipeline()
    if run_us:
        print("🇺🇸 Running US pipeline")
        run_us_pipeline()
    print(f"✅ 流程完成。耗時: {datetime.now() - start_time}")

if __name__ == "__main__":
    main()