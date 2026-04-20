"""
Signal list endpoints — reads current_trending.csv files.
In production (GCS_BUCKET set), files are downloaded from GCS and cached in memory.
In local dev, files are read from disk.
"""
from __future__ import annotations

import io
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/signals", tags=["signals"])

_NUMERIC = ["score", "price", "RSI", "bias", "vol_ratio",
            "MA120", "MA20", "foreign_net", "f60"]

# ── GCS client singleton ───────────────────────────────────────────────────────
_gcs_client = None

def _get_gcs_client():
    global _gcs_client
    if _gcs_client is None:
        from google.cloud import storage
        _gcs_client = storage.Client()
    return _gcs_client


# ── In-memory CSV cache: {path_key: (data, loaded_at)} ───────────────────────
_csv_cache: dict[str, tuple[list, float]] = {}
_CSV_CACHE_TTL = 3600  # 1 hour — matches pipeline run frequency


def _load_csv(path: Path) -> list[dict]:
    """Load CSV with in-memory cache. Sources: GCS (prod) or local disk (dev)."""
    key = str(path)
    now = time.time()
    cached = _csv_cache.get(key)
    if cached and (now - cached[1]) < _CSV_CACHE_TTL:
        return cached[0]

    if settings.GCS_BUCKET:
        data = _load_csv_gcs(path)
    elif not path.exists():
        data = []
    else:
        try:
            df = pd.read_csv(path, dtype={"ticker": str})
            data = _clean_df(df)
        except Exception as e:
            logger.warning("Local CSV load failed for %s: %s", path, e)
            data = []

    _csv_cache[key] = (data, now)
    return data


def _load_csv_gcs(local_path: Path) -> list[dict]:
    """Download CSV from GCS bucket, mirroring the local path structure."""
    try:
        rel = local_path.relative_to(BASE_DIR)
    except ValueError:
        rel = local_path.name
    gcs_key = str(rel)

    try:
        client = _get_gcs_client()
        bucket = client.bucket(settings.GCS_BUCKET)
        blob = bucket.blob(gcs_key)
        if not blob.exists():
            logger.warning("GCS object not found: gs://%s/%s", settings.GCS_BUCKET, gcs_key)
            return []
        content = blob.download_as_bytes()
        df = pd.read_csv(io.BytesIO(content), dtype={"ticker": str})
        return _clean_df(df)
    except Exception as e:
        logger.warning("GCS CSV load failed for %s: %s", gcs_key, e)
        return []


def _clean_df(df: pd.DataFrame) -> list[dict]:
    for col in _NUMERIC:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.where(pd.notna(df), None)
    return df.to_dict(orient="records")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/tw")
def get_tw_signals():
    """Today's Taiwan mean-reversion signals."""
    path = BASE_DIR / "current_trending.csv"
    rows = _load_csv(path)
    signals   = [r for r in rows if r.get("is_signal") or r.get("category") == "mean_reversion"]
    watchlist = [r for r in rows if r.get("category") == "high_value_moat"]
    return {"signals": signals, "watchlist": watchlist, "total": len(rows)}


@router.get("/us")
def get_us_signals():
    """Today's US mean-reversion signals and finviz watchlist."""
    path = BASE_DIR / "data_us" / "current_trending.csv"
    rows = _load_csv(path)
    signals   = [r for r in rows if str(r.get("is_signal", "")).lower() == "true"]
    watchlist = [r for r in rows if r.get("category") == "finviz_watch"]
    return {"signals": signals, "watchlist": watchlist, "total": len(rows)}


@router.post("/cache/invalidate")
def invalidate_cache():
    """Clear signal CSV cache (forces reload on next request)."""
    _csv_cache.clear()
    return {"cleared": True}


# ── Search endpoint (used by mobile ticker search + watchlist add) ─────────────

@router.get("/search")
def search_signals(
    q:      str  = Query(..., min_length=1, description="Ticker prefix or name substring"),
    market: str  = Query("all", description="TW | US | all"),
    limit:  int  = Query(20, ge=1, le=100),
):
    """Search signals by ticker prefix or name. Returns unified list across TW and/or US."""
    q_upper = q.upper()
    results = []

    def _match(row: dict) -> bool:
        ticker = str(row.get("ticker", "")).upper()
        name   = str(row.get("name",   "")).upper()
        return ticker.startswith(q_upper) or q_upper in name

    if market.upper() in ("TW", "ALL"):
        tw_rows = _load_csv(BASE_DIR / "current_trending.csv")
        for row in tw_rows:
            if _match(row):
                results.append({
                    "ticker":    row.get("ticker"),
                    "name":      row.get("name"),
                    "market":    "TW",
                    "score":     row.get("score"),
                    "RSI":       row.get("RSI"),
                    "price":     row.get("price"),
                    "bias":      row.get("bias"),
                    "is_signal": bool(row.get("is_signal") or row.get("category") == "mean_reversion"),
                })

    if market.upper() in ("US", "ALL"):
        us_rows = _load_csv(BASE_DIR / "data_us" / "current_trending.csv")
        for row in us_rows:
            if _match(row):
                results.append({
                    "ticker":    row.get("ticker"),
                    "name":      row.get("name"),
                    "market":    "US",
                    "score":     row.get("score"),
                    "RSI":       row.get("RSI"),
                    "price":     row.get("price"),
                    "bias":      row.get("bias"),
                    "is_signal": str(row.get("is_signal", "")).lower() == "true",
                })

    results.sort(key=lambda r: (
        0 if str(r["ticker"] or "").upper() == q_upper else 1,
        0 if r["is_signal"] else 1,
    ))
    return results[:limit]
