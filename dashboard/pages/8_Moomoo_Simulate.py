"""
Moomoo Simulate Account — portfolio viewer and trade backtrack.

Connects directly to Moomoo OpenD with SIMULATE trade environment
(independent of the MOOMOO_TRADE_ENV env var so this page always
shows simulate data regardless of other settings).

Tabs:
  1. Positions     — balance summary + current holdings
  2. Order History — all orders in last 90 days, colour-coded BUY/SELL
  3. Backtrack     — cross-reference filled orders with signal predictions
                     to show how the system actually performed in simulation
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

from dashboard.data_helpers import BASE_DIR

load_dotenv(BASE_DIR / ".env")

st.set_page_config(page_title="Moomoo Simulate", page_icon="🟡", layout="wide")
st.title("🟡 Moomoo Simulate Account")
st.caption("Paper-trading view — SIMULATE environment, OpenD required")

# ── Connect to Moomoo SIMULATE ────────────────────────────────────────────────

@st.cache_resource(show_spinner="Connecting to Moomoo OpenD…")
def _get_moomoo_client():
    """Force SIMULATE env regardless of .env setting."""
    import os
    os.environ["MOOMOO_TRADE_ENV"] = "SIMULATE"
    from brokers.moomoo import MoomooClient
    client = MoomooClient()
    ok = client.connect()
    return client, ok


client, connected = _get_moomoo_client()

if not connected:
    st.error(
        "**Cannot connect to Moomoo OpenD.**\n\n"
        "Make sure Futu OpenD is running on your machine, then refresh this page.\n\n"
        "- Download: https://www.futunn.com/download/OpenAPI\n"
        "- Default port: `11111` (set `MOOMOO_PORT` in `.env` to override)\n"
        "- Set `MOOMOO_MARKET=US` or `HK` in `.env`"
    )
    st.stop()

st.success("Connected to Moomoo OpenD (SIMULATE)")

if st.button("🔄 Refresh data"):
    st.cache_resource.clear()
    st.rerun()

st.divider()

# ── Fetch data ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner="Fetching positions…")
def _positions():
    return client.get_positions()

@st.cache_data(ttl=60, show_spinner="Fetching balance…")
def _balance():
    return client.get_balance()

@st.cache_data(ttl=60, show_spinner="Fetching order history…")
def _orders(days=90):
    return client.get_orders(days=days)


balance  = _balance()
pos_df   = _positions()
order_df = _orders(90)

# ── Prediction history for backtrack tab ─────────────────────────────────────

@st.cache_data(ttl=120)
def _pred_history():
    p = BASE_DIR / "data" / "predictions" / "prediction_history.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, dtype={"ticker": str, "market": str})
    for col in ["entry_price", "score", "RSI", "open_return_pct", "close_return_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["signal_date"] = pd.to_datetime(df["signal_date"], errors="coerce")
    return df


pred_df = _pred_history()

# ══════════════════════════════════════════════════════════════════════════════
tab_pos, tab_orders, tab_back = st.tabs([
    "💼 Positions", "📋 Order History", "📊 Backtrack"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Positions + Balance
# ══════════════════════════════════════════════════════════════════════════════
with tab_pos:
    # Balance cards
    if balance:
        cur   = balance.get("currency", "USD")
        total = balance.get("total_value",    0.0)
        cash  = balance.get("cash",           0.0)
        upnl  = balance.get("unrealized_pnl", 0.0)

        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Total Value",      f"{cur} {total:,.2f}")
        b2.metric("Cash",             f"{cur} {cash:,.2f}")
        b3.metric("Unrealized P&L",   f"{cur} {upnl:+,.2f}",
                  delta=f"{upnl:+.2f}", delta_color="normal")
        b4.metric("Invested",         f"{cur} {total - cash:,.2f}")
    else:
        st.info("Balance unavailable.")

    st.divider()

    if pos_df.empty:
        st.info("No open positions in Simulate account.")
    else:
        # Allocation pie
        fig_pie = px.pie(
            pos_df,
            values="mkt_value",
            names="ticker",
            title="Simulate Portfolio Allocation",
            hole=0.38,
            template="plotly_dark",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_pie.update_layout(paper_bgcolor="#0d1117", height=360)

        # P&L bar
        ps = pos_df.sort_values("pnl")
        colors = ["#ef5350" if v < 0 else "#00e676" for v in ps["pnl"]]
        fig_pnl = go.Figure(go.Bar(
            x=ps["ticker"], y=ps["pnl"],
            marker_color=colors,
            text=[f"{v:+.0f}" for v in ps["pnl"]],
            textposition="outside",
        ))
        fig_pnl.update_layout(
            title="Unrealized P&L by Position",
            template="plotly_dark",
            paper_bgcolor="#0d1117",
            height=300,
            xaxis_title="Ticker",
            yaxis_title="P&L",
        )

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            st.plotly_chart(fig_pnl, use_container_width=True)

        st.dataframe(
            pos_df.style.format({
                "qty":       "{:.0f}",
                "avg_cost":  "{:.2f}",
                "mkt_value": "{:,.2f}",
                "pnl":       "{:+,.2f}",
            }).applymap(
                lambda v: "color:#00e676" if isinstance(v, (int, float)) and v > 0
                          else ("color:#ef5350" if isinstance(v, (int, float)) and v < 0 else ""),
                subset=["pnl"],
            ),
            use_container_width=True,
            hide_index=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Order History
# ══════════════════════════════════════════════════════════════════════════════
with tab_orders:
    if order_df.empty:
        st.info("No orders found in the last 90 days.")
    else:
        # Filter controls
        fc1, fc2 = st.columns(2)
        side_filter   = fc1.multiselect("Side", ["BUY", "SELL"], default=["BUY", "SELL"])
        status_filter = fc2.multiselect(
            "Status",
            order_df["status"].unique().tolist(),
            default=order_df["status"].unique().tolist(),
        )

        filtered = order_df[
            order_df["side"].isin(side_filter) &
            order_df["status"].isin(status_filter)
        ].copy()

        # Trade value column
        filtered["value"] = filtered["qty"] * filtered["price"]

        # Volume by ticker bar
        by_ticker = (
            filtered[filtered["side"] == "BUY"]
            .groupby("ticker")["value"].sum()
            .reset_index()
            .sort_values("value", ascending=False)
            .head(20)
        )
        if not by_ticker.empty:
            fig_vol = px.bar(
                by_ticker, x="ticker", y="value",
                title="Total Buy Value by Ticker (simulate)",
                labels={"value": "Value (USD)", "ticker": "Ticker"},
                template="plotly_dark",
                color_discrete_sequence=["#00b4d8"],
            )
            fig_vol.update_layout(paper_bgcolor="#0d1117", height=280)
            st.plotly_chart(fig_vol, use_container_width=True)

        def _side_style(val):
            if val == "BUY":  return "color:#00e676; font-weight:bold"
            if val == "SELL": return "color:#f77f00; font-weight:bold"
            return ""

        st.dataframe(
            filtered.style.applymap(_side_style, subset=["side"])
            .format({"qty": "{:.0f}", "price": "{:.2f}", "value": "{:,.2f}"}),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"{len(filtered)} orders shown")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Backtrack (orders vs prediction history)
# ══════════════════════════════════════════════════════════════════════════════
with tab_back:
    st.markdown(
        "Cross-reference Moomoo SIMULATE filled BUY orders with the signal "
        "prediction history to see how the strategy performed in paper trading."
    )

    if order_df.empty:
        st.info("No order history to backtrack.")
    elif pred_df.empty:
        st.info("No prediction history yet — run `master_run.py` to start recording.")
    else:
        # Keep only filled BUY orders
        filled_buys = order_df[
            (order_df["side"] == "BUY") & (order_df["status"] == "FILLED")
        ].copy()
        filled_buys["date"] = pd.to_datetime(filled_buys["date"], errors="coerce")

        if filled_buys.empty:
            st.info("No filled BUY orders to match.")
        else:
            # Match on ticker + date (order date == signal_date)
            resolved_preds = pred_df[pred_df["status"] == "resolved"].copy()
            resolved_preds["signal_date_d"] = resolved_preds["signal_date"].dt.normalize()
            filled_buys["date_d"]           = filled_buys["date"].dt.normalize()

            merged = filled_buys.merge(
                resolved_preds.rename(columns={"signal_date_d": "date_d"}),
                on=["ticker", "date_d"],
                how="inner",
                suffixes=("_order", "_pred"),
            )

            if merged.empty:
                st.info(
                    "No overlap between filled Moomoo orders and resolved predictions yet.\n\n"
                    "This will populate once orders placed on signal dates have their "
                    "outcomes resolved (next morning)."
                )
            else:
                n = len(merged)
                wins = int(merged["win_open"].sum())
                wr   = wins / n * 100
                avg_ret = merged["open_return_pct"].mean()

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Matched Trades",       n)
                k2.metric("Wins (open exit)",      wins)
                k3.metric("Win Rate",             f"{wr:.1f}%")
                k4.metric("Avg Open Return",      f"{avg_ret:+.2f}%")

                # Equity curve from actual simulate trades
                mc = merged.sort_values("date_d").copy()
                mc["cum_return"] = mc["open_return_pct"].cumsum()
                fig_eq = px.line(
                    mc, x="date_d", y="cum_return",
                    title="Simulate Account — Cumulative Return (open exit, equal-weighted)",
                    labels={"date_d": "Date", "cum_return": "Cumulative Return %"},
                    template="plotly_dark",
                    color_discrete_sequence=["#ffa726"],
                )
                fig_eq.add_hline(y=0, line=dict(color="#888", dash="dash", width=1))
                fig_eq.update_layout(paper_bgcolor="#0d1117", height=300)
                st.plotly_chart(fig_eq, use_container_width=True)

                # Detail table
                display_cols = [c for c in [
                    "date_d", "ticker", "qty", "price_order",
                    "score", "RSI", "open_return_pct", "win_open",
                ] if c in merged.columns]
                st.dataframe(
                    merged[display_cols]
                    .rename(columns={
                        "date_d":          "date",
                        "price_order":     "fill_price",
                        "open_return_pct": "return%",
                    })
                    .sort_values("date", ascending=False)
                    .style.format({
                        "score":       "{:.1f}",
                        "RSI":         "{:.1f}",
                        "fill_price":  "{:.2f}",
                        "return%":     "{:+.2f}%",
                        "qty":         "{:.0f}",
                    }).applymap(
                        lambda v: "color:#00e676" if v is True
                                  else ("color:#ef5350" if v is False else ""),
                        subset=["win_open"],
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
