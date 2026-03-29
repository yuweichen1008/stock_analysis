"""
Signals page — today's Taiwan + US mean-reversion signal stocks.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.express as px
from dashboard.data_helpers import get_broker_manager, load_signals, load_company_mapping

st.set_page_config(page_title="Signals", page_icon="🚀", layout="wide")
st.title("🚀 Signal Stocks")
st.caption("Stocks that fired the mean-reversion buy signal: price > MA120, RSI < 35, Bias < -2%")

mgr       = get_broker_manager()
connected = mgr.connected_broker_names()

if st.button("🔄 Refresh signals"):
    st.cache_data.clear()
    st.rerun()

tab_tw, tab_us = st.tabs(["🇹🇼 Taiwan (TWS)", "🇺🇸 US Stocks"])

SIGNAL_COLS = [
    "ticker", "score", "price", "RSI", "bias", "MA120", "MA20",
    "vol_ratio", "foreign_net", "f5", "f20", "f_zscore",
    "news_sentiment", "last_date",
]


def _render_signals(market: str, tab_label: str):
    df = load_signals(market)
    mapping = load_company_mapping()

    if df.empty:
        st.warning(
            f"No {tab_label} signal file found. "
            "Run `python master_run.py` to generate today's signals."
        )
        return

    # Enrich with company name
    if not mapping.empty and "ticker" in mapping.columns and "name" in mapping.columns:
        df = df.merge(mapping[["ticker", "name", "industry"]], on="ticker", how="left")

    available_cols = [c for c in SIGNAL_COLS if c in df.columns]
    display_df = df[available_cols].copy()

    # ── KPI bar ──────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Signals Today",   len(df))
    k2.metric("Avg Score",       f"{df['score'].mean():.1f}" if "score" in df else "N/A")
    k3.metric("Avg RSI",         f"{df['RSI'].mean():.1f}"   if "RSI"   in df else "N/A")
    k4.metric("Avg Bias",        f"{df['bias'].mean():.1f}%" if "bias"  in df else "N/A")

    st.divider()

    # ── Score distribution chart ──────────────────────────────────────────────
    if "score" in df.columns:
        fig = px.histogram(
            df, x="score", nbins=10,
            title="Signal Score Distribution",
            labels={"score": "Score (0-10)"},
            color_discrete_sequence=["#26a69a"],
            template="plotly_dark",
        )
        fig.update_layout(paper_bgcolor="#0d1117", height=250)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Signal table with Trade This button ──────────────────────────────────
    st.subheader(f"{tab_label} Signal Stocks ({len(df)})")

    for _, row in df.sort_values("score", ascending=False).iterrows() if "score" in df.columns \
            else df.iterrows():
        ticker  = str(row["ticker"])
        name    = str(row.get("name", ticker))
        score   = float(row.get("score",  0))
        rsi     = float(row.get("RSI",    0)) if pd.notna(row.get("RSI"))    else None
        bias    = float(row.get("bias",   0)) if pd.notna(row.get("bias"))   else None
        price   = float(row.get("price",  0)) if pd.notna(row.get("price"))  else None
        sent    = float(row.get("news_sentiment", 0)) if pd.notna(row.get("news_sentiment")) else 0

        sent_icon = "😊" if sent > 0.1 else ("😟" if sent < -0.1 else "😐")

        with st.container():
            c1, c2, c3, c4, c5, c6 = st.columns([2, 1.5, 1.5, 1.5, 1, 1])
            c1.markdown(f"**{ticker}** {name}")
            c2.metric("Score",  f"⭐ {score:.1f}")
            c3.metric("RSI",    f"{rsi:.1f}"     if rsi   is not None else "N/A")
            c4.metric("Bias",   f"{bias:.1f}%"   if bias  is not None else "N/A")
            c5.metric("Price",  f"{price:.2f}"   if price is not None else "N/A")
            c6.markdown(f"Sentiment: {sent_icon}")

            if connected:
                if c6.button("⚡ Trade", key=f"trade_{ticker}_{market}"):
                    st.session_state["prefill_ticker"] = ticker
                    st.session_state["prefill_broker"] = connected[0]
                    st.switch_page("pages/3_Trading.py")

        st.markdown("---")


with tab_tw:
    _render_signals("TW", "Taiwan")

with tab_us:
    _render_signals("US", "US")
