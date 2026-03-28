"""
Google Cloud Function entrypoint for the TWS daily pipeline.

Mirrors master_run.py exactly:
  Step 1 — sync_daily_data()           fetch TWSE top-20 + K-lines
  Step 2 — run_taiwan_trending()        apply signal filters
  Step 3 — update_mapping_with_trending() refresh fundamentals
  Step 4 — send_stock_report()          Telegram report
  Step 5 — insert_trending() to BigQuery (cloud-only)

Environment variables:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  GCP_PROJECT  or  GOOGLE_CLOUD_PROJECT
  BQ_DATASET   (default: tws_dataset)
  BQ_TABLE     (default: tws_trending)
  BQ_LOCATION  (default: US)

In Cloud Functions the code directory is read-only.  All file writes
(OHLCV CSVs, ticker lists, trending results) go to /tmp which is the
only writable filesystem available at runtime.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# In GCF the code is read-only; use /tmp for all runtime writes.
# Locally (or on a VM) use the repo root so data persists between runs.
def _base_dir() -> str:
    if os.getenv("K_SERVICE"):          # GCF / Cloud Run sets K_SERVICE
        return "/tmp/tws"
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tws_handler(request: Any):
    """
    HTTP Cloud Function entrypoint.

    Trigger via Cloud Scheduler:
      curl -X POST https://<region>-<project>.cloudfunctions.net/tws_handler
    """
    from .core import TaiwanStockEngine
    from .taiwan_trending import run_taiwan_trending
    from .telegram_notifier import send_stock_report
    from .bq_helper import BigQueryClient

    base_dir = _base_dir()
    os.makedirs(os.path.join(base_dir, "data", "ohlcv"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "data", "tickers"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "data", "company"), exist_ok=True)

    engine = TaiwanStockEngine(base_dir)

    # Step 1: sync TWSE top-20 + download K-lines
    try:
        engine.sync_daily_data()
    except Exception:
        logger.exception("Step 1 sync_daily_data failed")

    # Step 2: run signal filters
    try:
        run_taiwan_trending(base_dir)
    except Exception:
        logger.exception("Step 2 run_taiwan_trending failed")

    # Step 3: refresh fundamentals (ROE, PE, target price …)
    try:
        engine.update_mapping_with_trending()
    except Exception:
        logger.exception("Step 3 update_mapping_with_trending failed")

    # Step 4: send Telegram report
    try:
        send_stock_report(base_dir)
    except Exception:
        logger.exception("Step 4 send_stock_report failed")

    # Step 5 (cloud-only): persist results to BigQuery
    trending_path = os.path.join(base_dir, "current_trending.csv")
    if os.path.exists(trending_path):
        try:
            import pandas as pd
            df = pd.read_csv(trending_path)
            BigQueryClient().insert_trending(df)
        except Exception:
            logger.exception("Step 5 BigQuery insert failed")

    return ("OK", 200)
