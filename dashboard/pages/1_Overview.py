"""
Overview page — combined portfolio summary across all connected brokers.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from typing import Optional
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from pathlib import Path
from dashboard.data_helpers import (
    BASE_DIR, get_broker_manager, merge_positions_with_fundamentals, fmt_currency
)

st.set_page_config(page_title="Overview", page_icon="💰", layout="wide")
st.title("💰 Portfolio Overview")

mgr = get_broker_manager()
connected = mgr.connected_broker_names()

# ── YTD baseline helpers ───────────────────────────────────────────────────────
_BASELINE_FILE    = BASE_DIR / "data" / "portfolio_baseline.json"
_STRATEGIES_FILE  = BASE_DIR / "data" / "account_strategies.json"
_STRATEGY_OPTIONS = ["Mean-Reversion", "High-Value Moat", "US Momentum", "Hold Only"]


def _load_baseline() -> Optional[dict]:
    if _BASELINE_FILE.exists():
        try:
            return json.loads(_BASELINE_FILE.read_text())
        except Exception:
            pass
    return None


def _save_baseline(total_value: float):
    _BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _BASELINE_FILE.write_text(json.dumps({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_value": round(total_value, 2),
    }))


def _load_strategies() -> dict:
    if _STRATEGIES_FILE.exists():
        try:
            return json.loads(_STRATEGIES_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_strategies(strategies: dict):
    _STRATEGIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STRATEGIES_FILE.write_text(json.dumps(strategies))

# ── Broker connection status ──────────────────────────────────────────────────
st.subheader("Broker Connections")
brokers_to_check = ["IBKR", "Moomoo", "Robinhood"]
cols = st.columns(len(brokers_to_check))
for col, name in zip(cols, brokers_to_check):
    status = "🟢 Connected" if name in connected else "🔴 Not configured"
    col.metric(label=name, value=status)

if not connected:
    st.warning("No brokers connected. Add credentials to `.env` and restart the dashboard.")
    st.stop()

st.divider()

# ── Balance cards ─────────────────────────────────────────────────────────────
st.subheader("Account Balances")
balances = mgr.get_all_balances()

if balances:
    b_cols = st.columns(len(balances))
    total_value_usd = 0.0
    total_cash      = 0.0
    total_upnl      = 0.0
    for col, b in zip(b_cols, balances):
        cur   = b.get("currency", "USD")
        total = b.get("total_value", 0)
        cash  = b.get("cash",        0)
        upnl  = b.get("unrealized_pnl", 0)
        total_value_usd += total
        total_cash      += cash
        total_upnl      += upnl
        with col:
            st.markdown(f"### {b['broker']}")
            st.metric("Net Value",       fmt_currency(total, cur))
            st.metric("Cash",            fmt_currency(cash,  cur))
            st.metric("Unrealized P&L",  fmt_currency(upnl,  cur),
                      delta=f"{upnl:+.2f}",
                      delta_color="normal")

    st.divider()

    # ── YTD KPI row ───────────────────────────────────────────────────────────
    baseline = _load_baseline()
    ytd_pct  = None
    ytd_delta = None
    if baseline and baseline.get("total_value", 0) > 0:
        ytd_pct   = (total_value_usd - baseline["total_value"]) / baseline["total_value"] * 100
        ytd_delta = total_value_usd - baseline["total_value"]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("💼 Total Assets",       f"{total_value_usd:,.2f}",
              help="Sum of all broker net values")
    k2.metric("📈 Unrealized PnL",     f"{total_upnl:+,.2f}",
              delta=f"{total_upnl:+,.2f}", delta_color="normal")
    k3.metric("💵 Total Cash",         f"{total_cash:,.2f}")
    if ytd_pct is not None:
        k4.metric(
            f"📊 YTD Return (since {baseline['date']})",
            f"{ytd_pct:+.2f}%",
            delta=f"{ytd_delta:+,.2f}",
            delta_color="normal",
        )
    else:
        with k4:
            st.metric("📊 YTD Return", "—", help="No baseline set")
            if st.button("📌 Set Baseline Now"):
                _save_baseline(total_value_usd)
                st.success(f"Baseline set: {total_value_usd:,.2f} on {datetime.now().strftime('%Y-%m-%d')}")
                st.rerun()

    st.divider()

    # ── Account strategy selector ─────────────────────────────────────────────
    with st.expander("🎯 Account Strategies", expanded=False):
        st.caption("Select a trading strategy per broker. Saved automatically.")
        saved_strats = _load_strategies()
        new_strats   = {}
        strat_cols   = st.columns(max(len(balances), 1))
        for col, b in zip(strat_cols, balances):
            broker = b["broker"]
            default_idx = _STRATEGY_OPTIONS.index(saved_strats.get(broker, "Mean-Reversion"))
            chosen = col.selectbox(broker, _STRATEGY_OPTIONS, index=default_idx, key=f"strat_{broker}")
            new_strats[broker] = chosen
        if new_strats != saved_strats:
            _save_strategies(new_strats)
            st.caption("✅ Strategies saved.")

st.divider()

# ── Positions summary ─────────────────────────────────────────────────────────
st.subheader("Open Positions Summary")
pos_df = mgr.get_all_positions()

if pos_df.empty:
    st.info("No open positions across connected brokers.")
else:
    enriched = merge_positions_with_fundamentals(pos_df)

    # Allocation pie chart
    fig_pie = px.pie(
        enriched,
        values="mkt_value",
        names="ticker",
        color="broker",
        title="Portfolio Allocation by Market Value",
        hole=0.35,
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    fig_pie.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0d1117",
        height=400,
        showlegend=True,
    )

    # P&L bar chart
    enriched_sorted = enriched.sort_values("pnl")
    colors = ["#ef5350" if v < 0 else "#26a69a" for v in enriched_sorted["pnl"]]
    fig_pnl = go.Figure(go.Bar(
        x=enriched_sorted["ticker"],
        y=enriched_sorted["pnl"],
        marker_color=colors,
        text=[f"{v:+.0f}" for v in enriched_sorted["pnl"]],
        textposition="outside",
    ))
    fig_pnl.update_layout(
        title="Unrealized P&L by Position",
        template="plotly_dark",
        paper_bgcolor="#0d1117",
        xaxis_title="Ticker",
        yaxis_title="P&L",
        height=350,
    )

    chart_col, table_col = st.columns([1, 1])
    with chart_col:
        st.plotly_chart(fig_pie, use_container_width=True)
    with table_col:
        st.plotly_chart(fig_pnl, use_container_width=True)

    # Summary table
    display_cols = [c for c in ["broker", "ticker", "name", "industry", "qty",
                                 "avg_cost", "mkt_value", "pnl", "pe_ratio", "roe"]
                    if c in enriched.columns]
    st.dataframe(
        enriched[display_cols].style.format({
            "avg_cost":  "{:.2f}",
            "mkt_value": "{:,.0f}",
            "pnl":       "{:+,.2f}",
        }).applymap(
            lambda v: "color: #26a69a" if isinstance(v, (int, float)) and v > 0
                      else ("color: #ef5350" if isinstance(v, (int, float)) and v < 0 else ""),
            subset=["pnl"],
        ),
        use_container_width=True,
        hide_index=True,
    )

# ── Quick stats ───────────────────────────────────────────────────────────────
st.divider()
tw_sigs = 0
us_sigs = 0
try:
    from dashboard.data_helpers import load_signals
    tw_df = load_signals("TW")
    us_df = load_signals("US")
    tw_sigs = len(tw_df)
    us_sigs = len(us_df)
except Exception:
    pass

q_cols = st.columns(4)
q_cols[0].metric("TW Signals Today",  tw_sigs)
q_cols[1].metric("US Signals Today",  us_sigs)
q_cols[2].metric("Open Positions",    len(pos_df) if not pos_df.empty else 0)
q_cols[3].metric("Connected Brokers", len(connected))
