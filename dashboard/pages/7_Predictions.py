"""
Prediction Win-Rate Dashboard — track how well the mean-reversion signals perform.

Tabs:
  1. Overview    — overall win rate, avg return, equity curve
  2. By Score    — win rate segmented by signal score bracket
  3. By Ticker   — per-ticker performance table + bar chart
  4. History     — full log, filterable, colour-coded outcome
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

from dashboard.data_helpers import BASE_DIR

st.set_page_config(page_title="Predictions", page_icon="🎯", layout="wide")
st.title("🎯 Prediction Win-Rate Tracker")
st.caption("Mean-reversion signal performance — entry at signal-day close, exit at next-day open")

# ── Load history ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=120, show_spinner="Loading prediction history…")
def _load() -> pd.DataFrame:
    p = BASE_DIR / "data" / "predictions" / "prediction_history.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, dtype={"ticker": str, "market": str, "status": str})
    for col in ["entry_price", "score", "RSI", "bias", "vol_ratio",
                "target_open", "target_close", "open_return_pct", "close_return_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["win_open", "win_close"]:
        if col in df.columns:
            df[col] = df[col].map({"True": True, "False": False, True: True, False: False})
    df["signal_date"] = pd.to_datetime(df["signal_date"], errors="coerce")
    return df


all_df = _load()

if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

if all_df.empty:
    st.info(
        "No prediction history yet. Run `python master_run.py` on a trading day to start recording signals.\n\n"
        "Outcomes are automatically resolved on the next run after the target date passes."
    )
    st.stop()

resolved = all_df[all_df["status"] == "resolved"].copy()
pending  = all_df[all_df["status"] == "pending"]
no_data  = all_df[all_df["status"] == "no_data"]

# ── Market filter ─────────────────────────────────────────────────────────────
markets = ["All"] + sorted(all_df["market"].dropna().unique().tolist())
mkt_sel = st.selectbox("Market", markets, horizontal=True if hasattr(st, "pills") else False)
if mkt_sel != "All":
    resolved = resolved[resolved["market"] == mkt_sel]

st.divider()

# ── KPI strip ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)
n = len(resolved)
if n > 0:
    wr_open  = resolved["win_open"].sum()  / n * 100
    wr_close = resolved["win_close"].sum() / n * 100
    avg_open  = resolved["open_return_pct"].mean()
    avg_close = resolved["close_return_pct"].mean()
else:
    wr_open = wr_close = avg_open = avg_close = 0.0

k1.metric("Resolved",      f"{n}")
k2.metric("Pending",       f"{len(pending)}")
k3.metric("Win Rate (Open)",  f"{wr_open:.1f}%",  help="Next-day open > entry close")
k4.metric("Win Rate (Close)", f"{wr_close:.1f}%", help="Next-day close > entry close")
k5.metric("Avg Open Return",  f"{avg_open:+.2f}%")
k6.metric("Avg Close Return", f"{avg_close:+.2f}%")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
tab_ov, tab_score, tab_ticker, tab_hist = st.tabs([
    "📈 Overview", "⭐ By Score", "🏷️ By Ticker", "📋 History"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Overview
# ══════════════════════════════════════════════════════════════════════════════
with tab_ov:
    if resolved.empty:
        st.info("No resolved predictions yet.")
    else:
        # Cumulative return curve (open exit)
        res_sorted = resolved.sort_values("signal_date").copy()
        res_sorted["cum_return"] = res_sorted["open_return_pct"].cumsum()

        fig_eq = px.line(
            res_sorted,
            x="signal_date",
            y="cum_return",
            color="market",
            title="Cumulative Return (open exit, equal-weighted)",
            labels={"signal_date": "Date", "cum_return": "Cumulative Return %"},
            template="plotly_dark",
            color_discrete_map={"TW": "#00b4d8", "US": "#f77f00"},
        )
        fig_eq.add_hline(y=0, line=dict(color="#888", dash="dash", width=1))
        fig_eq.update_layout(paper_bgcolor="#0d1117", height=320)
        st.plotly_chart(fig_eq, use_container_width=True)

        # Return distribution histogram
        fig_dist = px.histogram(
            resolved,
            x="open_return_pct",
            color="win_open",
            nbins=40,
            title="Return Distribution (open exit)",
            labels={"open_return_pct": "Open Return %", "win_open": "Win"},
            color_discrete_map={True: "#00e676", False: "#ef5350"},
            template="plotly_dark",
        )
        fig_dist.add_vline(x=0, line=dict(color="#888", dash="dash", width=1))
        fig_dist.update_layout(paper_bgcolor="#0d1117", height=280)
        st.plotly_chart(fig_dist, use_container_width=True)

        # Monthly win rate heatmap
        res_sorted["month"] = res_sorted["signal_date"].dt.to_period("M").astype(str)
        monthly = (
            res_sorted.groupby("month")
            .agg(
                trades=("win_open", "count"),
                wins=("win_open", "sum"),
                avg_ret=("open_return_pct", "mean"),
            )
            .reset_index()
        )
        monthly["win_rate"] = monthly["wins"] / monthly["trades"] * 100
        if not monthly.empty:
            st.markdown("#### Monthly Performance")
            st.dataframe(
                monthly.style.format({
                    "win_rate": "{:.1f}%",
                    "avg_ret":  "{:+.2f}%",
                }).background_gradient(subset=["win_rate"], cmap="RdYlGn", vmin=0, vmax=100),
                use_container_width=True,
                hide_index=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — By Score Bracket
# ══════════════════════════════════════════════════════════════════════════════
with tab_score:
    if resolved.empty:
        st.info("No resolved predictions yet.")
    else:
        bins   = [0, 2, 4, 6, 8, 10.01]
        labels = ["0–2", "2–4", "4–6", "6–8", "8–10"]
        resolved["score_bin"] = pd.cut(resolved["score"], bins=bins, labels=labels, right=False)

        score_stats = (
            resolved.groupby("score_bin", observed=True)
            .agg(
                trades=("win_open", "count"),
                wins=("win_open", "sum"),
                avg_open_ret=("open_return_pct", "mean"),
                avg_close_ret=("close_return_pct", "mean"),
            )
            .reset_index()
        )
        score_stats["win_rate"] = score_stats["wins"] / score_stats["trades"] * 100

        fig_sc = go.Figure()
        fig_sc.add_trace(go.Bar(
            x=score_stats["score_bin"].astype(str),
            y=score_stats["win_rate"],
            marker_color=[
                "#00e676" if v >= 60 else ("#ffa726" if v >= 50 else "#ef5350")
                for v in score_stats["win_rate"]
            ],
            text=[f"{v:.1f}%<br>({n:.0f})" for v, n in
                  zip(score_stats["win_rate"], score_stats["trades"])],
            textposition="outside",
        ))
        fig_sc.add_hline(y=50, line=dict(color="#888", dash="dash", width=1),
                         annotation_text="50% breakeven")
        fig_sc.update_layout(
            title="Win Rate by Signal Score Bracket (open exit)",
            xaxis_title="Score",
            yaxis_title="Win Rate %",
            yaxis_range=[0, 105],
            template="plotly_dark",
            paper_bgcolor="#0d1117",
            height=360,
        )
        st.plotly_chart(fig_sc, use_container_width=True)

        st.dataframe(
            score_stats.style.format({
                "win_rate":      "{:.1f}%",
                "avg_open_ret":  "{:+.2f}%",
                "avg_close_ret": "{:+.2f}%",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # RSI bracket analysis
        st.markdown("#### Win Rate by RSI at Signal")
        rsi_bins   = [0, 20, 25, 30, 35.01]
        rsi_labels = ["<20", "20–25", "25–30", "30–35"]
        resolved["rsi_bin"] = pd.cut(resolved["RSI"], bins=rsi_bins, labels=rsi_labels, right=False)
        rsi_stats = (
            resolved.groupby("rsi_bin", observed=True)
            .agg(
                trades=("win_open", "count"),
                wins=("win_open", "sum"),
                avg_ret=("open_return_pct", "mean"),
            )
            .reset_index()
        )
        rsi_stats["win_rate"] = rsi_stats["wins"] / rsi_stats["trades"] * 100
        st.dataframe(
            rsi_stats.style.format({"win_rate": "{:.1f}%", "avg_ret": "{:+.2f}%"}),
            use_container_width=True,
            hide_index=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — By Ticker
# ══════════════════════════════════════════════════════════════════════════════
with tab_ticker:
    if resolved.empty:
        st.info("No resolved predictions yet.")
    else:
        ticker_stats = (
            resolved.groupby(["market", "ticker"])
            .agg(
                trades=("win_open", "count"),
                wins=("win_open", "sum"),
                avg_open_ret=("open_return_pct", "mean"),
                avg_close_ret=("close_return_pct", "mean"),
                avg_score=("score", "mean"),
                last_signal=("signal_date", "max"),
            )
            .reset_index()
        )
        ticker_stats["win_rate"] = ticker_stats["wins"] / ticker_stats["trades"] * 100
        ticker_stats = ticker_stats.sort_values("win_rate", ascending=False)

        min_trades = st.slider("Min trades to show", 1, 10, 2)
        ts = ticker_stats[ticker_stats["trades"] >= min_trades]

        if ts.empty:
            st.info(f"No tickers with ≥ {min_trades} resolved trades yet.")
        else:
            fig_tk = px.bar(
                ts.head(30),
                x="ticker",
                y="win_rate",
                color="market",
                color_discrete_map={"TW": "#00b4d8", "US": "#f77f00"},
                text=[f"{v:.0f}%" for v in ts.head(30)["win_rate"]],
                title=f"Win Rate by Ticker (top 30, ≥{min_trades} trades)",
                labels={"win_rate": "Win Rate %", "ticker": "Ticker"},
                template="plotly_dark",
            )
            fig_tk.add_hline(y=50, line=dict(color="#888", dash="dash", width=1))
            fig_tk.update_layout(paper_bgcolor="#0d1117", height=380)
            st.plotly_chart(fig_tk, use_container_width=True)

            st.dataframe(
                ts.style.format({
                    "win_rate":      "{:.1f}%",
                    "avg_open_ret":  "{:+.2f}%",
                    "avg_close_ret": "{:+.2f}%",
                    "avg_score":     "{:.1f}",
                }).background_gradient(subset=["win_rate"], cmap="RdYlGn", vmin=30, vmax=80),
                use_container_width=True,
                hide_index=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Full History Log
# ══════════════════════════════════════════════════════════════════════════════
with tab_hist:
    # Filter controls
    fc1, fc2, fc3 = st.columns([2, 2, 2])
    status_sel = fc1.multiselect("Status", ["resolved", "pending", "no_data"],
                                 default=["resolved", "pending"])
    market_sel = fc2.multiselect("Market", all_df["market"].dropna().unique().tolist(),
                                 default=all_df["market"].dropna().unique().tolist())

    if all_df["signal_date"].notna().any():
        min_d = all_df["signal_date"].min().date()
        max_d = all_df["signal_date"].max().date()
        date_range = fc3.date_input("Date range", value=(min_d, max_d))
    else:
        date_range = None

    mask = (
        all_df["status"].isin(status_sel) &
        all_df["market"].isin(market_sel)
    )
    if date_range and len(date_range) == 2:
        mask &= (
            (all_df["signal_date"].dt.date >= date_range[0]) &
            (all_df["signal_date"].dt.date <= date_range[1])
        )
    filtered = all_df[mask].sort_values("signal_date", ascending=False)

    st.caption(f"{len(filtered)} rows shown")

    display_cols = [c for c in [
        "signal_date", "market", "ticker", "score", "RSI", "bias",
        "entry_price", "target_date", "target_open",
        "open_return_pct", "win_open", "status",
    ] if c in filtered.columns]

    def _row_style(row):
        if row.get("status") == "resolved":
            if row.get("win_open") is True:
                return ["background-color: #1b3a1b"] * len(row)
            elif row.get("win_open") is False:
                return ["background-color: #3a1b1b"] * len(row)
        return [""] * len(row)

    styled = (
        filtered[display_cols]
        .style
        .apply(_row_style, axis=1)
        .format({
            "score":           "{:.1f}",
            "RSI":             "{:.1f}",
            "bias":            "{:.1f}%",
            "entry_price":     "{:.2f}",
            "target_open":     lambda v: f"{v:.2f}" if pd.notna(v) else "—",
            "open_return_pct": lambda v: f"{v:+.2f}%" if pd.notna(v) else "—",
        }, na_rep="—")
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Download button
    csv = filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Download CSV",
        data=csv,
        file_name="prediction_history.csv",
        mime="text/csv",
    )
