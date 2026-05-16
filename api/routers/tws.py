"""
TWS (Taiwan Stock) Management API — enriched stock universe for the web dashboard.

Merges three data sources:
  1. universe_snapshot.csv   — scanned tickers with live technical metrics
  2. current_trending.csv    — signal tickers (mean_reversion / high_value_moat)
  3. company_mapping.csv     — all listed TW stocks with name, industry, fundamentals

GET /api/tws/universe          — full enriched stock list (searchable, filterable)
GET /api/tws/stock/{ticker}    — single stock detail
"""
from __future__ import annotations

import io
import logging
import math
import sys
import time
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Query

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tws", tags=["tws"])

_NUMERIC_COLS = [
    "score", "price", "MA120", "MA20", "RSI", "bias",
    "vol_ratio", "foreign_net", "f5", "f20", "f60", "f_zscore",
    "short_interest", "news_sentiment",
]

_cache: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 1800.0  # 30 min


# ── Data loading ───────────────────────────────────────────────────────────────

def _read_csv_local(path: Path, ticker_dtype: bool = True) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        kw = {"dtype": {"ticker": str}} if ticker_dtype else {}
        df = pd.read_csv(path, **kw)
        df.columns = [c.lstrip("﻿") for c in df.columns]  # strip BOM
        return df
    except Exception as e:
        logger.warning("CSV read failed %s: %s", path, e)
        return None


def _read_csv_gcs(local_path: Path) -> pd.DataFrame | None:
    try:
        from google.cloud import storage
        client = storage.Client()
        rel = local_path.relative_to(BASE_DIR)
        blob = client.bucket(settings.GCS_BUCKET).blob(str(rel))
        if not blob.exists():
            return None
        content = blob.download_as_bytes()
        df = pd.read_csv(io.BytesIO(content), dtype={"ticker": str})
        df.columns = [c.lstrip("﻿") for c in df.columns]
        return df
    except Exception as e:
        logger.warning("GCS read failed: %s", e)
        return None


def _read_csv(path: Path) -> pd.DataFrame | None:
    if settings.GCS_BUCKET:
        return _read_csv_gcs(path)
    return _read_csv_local(path)


def _safe(v) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return None


