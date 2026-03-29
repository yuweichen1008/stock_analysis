"""
Backtest page — run historical backtests using the existing Backtester engine.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
from dashboard.data_helpers import BASE_DIR

st.set_page_config(page_title="Backtest", page_icon="🔬", layout="wide")
st.title("🔬 Backtest")
st.caption("Run the mean-reversion strategy on historical OHLCV data.")

# ── Parameter form ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Backtest Parameters")

    # Ticker input
    ticker_input = st.text_area(
        "Tickers (one per line or comma-separated)",
        value="2330\n2317\n2454\n2308",
        height=120,
        help="Taiwan 4-digit codes or US symbols with downloaded OHLCV data",
    )

    start_date = st.date_input("Start Date",  value=pd.Timestamp("2025-01-01").date())
    end_date   = st.date_input("End Date",    value=pd.Timestamp.today().date())

    st.subheader("Strategy Parameters")
    holding_days    = st.slider("Max holding days",    1,  30, 5)
    stop_loss_pct   = st.slider("Stop loss %",         1,  20, 5) / 100
    take_profit_pct = st.slider("Take profit %",       1,  50, 10) / 100
    commission_pct  = st.number_input("Commission %", min_value=0.0, max_value=2.0,
                                      value=0.285, step=0.001) / 100

    run_button = st.button("▶️ Run Backtest", type="primary")

# ── Main area ─────────────────────────────────────────────────────────────────
if not run_button:
    st.info("Configure parameters in the sidebar and click **Run Backtest**.")
    st.stop()

# Parse tickers
raw = ticker_input.replace(",", "\n").split("\n")
tickers = [t.strip() for t in raw if t.strip()]

if not tickers:
    st.error("Please enter at least one ticker.")
    st.stop()

# ── Run ───────────────────────────────────────────────────────────────────────
with st.spinner(f"Running backtest on {len(tickers)} ticker(s)…"):
    try:
        from backtester import Backtester
        bt = Backtester(
            start_date=str(start_date),
            end_date=str(end_date),
        )
        trades_df, summary = bt.run(
            tickers           = tickers,
            holding_days      = holding_days,
            stop_loss_pct     = stop_loss_pct,
            take_profit_pct   = take_profit_pct,
            commission_pct    = commission_pct,
        )
    except Exception as e:
        st.error(f"Backtest failed: {e}")
        st.stop()

if trades_df is None or (isinstance(trades_df, pd.DataFrame) and trades_df.empty):
    st.warning("No trades were generated. Try adjusting the date range or parameters.")
    st.stop()

# Normalise: Backtester.run() might return (df, dict) or just df depending on version
if isinstance(summary, pd.DataFrame) and isinstance(trades_df, dict):
    trades_df, summary = summary, trades_df

# ── Summary metrics ───────────────────────────────────────────────────────────
st.subheader("Performance Summary")
if isinstance(summary, dict) and summary:
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Trades",    summary.get("total_trades",  "N/A"))
    m2.metric("Win Rate",        f"{float(summary.get('win_rate', 0))*100:.1f}%" if summary.get('win_rate') is not None else "N/A")
    m3.metric("Avg Profit %",    f"{float(summary.get('avg_profit_pct', 0)):+.2f}%" if summary.get('avg_profit_pct') is not None else "N/A")
    m4.metric("Total Profit",    f"{float(summary.get('total_profit', 0)):+,.0f}"  if summary.get('total_profit')  is not None else "N/A")
    m5.metric("Sharpe Ratio",    f"{float(summary.get('sharpe', 0)):.2f}"          if summary.get('sharpe')        is not None else "N/A")
    m6.metric("Max Drawdown",    f"{float(summary.get('max_drawdown', 0))*100:.1f}%" if summary.get('max_drawdown') is not None else "N/A")

st.divider()

# ── Equity curve ──────────────────────────────────────────────────────────────
if isinstance(trades_df, pd.DataFrame) and not trades_df.empty:
    # Try to build equity curve from cumulative profit
    profit_col = next((c for c in ["profit", "pnl", "net_profit"] if c in trades_df.columns), None)
    date_col   = next((c for c in ["exit_date", "entry_date", "date"] if c in trades_df.columns), None)

    if profit_col and date_col:
        eq = trades_df[[date_col, profit_col]].copy()
        eq[date_col] = pd.to_datetime(eq[date_col], errors="coerce")
        eq = eq.dropna().sort_values(date_col)
        eq["cumulative_profit"] = eq[profit_col].cumsum()

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=eq[date_col],
            y=eq["cumulative_profit"],
            fill="tozeroy",
            line=dict(color="#26a69a", width=2),
            name="Cumulative P&L",
        ))
        fig_eq.update_layout(
            title="Equity Curve (Cumulative P&L)",
            template="plotly_dark",
            paper_bgcolor="#0d1117",
            xaxis_title="Date",
            yaxis_title="Cumulative Profit",
            height=350,
        )
        st.plotly_chart(fig_eq, use_container_width=True)

    # ── Per-ticker win rate ───────────────────────────────────────────────────
    ticker_col = next((c for c in ["ticker", "symbol", "stock"] if c in trades_df.columns), None)
    if ticker_col and profit_col:
        by_ticker = (
            trades_df.groupby(ticker_col)[profit_col]
            .agg(trades="count", total=sum, wins=lambda x: (x > 0).sum())
            .reset_index()
        )
        by_ticker["win_rate"] = by_ticker["wins"] / by_ticker["trades"]
        by_ticker = by_ticker.sort_values("total", ascending=False)

        fig_bt = px.bar(
            by_ticker,
            x=ticker_col,
            y="total",
            color="win_rate",
            color_continuous_scale="RdYlGn",
            title="Total Profit by Ticker",
            labels={"total": "Total Profit", ticker_col: "Ticker", "win_rate": "Win Rate"},
            template="plotly_dark",
        )
        fig_bt.update_layout(paper_bgcolor="#0d1117", height=300)
        st.plotly_chart(fig_bt, use_container_width=True)

    # ── Trade log ─────────────────────────────────────────────────────────────
    st.subheader("Trade Log")
    st.dataframe(
        trades_df.sort_values(date_col if date_col else trades_df.columns[0], ascending=False),
        use_container_width=True,
        hide_index=True,
    )
