import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_base_dir() -> str:
    # tws package lives in <repo>/tws
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tws_handler(request: Any):
    """
    Cloud Function (HTTP) entrypoint.

    Flow:
      1. Run short-term/day-trading scan (writes current_trending.csv)
      2. If results exist, write them to BigQuery
      3. Send Telegram report to subscribers

    Environment variables expected:
      - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
      - GOOGLE_CLOUD_PROJECT or GCP_PROJECT
      - BQ_DATASET (optional, default: tws_dataset)
      - BQ_TABLE (optional, default: tws_trending)

    This function is intentionally simple and idempotent so it can be triggered
    by a Cloud Scheduler (HTTP) job each trading day.
    """
    # Lazy imports so the function cold-start is fast
    try:
        from .taiwan_trending import run_taiwan_trending
        from .telegram_notifier import send_stock_report
        from .bq_helper import BigQueryClient
    except Exception as e:
        logger.exception("Failed to import local modules: %s", e)
        return ("Server error", 500)

    base_dir = _get_base_dir()

    # 1) Run the trending scan
    try:
        run_taiwan_trending(base_dir)
    except Exception as e:
        logger.exception("run_taiwan_trending failed: %s", e)
        # Continue to attempt notifications (best-effort)

    # 2) If results exist, write them to BigQuery
    trending_path = os.path.join(base_dir, "current_trending.csv")
    if os.path.exists(trending_path):
        try:
            import pandas as pd

            df = pd.read_csv(trending_path)
            bq = BigQueryClient()
            bq.insert_trending(df)
        except Exception as e:
            logger.exception("Failed to write trending to BigQuery: %s", e)

    # 3) Send Telegram report (best-effort)
    try:
        send_stock_report(base_dir)
    except Exception as e:
        logger.exception("Failed to send telegram report: %s", e)

    return ("OK", 200)


def pubsub_tws(event, context):
    """
    Alternative Cloud Function entrypoint for Pub/Sub triggers.
    It simply forwards to tws_handler with a fake request object.
    """
    class _Req:
        pass

    return tws_handler(_Req())
