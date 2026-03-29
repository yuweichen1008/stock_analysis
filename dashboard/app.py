"""
Personal Trading Dashboard — entry point.

Run:
    streamlit run dashboard/app.py --server.address=127.0.0.1

The --server.address flag restricts access to localhost only (default: all interfaces).
Access in browser: http://localhost:8501
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dashboard.auth import load_authenticator, require_login

st.set_page_config(
    page_title="Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Authentication gate ───────────────────────────────────────────────────────
auth = load_authenticator()
name, _ = require_login(auth)   # blocks (st.stop) until logged in

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 Trading Dashboard")
    st.caption(f"Logged in as **{name}**")
    auth.logout("Logout", "sidebar")
    st.divider()
    st.caption("Navigate using the pages above.")

# ── Landing page ─────────────────────────────────────────────────────────────
st.title("📈 Personal Trading Dashboard")
st.markdown(
    """
    Welcome to your trading dashboard. Use the sidebar pages to navigate:

    | Page | Description |
    |------|-------------|
    | **Overview** | Portfolio summary — balance + P&L across all brokers |
    | **Positions** | All open holdings merged across IBKR / Moomoo / Robinhood |
    | **Trading** | Place orders, select execution algo, run automated strategies |
    | **Signals** | Today's Taiwan + US mean-reversion signal stocks |
    | **Backtest** | Run backtests on historical data with configurable parameters |
    """
)

st.info(
    "This dashboard is for personal use. "
    "Run with `streamlit run dashboard/app.py --server.address=127.0.0.1` "
    "to restrict access to localhost only.",
    icon="🔒",
)