def _build_universe() -> dict:
    """Merge snapshot + trending + mapping into enriched stock list."""
    # ── Load universe snapshot (technical metrics) ─────────────────────────
    snap_path = BASE_DIR / "data" / "company" / "universe_snapshot.csv"
    snap_df = _read_csv(snap_path)

    # ── Load current trending (signal tickers) ─────────────────────────────
    trend_path = BASE_DIR / "current_trending.csv"
    trend_df = _read_csv(trend_path)

    # ── Load company mapping (name + fundamentals) ──────────────────────────
    map_path = BASE_DIR / "data" / "company" / "company_mapping.csv"
    map_df = _read_csv_local(map_path, ticker_dtype=True)

    # ── Build lookup dicts ─────────────────────────────────────────────────
    name_lookup: dict[str, dict] = {}
    if map_df is not None:
        for _, row in map_df.iterrows():
            t = str(row.get("ticker", "")).strip()
            name_lookup[t] = {
                "name":           row.get("name"),
                "industry":       row.get("industry"),
                "pe_ratio":       str(row.get("pe_ratio", "")) or None,
                "roe":            str(row.get("roe", "")) or None,
                "dividend_yield": str(row.get("dividend_yield", "")) or None,
                "debt_to_equity": str(row.get("debt_to_equity", "")) or None,
            }

    signal_lookup: dict[str, dict] = {}
    if trend_df is not None:
        for col in _NUMERIC_COLS:
            if col in trend_df.columns:
                trend_df[col] = pd.to_numeric(trend_df[col], errors="coerce")
        for _, row in trend_df.iterrows():
            t = str(row.get("ticker", "")).strip()
            signal_lookup[t] = row.to_dict()

    # ── Merge rows ─────────────────────────────────────────────────────────
    rows: list[dict] = []
    seen: set[str] = set()
    last_updated: str | None = None

    def _make_row(ticker: str, snap_row: dict | None, sig_row: dict | None) -> dict:
        base = sig_row or snap_row or {}
        meta = name_lookup.get(ticker, {})

        is_signal = (
            bool(base.get("is_signal"))
            or str(base.get("is_signal", "")).lower() == "true"
            or base.get("category") in ("mean_reversion",)
        )
        category = base.get("category") or ""
        if not category and is_signal:
            category = "mean_reversion"

        nd = snap_row or base
        return {
            "ticker":         ticker,
            "name":           meta.get("name") or base.get("name"),
            "industry":       meta.get("industry") or base.get("industry"),
            "pe_ratio":       meta.get("pe_ratio"),
            "roe":            meta.get("roe"),
            "dividend_yield": meta.get("dividend_yield"),
            "debt_to_equity": meta.get("debt_to_equity"),
            "is_signal":      is_signal,
            "category":       category,
            "score":          _safe(nd.get("score")),
            "price":          _safe(nd.get("price")),
            "MA120":          _safe(nd.get("MA120")),
            "MA20":           _safe(nd.get("MA20")),
            "RSI":            _safe(nd.get("RSI")),
            "bias":           _safe(nd.get("bias")),
            "vol_ratio":      _safe(nd.get("vol_ratio")),
            "foreign_net":    _safe(nd.get("foreign_net")),
            "f5":             _safe(nd.get("f5")),
            "f20":            _safe(nd.get("f20")),
            "f60":            _safe(nd.get("f60")),
            "f_zscore":       _safe(nd.get("f_zscore")),
            "short_interest": _safe(nd.get("short_interest")),
            "news_sentiment": _safe(nd.get("news_sentiment")),
            "last_date":      str(nd.get("last_date", "")) or None,
        }

    # From universe snapshot
    if snap_df is not None:
        for col in _NUMERIC_COLS:
            if col in snap_df.columns:
                snap_df[col] = pd.to_numeric(snap_df[col], errors="coerce")
        for _, srow in snap_df.iterrows():
            ticker = str(srow.get("ticker", "")).strip()
            if not ticker:
                continue
            seen.add(ticker)
            sig = signal_lookup.get(ticker)
            row = _make_row(ticker, srow.to_dict(), sig)
            rows.append(row)
            if row["last_date"]:
                last_updated = row["last_date"]

    # Tickers from trending CSV not yet in snapshot
    for ticker, sig_row in signal_lookup.items():
        if ticker in seen:
            continue
        row = _make_row(ticker, None, sig_row)
        rows.append(row)
        if row["last_date"]:
            last_updated = row["last_date"]

    # Sort: signals first, then high-value, then by score desc
    def _sort_key(r: dict):
        cat = r.get("category") or ""
        return (
            0 if cat == "mean_reversion" else
            1 if cat == "high_value_moat" else 2,
            -(r.get("score") or 0),
        )

    rows.sort(key=_sort_key)

    signal_count    = sum(1 for r in rows if r["is_signal"])
    high_value_count = sum(1 for r in rows if r.get("category") == "high_value_moat")
    sectors = sorted({r["industry"] for r in rows if r.get("industry") and r["industry"] != "N/A"})

    return {
        "stocks":           rows,
        "total":            len(rows),
        "signal_count":     signal_count,
        "high_value_count": high_value_count,
        "last_updated":     last_updated,
        "sectors":          sectors,
    }


def _get_universe() -> dict:
    now = time.time()
    if _cache["data"] is not None and now - _cache["ts"] < _CACHE_TTL:
        return _cache["data"]
    data = _build_universe()
    _cache["data"] = data
    _cache["ts"] = now
    return data


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/universe")
def get_universe(
    signal_only: bool = Query(False, description="Only return signal tickers"),
    sector:      str  = Query("",    description="Filter by industry sector"),
    q:           str  = Query("",    description="Search by ticker or name"),
    sort_by:     str  = Query("signal", description="signal | rsi | foreign | score"),
    limit:       int  = Query(200,  ge=1, le=500),
):
    """Return enriched TWS stock universe for the management dashboard."""
    data = _get_universe()
    stocks = data["stocks"]

    if signal_only:
        stocks = [s for s in stocks if s["is_signal"]]
    if sector:
        stocks = [s for s in stocks if (s.get("industry") or "") == sector]
    if q:
        q_up = q.upper()
        stocks = [s for s in stocks
                  if q_up in str(s.get("ticker", "")).upper()
                  or q_up in str(s.get("name", "")).upper()]

    # Re-sort based on user preference
    if sort_by == "rsi":
        stocks = sorted(stocks, key=lambda s: s.get("RSI") or 999)
    elif sort_by == "foreign":
        stocks = sorted(stocks, key=lambda s: -(s.get("f60") or 0))
    elif sort_by == "score":
        stocks = sorted(stocks, key=lambda s: -(s.get("score") or 0))

    return {
        **{k: v for k, v in data.items() if k != "stocks"},
        "stocks":  stocks[:limit],
        "count":   len(stocks),
    }


@router.get("/stock/{ticker}")
def get_stock(ticker: str):
    """Return enriched detail for one TWS ticker."""
    data = _get_universe()
    ticker_up = ticker.upper().strip()
    for s in data["stocks"]:
        if str(s.get("ticker", "")).upper().strip() == ticker_up:
            return s
    return {"ticker": ticker_up, "error": f"Ticker {ticker_up} not found in universe"}


@router.post("/cache/invalidate")
def invalidate():
    _cache["data"] = None
    return {"cleared": True}
