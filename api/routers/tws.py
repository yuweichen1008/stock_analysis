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

import asyncio
import io
import logging
from datetime import datetime, timezone
import math
import sys
import time
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Query

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import Depends
from sqlalchemy.orm import Session

from api.config import settings
from api.db import TwsStockCache, get_db

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


# ── DB-first ticker lookup ─────────────────────────────────────────────────────

def _fetch_and_store_ticker(ticker: str, db: Session) -> dict:
    """Fetch ticker from yfinance, compute RSI/MA, persist to tws_stock_cache."""
    import math
    import yfinance as yf

    yf_ticker = f"{ticker}.TW" if not ticker.upper().endswith(".TW") else ticker
    t = yf.Ticker(yf_ticker)

    hist = t.history(period="6mo")
    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass

    price = rsi_14 = ma20 = ma120 = bias = None
    open_price = None

    if not hist.empty:
        close = hist["Close"]
        price = float(close.iloc[-1])
        open_price = float(hist["Open"].iloc[-1])

        # RSI(14) — Wilder's
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi_series = 100 - 100 / (1 + rs)
        if len(rsi_series) >= 14:
            v = rsi_series.iloc[-1]
            rsi_14 = None if math.isnan(v) else round(float(v), 2)

        # MA20 / MA120
        if len(close) >= 20:
            v = close.rolling(20).mean().iloc[-1]
            ma20 = None if math.isnan(v) else round(float(v), 2)
        if len(close) >= 120:
            v = close.rolling(120).mean().iloc[-1]
            ma120 = None if math.isnan(v) else round(float(v), 2)

        # Bias vs MA20
        if ma20 and ma20 > 0 and price:
            bias = round((price - ma20) / ma20 * 100, 2)

    def _g(k, default=None):
        v = info.get(k, default)
        return None if v == "N/A" or v is None else v

    # name: try yfinance info, fall back to company_mapping
    name = _g("longName") or _g("shortName")
    if not name:
        try:
            map_df = _read_csv_local(BASE_DIR / "data" / "company" / "company_mapping.csv")
            if map_df is not None:
                row = map_df[map_df["ticker"] == ticker.upper()]
                if not row.empty:
                    name = str(row.iloc[0].get("name", ""))
        except Exception:
            pass

    row = db.query(TwsStockCache).filter(TwsStockCache.ticker == ticker.upper()).first()
    now = datetime.now(timezone.utc)

    data = {
        "name":           name,
        "industry":       _g("sector") or _g("industry"),
        "price":          price,
        "open_price":     open_price,
        "high_52w":       _safe(_g("fiftyTwoWeekHigh")),
        "low_52w":        _safe(_g("fiftyTwoWeekLow")),
        "volume":         int(_g("volume") or 0) or None,
        "market_cap":     _safe(_g("marketCap")),
        "pe_ratio":       _safe(_g("trailingPE")),
        "roe":            _safe(_g("returnOnEquity")),
        "dividend_yield": _safe(_g("dividendYield")),
        "rsi_14":         rsi_14,
        "ma20":           ma20,
        "ma120":          ma120,
        "bias":           bias,
        "updated_at":     now,
    }

    if row:
        for k, v in data.items():
            setattr(row, k, v)
    else:
        row = TwsStockCache(ticker=ticker.upper(), fetched_at=now, **data)
        db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ticker":         row.ticker,
        "name":           row.name,
        "industry":       row.industry,
        "price":          row.price,
        "open_price":     row.open_price,
        "high_52w":       row.high_52w,
        "low_52w":        row.low_52w,
        "volume":         row.volume,
        "market_cap":     row.market_cap,
        "pe_ratio":       str(row.pe_ratio) if row.pe_ratio else None,
        "roe":            str(round(row.roe * 100, 2)) + "%" if row.roe else None,
        "dividend_yield": str(round(row.dividend_yield * 100, 2)) + "%" if row.dividend_yield else None,
        "rsi_14":         row.rsi_14,
        "ma20":           row.ma20,
        "ma120":          row.ma120,
        "bias":           row.bias,
        "RSI":            row.rsi_14,
        "MA20":           row.ma20,
        "MA120":          row.ma120,
        "is_signal":      False,
        "category":       None,
        "score":          None,
        "source":         "yfinance",
        "fetched_at":     row.fetched_at.isoformat() if row.fetched_at else None,
        "updated_at":     row.updated_at.isoformat() if row.updated_at else None,
    }


_STALE_HOURS = 4   # re-fetch if cached data is older than this


@router.get("/lookup/{ticker}")
async def lookup_ticker(ticker: str, db: Session = Depends(get_db)):
    """
    DB-first ticker lookup for the TWS search box.

    1. Check tws_stock_cache in DB — return immediately if fresh (< 4h old)
    2. Check universe_snapshot / company_mapping (in-memory, fast)
    3. If not found or stale → fetch from yfinance, store in DB, return
    """
    ticker_up = ticker.upper().strip()

    # ── Step 1: DB cache ──────────────────────────────────────────────────────
    row = db.query(TwsStockCache).filter(TwsStockCache.ticker == ticker_up).first()
    if row and row.updated_at:
        age_hours = (datetime.now(timezone.utc) - row.updated_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        if age_hours < _STALE_HOURS:
            return {
                "ticker":         row.ticker,
                "name":           row.name,
                "industry":       row.industry,
                "price":          row.price,
                "open_price":     row.open_price,
                "high_52w":       row.high_52w,
                "low_52w":        row.low_52w,
                "volume":         row.volume,
                "market_cap":     row.market_cap,
                "pe_ratio":       str(row.pe_ratio) if row.pe_ratio else None,
                "roe":            str(round(row.roe * 100, 2)) + "%" if row.roe else None,
                "dividend_yield": str(round(row.dividend_yield * 100, 2)) + "%" if row.dividend_yield else None,
                "RSI":            row.rsi_14,
                "rsi_14":         row.rsi_14,
                "MA20":           row.ma20,
                "MA120":          row.ma120,
                "ma20":           row.ma20,
                "ma120":          row.ma120,
                "bias":           row.bias,
                "is_signal":      False,
                "category":       None,
                "score":          None,
                "source":         "db_cache",
                "fetched_at":     row.fetched_at.isoformat() if row.fetched_at else None,
                "updated_at":     row.updated_at.isoformat() if row.updated_at else None,
            }

    # ── Step 2: in-memory universe (already loaded) ────────────────────────────
    data = _get_universe()
    for s in data["stocks"]:
        if str(s.get("ticker", "")).upper() == ticker_up:
            return {**s, "source": "universe_snapshot"}

    # ── Step 3: yfinance fetch + persist ──────────────────────────────────────
    try:
        return await asyncio.to_thread(_fetch_and_store_ticker, ticker_up, db)
    except Exception as exc:
        return {"ticker": ticker_up, "error": str(exc), "source": "error"}
