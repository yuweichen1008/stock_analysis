"""
Shared data-loading helpers for the Streamlit dashboard.

All functions that touch the filesystem or broker connections are cached
with st.cache_resource (singleton) or st.cache_data (data TTL) so pages
don't re-fetch on every rerender.
"""

import json
import logging
import os
import pandas as pd
import streamlit as st
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent   # repo root

# ---------------------------------------------------------------------------
# One-time data directory bootstrap
# ---------------------------------------------------------------------------

def _bootstrap_data_dirs():
    """
    Ensure all required data directories exist on first run.
    Creates empty stub files where needed so pages never crash on missing paths.
    """
    dirs = [
        BASE_DIR / "data" / "company",
        BASE_DIR / "data" / "tickers",
        BASE_DIR / "data" / "ohlcv",
        BASE_DIR / "data" / "predictions",
        BASE_DIR / "data_us" / "ohlcv",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Stub files that dashboard pages read on first boot
    stubs = {
        BASE_DIR / "data" / "company" / "company_mapping.csv":
            "ticker,name,industry,pe_ratio,roe,debt_to_equity,target_price,"
            "recommendation,dividend_yield,last_update_date\n",
        BASE_DIR / "data" / "company" / "universe_snapshot.csv":
            "ticker,is_signal,category,score,price,MA120,MA20,RSI,bias,"
            "vol_ratio,foreign_net,f5,f20,f60,f_zscore,short_interest,"
            "news_sentiment,last_date\n",
        BASE_DIR / "data" / "predictions" / "prediction_history.csv":
            "signal_date,market,ticker,entry_price,score,RSI,bias,vol_ratio,"
            "news_sentiment,target_date,target_open,target_close,"
            "open_return_pct,close_return_pct,win_open,win_close,status\n",
    }
    for path, header in stubs.items():
        if not path.exists():
            try:
                path.write_text(header, encoding="utf-8-sig")
                logger.info("Created stub: %s", path)
            except Exception as e:
                logger.warning("Could not create stub %s: %s", path, e)


_bootstrap_data_dirs()


# ---------------------------------------------------------------------------
# Signal data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)   # re-read every 5 minutes
def load_signals(market: str = "TW") -> pd.DataFrame:
    """
    Load today's signal CSV.
    market='TW' → current_trending.csv
    market='US' → data_us/current_trending.csv
    """
    path = (
        BASE_DIR / "current_trending.csv"
        if market == "TW"
        else BASE_DIR / "data_us" / "current_trending.csv"
    )
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"ticker": str})
    return df


# ---------------------------------------------------------------------------
# Company fundamentals
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)   # re-read every hour
def load_company_mapping() -> pd.DataFrame:
    path = BASE_DIR / "data" / "company" / "company_mapping.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"ticker": str})


def merge_positions_with_fundamentals(positions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join positions DataFrame with company_mapping.
    Adds: name, industry, pe_ratio, roe, target_price columns where available.
    """
    if positions_df.empty:
        return positions_df
    mapping = load_company_mapping()
    if mapping.empty:
        return positions_df
    cols = [c for c in ["ticker", "name", "industry", "pe_ratio", "roe", "target_price"]
            if c in mapping.columns]
    return positions_df.merge(mapping[cols], on="ticker", how="left")


# ---------------------------------------------------------------------------
# Broker manager singleton
# ---------------------------------------------------------------------------

@st.cache_resource
def get_broker_manager():
    """
    Instantiate and connect BrokerManager once per Streamlit session.
    Cached as a resource so it persists across rerenders without reconnecting.
    """
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
    from brokers.manager import BrokerManager
    mgr = BrokerManager()
    mgr.connect_all()
    return mgr


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_currency(value, currency: str = "USD") -> str:
    try:
        return f"{currency} {float(value):,.2f}"
    except (ValueError, TypeError):
        return "N/A"


def fmt_pct(value, decimals: int = 2) -> str:
    try:
        return f"{float(value):+.{decimals}f}%"
    except (ValueError, TypeError):
        return "N/A"


def pnl_color(value) -> str:
    """Return 'green' or 'red' based on sign of value."""
    try:
        return "green" if float(value) >= 0 else "red"
    except (ValueError, TypeError):
        return "gray"
