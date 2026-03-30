"""
US company fundamentals mapper.

Fetches PE, ROE, sector, target price etc. via yfinance for S&P 500 stocks
and persists them in data_us/company_mapping.csv — mirroring the Taiwan
data/company/company_mapping.csv structure so the dashboard and AI layer
can treat both markets identically.

Usage (standalone or called from master_run.py):
    from us.company_mapper import update_us_mapping
    update_us_mapping(BASE_DIR, tickers)
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_REFRESH_DAYS = 7          # Re-fetch fundamentals older than this many days
_MAX_WORKERS  = 8
_COLUMNS = [
    "ticker", "name", "sector", "industry",
    "pe_ratio", "roe", "debt_to_equity",
    "target_price", "recommendation",
    "dividend_yield", "market_cap",
    "last_update_date",
]


def _mapping_path(base_dir: str) -> str:
    return str(Path(base_dir) / "data_us" / "company_mapping.csv")


def _fetch_one(ticker: str) -> dict:
    """Fetch fundamentals for a single US ticker via yfinance."""
    try:
        time.sleep(0.2)   # polite rate-limiting
        info = yf.Ticker(ticker).info

        pe  = info.get("trailingPE") or info.get("forwardPE")
        if pe is None:
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            eps   = info.get("trailingEps", 0)
            pe    = round(price / eps, 2) if eps else "N/A"

        roe = info.get("returnOnEquity")
        roe = round(float(roe), 4) if roe is not None else "N/A"

        div = info.get("dividendYield") or info.get("trailingAnnualDividendYield")
        div = round(float(div), 4) if div is not None else "N/A"

        return {
            "ticker":           ticker,
            "name":             info.get("longName", info.get("shortName", ticker)),
            "sector":           info.get("sector",           "N/A"),
            "industry":         info.get("industry",         "N/A"),
            "pe_ratio":         pe,
            "roe":              roe,
            "debt_to_equity":   info.get("debtToEquity",    "N/A"),
            "target_price":     info.get("targetMeanPrice", "N/A"),
            "recommendation":   info.get("recommendationKey","N/A"),
            "dividend_yield":   div,
            "market_cap":       info.get("marketCap",       "N/A"),
            "last_update_date": datetime.now().strftime("%Y-%m-%d"),
        }
    except Exception as e:
        logger.debug("_fetch_one(%s) failed: %s", ticker, e)
        return {
            "ticker":           ticker,
            "name":             ticker,
            "sector":           "N/A",
            "industry":         "N/A",
            "pe_ratio":         "N/A",
            "roe":              "N/A",
            "debt_to_equity":   "N/A",
            "target_price":     "N/A",
            "recommendation":   "N/A",
            "dividend_yield":   "N/A",
            "market_cap":       "N/A",
            "last_update_date": datetime.now().strftime("%Y-%m-%d"),
        }


def load_us_mapping(base_dir: str) -> pd.DataFrame:
    """Load existing US mapping CSV, return empty DF if not found."""
    path = _mapping_path(base_dir)
    if not os.path.exists(path):
        return pd.DataFrame(columns=_COLUMNS)
    return pd.read_csv(path, dtype={"ticker": str})


def update_us_mapping(base_dir: str, tickers: List[str]) -> pd.DataFrame:
    """
    Update data_us/company_mapping.csv for the given tickers.

    Only re-fetches rows that are missing or older than _REFRESH_DAYS days.
    Returns the complete updated DataFrame.
    """
    os.makedirs(str(Path(base_dir) / "data_us"), exist_ok=True)
    existing = load_us_mapping(base_dir)

    # Determine which tickers need refreshing
    stale_cutoff = (datetime.now() - timedelta(days=_REFRESH_DAYS)).strftime("%Y-%m-%d")
    to_update = []
    for t in tickers:
        row = existing[existing["ticker"] == t] if "ticker" in existing.columns else pd.DataFrame()
        if row.empty:
            to_update.append(t)
        else:
            last = str(row.iloc[0].get("last_update_date", ""))
            if last < stale_cutoff:
                to_update.append(t)

    if not to_update:
        logger.info("US mapping: all %d tickers are up to date.", len(tickers))
        return existing

    logger.info("US mapping: fetching fundamentals for %d tickers…", len(to_update))

    new_rows = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_one, t): t for t in to_update}
        for fut in as_completed(futures):
            new_rows.append(fut.result())

    if not new_rows:
        return existing

    df_new = pd.DataFrame(new_rows)

    # Merge: drop old stale rows, append fresh ones
    if not existing.empty and "ticker" in existing.columns:
        existing = existing[~existing["ticker"].isin(to_update)]
        combined = pd.concat([existing, df_new], ignore_index=True)
    else:
        combined = df_new

    # Ensure all expected columns are present
    for col in _COLUMNS:
        if col not in combined.columns:
            combined[col] = "N/A"

    combined = combined[_COLUMNS]
    combined.to_csv(_mapping_path(base_dir), index=False, encoding="utf-8-sig")
    logger.info("US mapping saved: %d rows → %s", len(combined), _mapping_path(base_dir))
    return combined
