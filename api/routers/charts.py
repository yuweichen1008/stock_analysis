"""
OHLCV Chart data API — returns candlestick/band data for any ticker.

Tries Moomoo first (if OpenD is running), falls back to yfinance.

GET /api/charts/ohlcv/{ticker}?period=3mo&market=US
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/charts", tags=["charts"])

VALID_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y"}


@router.get("/ohlcv/{ticker}")
async def get_ohlcv(
    ticker: str,
    period: str = Query("3mo", description="1mo | 3mo | 6mo | 1y | 2y"),
    market: str = Query("US",  description="US | TW"),
):
    """Return OHLCV bars + MA20 + MA50 for charting."""
    if period not in VALID_PERIODS:
        period = "3mo"

    def _fetch_yfinance():
        import math
        import yfinance as yf

        yf_ticker = ticker.upper()
        if market == "TW" and not yf_ticker.endswith(".TW"):
            yf_ticker = f"{yf_ticker}.TW"

        hist = yf.Ticker(yf_ticker).history(period=period)
        if hist.empty:
            return {"ticker": ticker.upper(), "market": market, "period": period, "bars": [],
                    "error": f"No data found for {yf_ticker}"}

        close = hist["Close"]
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()

        bars = []
        for i, (dt, row) in enumerate(hist.iterrows()):
            m20 = float(ma20.iloc[i])
            m50 = float(ma50.iloc[i])
            bars.append({
                "date":   dt.strftime("%Y-%m-%d"),
                "open":   round(float(row["Open"]),  4),
                "high":   round(float(row["High"]),  4),
                "low":    round(float(row["Low"]),   4),
                "close":  round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
                "ma20":   round(m20, 4) if not math.isnan(m20) else None,
                "ma50":   round(m50, 4) if not math.isnan(m50) else None,
            })

        latest = bars[-1] if bars else {}
        return {
            "ticker":       ticker.upper(),
            "market":       market,
            "period":       period,
            "bars":         bars,
            "latest_close": latest.get("close"),
            "latest_date":  latest.get("date"),
            "source":       "yfinance",
        }

    try:
        return await asyncio.to_thread(_fetch_yfinance)
    except Exception as exc:
        return {"ticker": ticker.upper(), "market": market, "period": period, "bars": [],
                "error": str(exc)}


@router.get("/search")
async def search_ticker(q: str = Query(..., min_length=1, max_length=20)):
    """Basic ticker lookup via yfinance fast_info."""
    def _search():
        import yfinance as yf
        ticker = q.strip().upper()
        try:
            info = yf.Ticker(ticker).fast_info
            return {
                "ticker": ticker,
                "name":   getattr(info, "company_name", ticker),
                "found":  True,
            }
        except Exception:
            return {"ticker": ticker, "name": ticker, "found": False}

    try:
        return await asyncio.to_thread(_search)
    except Exception as exc:
        return {"ticker": q.upper(), "found": False, "error": str(exc)}
