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


def _render_signal_card(row, market: str):
    """Render a single signal stock card with trade button."""
    ticker = str(row["ticker"])
    name   = str(row.get("name", ticker))
    score  = float(row.get("score", 0) or 0)
    rsi    = float(row["RSI"])   if pd.notna(row.get("RSI"))   else None
    bias   = float(row["bias"])  if pd.notna(row.get("bias"))  else None
    price  = float(row["price"]) if pd.notna(row.get("price")) else None
    sent   = float(row.get("news_sentiment", 0) or 0)
    fv_pe  = row.get("fv_pe")
    fv_sec = str(row.get("fv_sector") or "")[:24]

    sent_icon = "😊" if sent > 0.1 else ("😟" if sent < -0.1 else "😐")

    with st.container():
        c1, c2, c3, c4, c5, c6 = st.columns([2, 1.5, 1.5, 1.5, 1, 1])
        label = f"**{ticker}** {name}"
        if fv_sec:
            label += f"  `{fv_sec}`"
        c1.markdown(label)
        c2.metric("Score",  f"⭐ {score:.1f}")
        c3.metric("RSI",    f"{rsi:.1f}"     if rsi   is not None else "N/A")
        c4.metric("Bias",   f"{bias:.1f}%"   if bias  is not None else "N/A")
        c5.metric("Price",  f"{price:.2f}"   if price is not None else "N/A",
                  help=f"PE: {fv_pe}" if fv_pe else None)
        c6.markdown(f"Sentiment: {sent_icon}")

        if connected:
            if c6.button("⚡ Trade", key=f"trade_{ticker}_{market}"):
                st.session_state["prefill_ticker"] = ticker
                st.session_state["prefill_broker"] = connected[0]
                st.switch_page("pages/3_Trading.py")

    st.markdown("---")


def _render_signals(market: str, tab_label: str):
    df = load_signals(market)
    mapping = load_company_mapping()

    if df.empty:
        st.warning(
            f"No {tab_label} signal file found. "
            "Run `python master_run.py` to generate today's signals."
        )
        return

    # Enrich with company name/industry
    if not mapping.empty and "ticker" in mapping.columns and "name" in mapping.columns:
        df = df.merge(mapping[["ticker", "name", "industry"]], on="ticker", how="left")

    # Split signals from watch-list
    is_sig_mask  = df["is_signal"].astype(str).str.lower().isin(["true", "1"]) \
                   if "is_signal" in df.columns else pd.Series([True] * len(df))
    is_watch_mask = df.get("category", pd.Series([""] * len(df))) == "finviz_watch"

    signals   = df[is_sig_mask].copy()
    watchlist = df[is_watch_mask].copy()

    # ── KPI bar (signals only) ────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Signals Today",  len(signals))
    k2.metric("Avg Score",      f"{signals['score'].mean():.1f}"  if not signals.empty and "score" in signals else "N/A")
    k3.metric("Avg RSI",        f"{signals['RSI'].mean():.1f}"    if not signals.empty and "RSI"   in signals else "N/A")
    k4.metric("Avg Bias",       f"{signals['bias'].mean():.1f}%"  if not signals.empty and "bias"  in signals else "N/A")

    st.divider()

    # ── Score distribution ────────────────────────────────────────────────────
    if not signals.empty and "score" in signals.columns:
        fig = px.histogram(
            signals, x="score", nbins=10,
            title="Signal Score Distribution",
            labels={"score": "Score (0-10)"},
            color_discrete_sequence=["#26a69a"],
            template="plotly_dark",
        )
        fig.update_layout(paper_bgcolor="#0d1117", height=220)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Signal cards ──────────────────────────────────────────────────────────
    if not signals.empty:
        st.subheader(f"🎯 {tab_label} Signal Stocks ({len(signals)})")
        sort_col = "score" if "score" in signals.columns else signals.columns[0]
        for _, row in signals.sort_values(sort_col, ascending=False).iterrows():
            _render_signal_card(row, market)
    else:
        st.info(f"No {tab_label} mean-reversion signals fired today.")

    # ── Finviz watch-list (US only) ───────────────────────────────────────────
    if not watchlist.empty:
        st.divider()
        st.subheader(f"👀 Finviz Watch-List ({len(watchlist)} near-oversold)")
        st.caption("These stocks didn't fire a full signal but are approaching oversold territory.")
        for _, row in watchlist.sort_values("RSI", ascending=True).iterrows():
            ticker  = str(row["ticker"])
            price   = float(row["price"])  if pd.notna(row.get("price"))  else None
            rsi     = float(row["RSI"])    if pd.notna(row.get("RSI"))    else None
            fv_sec  = str(row.get("fv_sector") or "")[:24]
            fv_pe   = row.get("fv_pe")
            fv_rat  = str(row.get("fv_analyst_rating") or "")

            with st.container():
                c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 2])
                c1.markdown(f"**{ticker}**  `{fv_sec}`" if fv_sec else f"**{ticker}**")
                c2.metric("RSI",   f"{rsi:.1f}"   if rsi   is not None else "N/A")
                c3.metric("Price", f"${price:.2f}" if price is not None else "N/A",
                          help=f"PE: {fv_pe}" if fv_pe else None)
                c4.markdown(f"*{fv_rat}*" if fv_rat else "")
            st.markdown("---")


with tab_tw:
    _render_signals("TW", "Taiwan")

with tab_us:
    _render_signals("US", "US")
