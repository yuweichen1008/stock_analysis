"""
Shared data-loading helpers for the Streamlit dashboard.

All functions that touch the filesystem or broker connections are cached
with st.cache_resource (singleton) or st.cache_data (data TTL) so pages
don't re-fetch on every rerender.
"""

import os
import pandas as pd
import streamlit as st
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent   # repo root


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
