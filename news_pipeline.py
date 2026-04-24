"""
News + PCR pipeline — Cloud Run Job entry point.

Runs every 30 min during market hours (TW: 09:00-13:30 TST, US: 09:30-17:00 ET).
Fetches news via Google News RSS, stores new items, snapshots PCR for US tickers,
and computes cross-related news links.

Usage:
    python news_pipeline.py
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from api.db import NewsItem, NewsPcrSnapshot, SessionLocal
from news.fetcher import fetch_broad_market_news, fetch_ticker_news
from news.pcr import fetch_pcr
from news.related import compute_related_ids, related_ids_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("news_pipeline")


def _collect_tickers() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (us_tickers, tw_tickers) as (ticker, market) pairs from signals CSVs."""
    import csv

    us_tickers: list[tuple[str, str]] = []
    tw_tickers: list[tuple[str, str]] = []

    # Try GCS first, fall back to local
    def _read_csv(local_path: str, gcs_key: str) -> list[dict]:
        try:
            from api.config import settings
            if settings.GCS_BUCKET:
                from google.cloud import storage
                import io
                client = storage.Client()
                blob = client.bucket(settings.GCS_BUCKET).blob(gcs_key)
                content = blob.download_as_text()
                return list(csv.DictReader(io.StringIO(content)))
        except Exception:
            pass
        full_path = BASE_DIR / local_path
        if full_path.exists():
            with open(full_path) as f:
                return list(csv.DictReader(f))
        return []

    for row in _read_csv("data_us/current_trending.csv", "data_us/current_trending.csv"):
        ticker = (row.get("ticker") or "").strip().upper()
        if ticker:
            us_tickers.append((ticker, "US"))

    for row in _read_csv("current_trending.csv", "current_trending.csv"):
        ticker = (row.get("ticker") or "").strip()
        if ticker:
            tw_tickers.append((ticker, "TW"))

    # Deduplicate
    us_tickers = list(dict.fromkeys(us_tickers))
    tw_tickers = list(dict.fromkeys(tw_tickers))

    logger.info("Collected %d US tickers, %d TW tickers", len(us_tickers), len(tw_tickers))
    return us_tickers, tw_tickers


def _insert_items(db, items: list[dict]) -> list[NewsItem]:
    """Insert news items, skipping duplicates. Returns list of inserted rows."""
    inserted: list[NewsItem] = []
    for item in items:
        existing = db.query(NewsItem).filter_by(external_id=item["external_id"]).first()
        if existing:
            continue
        row = NewsItem(**item)
        db.add(row)
        try:
            db.flush()
            inserted.append(row)
        except Exception:
            db.rollback()
    return inserted


def _snapshot_pcr(db, cutoff: datetime) -> int:
    """Snapshot PCR for all US NewsItems published within the last 12h."""
    now_utc = datetime.utcnow()
    us_items = (
        db.query(NewsItem)
        .filter(NewsItem.market == "US", NewsItem.published_at >= cutoff)
        .filter(NewsItem.ticker.isnot(None))
        .all()
    )

    # Dedupe: one PCR call per ticker per pipeline run
    seen_tickers: set[str] = set()
    snapshot_count = 0

    for item in us_items:
        ticker = item.ticker
        if ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)

        pcr_data = fetch_pcr(ticker)
        if not pcr_data:
            continue

        snapshot = NewsPcrSnapshot(
            news_item_id=item.id,
            ticker=ticker,
            snapshot_at=now_utc,
            put_volume=pcr_data["put_volume"],
            call_volume=pcr_data["call_volume"],
            pcr=pcr_data["pcr"],
            pcr_label=pcr_data["pcr_label"],
        )
        db.add(snapshot)
        snapshot_count += 1
        logger.info("  PCR %s: %.3f (%s)", ticker, pcr_data["pcr"], pcr_data["pcr_label"])

    return snapshot_count


def _update_related(db, cutoff: datetime) -> None:
    """Recompute related_ids for all items in the 12h window."""
    window_items = (
        db.query(NewsItem)
        .filter(NewsItem.published_at >= cutoff)
        .all()
    )
    if not window_items:
        return

    dicts = [{"id": it.id, "ticker": it.ticker, "headline": it.headline} for it in window_items]
    related_map = compute_related_ids(dicts)

    for item in window_items:
        related = related_map.get(item.id, [])
        item.related_ids = related_ids_json(related)

    logger.info("Cross-linked %d news items", len(window_items))


def main() -> None:
    cutoff = datetime.utcnow() - timedelta(hours=12)

    logger.info("=== news_pipeline start ===")
    us_tickers, tw_tickers = _collect_tickers()

    # 1. Gather all news
    all_items: list[dict] = []

    logger.info("Fetching broad market news...")
    all_items.extend(fetch_broad_market_news())

    logger.info("Fetching US ticker news (%d tickers)...", len(us_tickers))
    for ticker, market in us_tickers:
        all_items.extend(fetch_ticker_news(ticker, market))

    logger.info("Fetching TW ticker news (%d tickers)...", len(tw_tickers))
    for ticker, market in tw_tickers:
        all_items.extend(fetch_ticker_news(ticker, market))

    logger.info("Fetched %d raw news items", len(all_items))

    db = SessionLocal()
    try:
        # 2. Insert new items
        inserted = _insert_items(db, all_items)
        db.flush()
        logger.info("Inserted %d new items (%d duplicates skipped)",
                    len(inserted), len(all_items) - len(inserted))

        # 3. Snapshot PCR for US tickers
        logger.info("Snapshotting PCR for US tickers...")
        n_snapshots = _snapshot_pcr(db, cutoff)
        logger.info("PCR snapshots: %d", n_snapshots)

        # 4. Compute cross-related links
        logger.info("Computing related news links...")
        _update_related(db, cutoff)

        db.commit()
        logger.info("=== news_pipeline done ===")

    except Exception:
        db.rollback()
        logger.exception("Pipeline failed — rolled back")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
