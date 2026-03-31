"""
Finviz data integration for US stock screening and fundamentals.

Uses the `finvizfinance` library (unofficial Finviz scraper).
Install: pip install finvizfinance

Usage:
    from us.finviz_data import get_screener_results, get_stock_fundamentals

    # Screen for oversold large-caps
    df = get_screener_results({"RSI (14)": "Oversold (30)", "Market Cap.": "Large ($10bln to $200bln)"})

    # Full fundamental snapshot for one ticker
    info = get_stock_fundamentals("AAPL")
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Common Finviz screener filter keys (subset used by US pipeline)
# Full filter list: https://finviz.com/screener.ashx
_DEFAULT_FILTERS: dict[str, str] = {
    "Country": "USA",
    "Market Cap.": "Small+ (over $300mln)",
}


def get_screener_results(
    filters: Optional[dict] = None,
    order_by: str = "RSI (14)",
    max_retries: int = 2,
) -> pd.DataFrame:
    """
    Run a Finviz screener and return a DataFrame of matching US stocks.

    Args:
        filters:    Dict of Finviz filter name → value strings.
                    Merged with _DEFAULT_FILTERS (caller's values override defaults).
        order_by:   Column to sort by (Finviz column name string).
        max_retries: Number of retry attempts on network errors.

    Returns:
        DataFrame with columns including: Ticker, Company, Sector, Industry,
        Country, Market Cap, P/E, EPS (ttm), Price, Change, Volume, RSI (14), etc.
        Empty DataFrame on failure.
    """
    try:
        from finvizfinance.screener.overview import Overview
    except ImportError:
        logger.warning("finvizfinance not installed — run: pip install finvizfinance")
        return pd.DataFrame()

    merged_filters = {**_DEFAULT_FILTERS, **(filters or {})}

    for attempt in range(max_retries + 1):
        try:
            screener = Overview()
            screener.set_filter(filters_dict=merged_filters)
            df = screener.screener_view(order=order_by, verbose=0)
            if df is None or df.empty:
                return pd.DataFrame()
            logger.info("Finviz screener: %d results for filters %s", len(df), merged_filters)
            return df
        except Exception as e:
            if attempt < max_retries:
                logger.warning("Finviz screener attempt %d failed: %s — retrying", attempt + 1, e)
                time.sleep(2)
            else:
                logger.warning("Finviz screener failed after %d attempts: %s", max_retries + 1, e)
                return pd.DataFrame()

    return pd.DataFrame()


def get_stock_fundamentals(ticker: str, max_retries: int = 2) -> dict:
    """
    Fetch full fundamental + technical snapshot for a single US ticker from Finviz.

    Returns a dict with keys like: P/E, EPS (ttm), Insider Own, Short Float,
    Target Price, RSI (14), Avg Volume, Market Cap, Sector, Industry, etc.
    Returns empty dict on failure.
    """
    try:
        from finvizfinance.quote import finvizfinance
    except ImportError:
        logger.warning("finvizfinance not installed — run: pip install finvizfinance")
        return {}

    for attempt in range(max_retries + 1):
        try:
            stock = finvizfinance(ticker)
            info  = stock.ticker_fundament()
            if not info:
                return {}
            logger.debug("Finviz fundamentals fetched for %s: %d fields", ticker, len(info))
            return info
        except Exception as e:
            if attempt < max_retries:
                logger.warning("Finviz fundamentals attempt %d failed for %s: %s", attempt + 1, ticker, e)
                time.sleep(1)
            else:
                logger.warning("Finviz fundamentals failed for %s: %s", ticker, e)
                return {}

    return {}


def enrich_signals_with_finviz(signals_df: pd.DataFrame, delay: float = 0.5) -> pd.DataFrame:
    """
    Enrich a US signal DataFrame with Finviz fundamentals (P/E, EPS, Sector, Target Price).

    Called by us/us_trending.py after the signal list is finalized.
    Adds columns: fv_pe, fv_eps, fv_sector, fv_target_price, fv_analyst_rating.

    Args:
        signals_df: DataFrame with a 'ticker' column.
        delay:      Sleep between API calls to avoid rate limiting.

    Returns:
        signals_df with additional fv_* columns (NaN for tickers that fail).
    """
    if signals_df.empty or "ticker" not in signals_df.columns:
        return signals_df

    enriched_rows = []
    for ticker in signals_df["ticker"].tolist():
        info = get_stock_fundamentals(ticker)
        enriched_rows.append({
            "ticker":            ticker,
            "fv_pe":             _safe_float(info.get("P/E")),
            "fv_eps":            _safe_float(info.get("EPS (ttm)")),
            "fv_sector":         info.get("Sector", ""),
            "fv_industry":       info.get("Industry", ""),
            "fv_target_price":   _safe_float(info.get("Target Price")),
            "fv_analyst_rating": info.get("Recom.", ""),
            "fv_short_float":    info.get("Short Float", ""),
        })
        time.sleep(delay)

    fv_df = pd.DataFrame(enriched_rows)
    return signals_df.merge(fv_df, on="ticker", how="left")


def _safe_float(val) -> float | None:
    """Parse a Finviz value string like '24.5' or '24.5B' to float, or None."""
    if val is None:
        return None
    s = str(val).replace(",", "").replace("%", "").strip()
    if s in ("-", "N/A", ""):
        return None
    # Handle suffixes like B/M/K
    multipliers = {"B": 1e9, "M": 1e6, "K": 1e3, "T": 1e12}
    if s and s[-1].upper() in multipliers:
        try:
            return float(s[:-1]) * multipliers[s[-1].upper()]
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None
