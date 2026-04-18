"""
Signal list endpoints — reads current_trending.csv files.
In production (GCS_BUCKET set), files are downloaded from GCS.
In local dev, files are read from disk.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.config import settings

router = APIRouter(prefix="/api/signals", tags=["signals"])

_NUMERIC = ["score", "price", "RSI", "bias", "vol_ratio",
            "MA120", "MA20", "foreign_net", "f60"]


def _load_csv(path: Path) -> list[dict]:
    """Load CSV from local path or GCS (if GCS_BUCKET is configured)."""
    if settings.GCS_BUCKET:
        return _load_csv_gcs(path)
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, dtype={"ticker": str})
        return _clean_df(df)
    except Exception:
        return []


def _load_csv_gcs(local_path: Path) -> list[dict]:
    """Download CSV from GCS bucket, mirroring the local path structure."""
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(settings.GCS_BUCKET)
        # Convert absolute local path to relative GCS object name
        try:
            rel = local_path.relative_to(BASE_DIR)
        except ValueError:
            rel = local_path.name
        blob = bucket.blob(str(rel))
        if not blob.exists():
            return []
        content = blob.download_as_bytes()
        df = pd.read_csv(io.BytesIO(content), dtype={"ticker": str})
        return _clean_df(df)
    except Exception:
        return []


def _clean_df(df: pd.DataFrame) -> list[dict]:
    for col in _NUMERIC:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.where(pd.notna(df), None)
    return df.to_dict(orient="records")


# ── Existing endpoints ────────────────────────────────────────────────────────

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


# ── Search endpoint (used by mobile ticker search + watchlist add) ────────────

@router.get("/search")
def search_signals(
    q:      str  = Query(..., min_length=1, description="Ticker prefix or name substring"),
    market: str  = Query("all", description="TW | US | all"),
    limit:  int  = Query(20, ge=1, le=100),
):
    """
    Search signals by ticker prefix or name.
    Returns a unified list across TW and/or US data.
    """
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
                    "ticker":     row.get("ticker"),
                    "name":       row.get("name"),
                    "market":     "TW",
                    "score":      row.get("score"),
                    "RSI":        row.get("RSI"),
                    "price":      row.get("price"),
                    "bias":       row.get("bias"),
                    "is_signal":  bool(row.get("is_signal") or row.get("category") == "mean_reversion"),
                })

    if market.upper() in ("US", "ALL"):
        us_rows = _load_csv(BASE_DIR / "data_us" / "current_trending.csv")
        for row in us_rows:
            if _match(row):
                results.append({
                    "ticker":     row.get("ticker"),
                    "name":       row.get("name"),
                    "market":     "US",
                    "score":      row.get("score"),
                    "RSI":        row.get("RSI"),
                    "price":      row.get("price"),
                    "bias":       row.get("bias"),
                    "is_signal":  str(row.get("is_signal", "")).lower() == "true",
                })

    # Sort: exact ticker match first, then signals before non-signals
    results.sort(key=lambda r: (
        0 if str(r["ticker"] or "").upper() == q_upper else 1,
        0 if r["is_signal"] else 1,
    ))
    return results[:limit]
