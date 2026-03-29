"""
Positions page — all open holdings across brokers, enriched with fundamentals.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.express as px
from dashboard.data_helpers import get_broker_manager, merge_positions_with_fundamentals

st.set_page_config(page_title="Positions", page_icon="📋", layout="wide")
st.title("📋 Open Positions")

mgr = get_broker_manager()

if st.button("🔄 Refresh"):
    st.cache_resource.clear()
    st.rerun()

pos_df = mgr.get_all_positions()

if pos_df.empty:
    st.info("No open positions found across connected brokers.")
    st.stop()

enriched = merge_positions_with_fundamentals(pos_df)

# ── Filters ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Filters")
    broker_filter = st.multiselect(
        "Broker",
        options=enriched["broker"].unique().tolist(),
        default=enriched["broker"].unique().tolist(),
    )
    show_pnl_only = st.checkbox("Show losing positions only", value=False)

filtered = enriched[enriched["broker"].isin(broker_filter)].copy()
if show_pnl_only:
    filtered = filtered[filtered["pnl"] < 0]

# ── KPI row ───────────────────────────────────────────────────────────────────
total_val  = filtered["mkt_value"].sum()
total_pnl  = filtered["pnl"].sum()
n_pos      = len(filtered)
n_winning  = int((filtered["pnl"] > 0).sum())

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Market Value", f"{total_val:,.0f}")
k2.metric("Total Unrealized P&L", f"{total_pnl:+,.2f}",
          delta_color="normal", delta=f"{total_pnl:+.2f}")
k3.metric("# Positions", n_pos)
k4.metric("Winning / Total", f"{n_winning} / {n_pos}")

st.divider()

# ── Allocation breakdown chart ────────────────────────────────────────────────
if "industry" in filtered.columns:
    ind_grouped = (
        filtered.dropna(subset=["industry"])
        .groupby("industry")["mkt_value"].sum()
        .reset_index()
        .sort_values("mkt_value", ascending=False)
    )
    fig = px.bar(
        ind_grouped,
        x="industry",
        y="mkt_value",
        title="Market Value by Industry",
        labels={"mkt_value": "Market Value", "industry": "Industry"},
        color="mkt_value",
        color_continuous_scale="teal",
        template="plotly_dark",
    )
    fig.update_layout(paper_bgcolor="#0d1117", showlegend=False, height=300)
    st.plotly_chart(fig, use_container_width=True)

# ── Positions table ───────────────────────────────────────────────────────────
display_cols = [c for c in [
    "broker", "ticker", "name", "industry",
    "qty", "avg_cost", "mkt_value", "pnl",
    "pe_ratio", "roe", "target_price",
] if c in filtered.columns]

def _color_pnl(val):
    if not isinstance(val, (int, float)):
        return ""
    return "color: #26a69a; font-weight: bold" if val > 0 else "color: #ef5350; font-weight: bold"

styled = (
    filtered[display_cols]
    .sort_values("mkt_value", ascending=False)
    .style
    .format({
        "avg_cost":    "{:.2f}",
        "mkt_value":   "{:,.0f}",
        "pnl":         "{:+,.2f}",
        "pe_ratio":    lambda x: f"{x:.1f}" if str(x) not in ("N/A", "nan") else "N/A",
        "roe":         lambda x: f"{float(x)*100:.1f}%" if str(x) not in ("N/A", "nan") else "N/A",
    }, na_rep="N/A")
    .applymap(_color_pnl, subset=["pnl"])
)

st.dataframe(styled, use_container_width=True, hide_index=True)
st.caption(f"{len(filtered)} positions shown")
