"""
10_Market_Oracle.py — TAIEX Market Oracle Dashboard

Real-time bull/bear prediction with live scoring and historical stats.
Auto-refreshes every 5 minutes when enabled.
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Path setup ────────────────────────────────────────────────────────────────
DASHBOARD_DIR = Path(__file__).resolve().parent.parent
BASE_DIR       = DASHBOARD_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tws.index_tracker import (
    compute_prediction,
    get_taiex_live,
    oracle_stats,
    save_prediction,
    _load_history,
)

st.set_page_config(
    page_title="Market Oracle",
    page_icon="🔮",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _direction_badge(direction: str, size: int = 48) -> str:
    if direction == "Bull":
        return f'<span style="font-size:{size}px">🟢</span> <b style="font-size:{size//2}px;color:#26a69a">多方 BULL</b>'
    return f'<span style="font-size:{size}px">🔴</span> <b style="font-size:{size//2}px;color:#ef5350">空方 BEAR</b>'


def _factor_label(name: str) -> str:
    return {
        "spx_overnight":  "SPX夜盤報酬",
        "taiex_momentum": "台股前日動能",
        "vix_fear":       "VIX恐慌指數",
        "signal_count":   "超跌訊號數",
        "tw_win_rate":    "近期TW勝率",
    }.get(name, name)


def _factor_unit(name: str) -> str:
    return {
        "spx_overnight":  "%",
        "taiex_momentum": "%",
        "vix_fear":       "",
        "signal_count":   "檔",
        "tw_win_rate":    "%",
    }.get(name, "")


def _bull_threshold_desc(name: str) -> str:
    return {
        "spx_overnight":  "> +0.3%",
        "taiex_momentum": "> +0.5%",
        "vix_fear":       "< 20",
        "signal_count":   "≥ 3",
        "tw_win_rate":    "> 55%",
    }.get(name, "")


def _is_tw_market_open() -> bool:
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    return now.weekday() < 5 and 9 <= now.hour < 14


# ─────────────────────────────────────────────────────────────────────────────
# Auto-refresh
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    auto_refresh = st.toggle("自動更新 (每5分)", value=False, key="auto_refresh")
    if auto_refresh:
        st.caption("下次更新: 5分鐘後")

if auto_refresh:
    time.sleep(300)
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Page header
# ─────────────────────────────────────────────────────────────────────────────

st.title("🔮 台股大盤 Oracle")
st.caption("每日多空預測 · 命中率 · 積分追蹤")

# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_today, tab_history, tab_stats = st.tabs(["今日預測", "歷史戰績", "統計分析"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: Today's prediction
# ─────────────────────────────────────────────────────────────────────────────

with tab_today:
    today_str = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")

    # Load or compute today's prediction
    history = _load_history(str(BASE_DIR))
    today_rows = history[history["date"] == today_str] if not history.empty else pd.DataFrame()

    col_pred, col_live = st.columns([1, 1])

    # ── Prediction card ────────────────────────────────────────────────────
    with col_pred:
        if today_rows.empty:
            st.info("今日預測尚未生成。點擊下方按鈕立即生成。")
            if st.button("🔮 生成今日預測", type="primary"):
                with st.spinner("計算中..."):
                    try:
                        pred = compute_prediction(str(BASE_DIR))
                        save_prediction(str(BASE_DIR), pred)
                        st.success("預測已生成！重新整理以查看。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"生成失敗: {e}")
        else:
            row = today_rows.iloc[-1]
            direction      = row.get("direction", "?")
            confidence_pct = row.get("confidence_pct", 0)
            status         = row.get("status", "pending")

            st.markdown(f"### {today_str}")
            st.markdown(_direction_badge(direction), unsafe_allow_html=True)

            st.metric("信心指數", f"{confidence_pct:.1f}%")

            if status == "resolved":
                change_pts = float(row.get("taiex_change_pts") or 0)
                score_pts  = float(row.get("score_pts") or 0)
                is_correct = row.get("is_correct")
                outcome    = "✅ 命中" if is_correct else "❌ 未命中"
                score_color = "green" if score_pts >= 0 else "red"
                st.markdown(
                    f"**結果**: {outcome}  \n"
                    f"大盤變動: **{change_pts:+.0f}點**  \n"
                    f"本日得分: <span style='color:{score_color};font-size:24px'><b>{score_pts:+.0f}分</b></span>",
                    unsafe_allow_html=True,
                )
            else:
                st.info("今日預測進行中 — 盤後自動結算")

            # Factor breakdown
            try:
                factors = json.loads(str(row.get("factors_json") or "{}"))
                if factors:
                    st.markdown("---")
                    st.markdown("**因子分析**")
                    weights = {"spx_overnight": 0.30, "taiex_momentum": 0.25,
                               "vix_fear": 0.20, "signal_count": 0.15, "tw_win_rate": 0.10}
                    rows_data = []
                    for fname, finfo in factors.items():
                        val   = finfo.get("value")
                        is_bull = finfo.get("bull", False)
                        val_str = f"{val}{_factor_unit(fname)}" if val is not None else "N/A"
                        rows_data.append({
                            "因子": _factor_label(fname),
                            "數值": val_str,
                            "多空": "🟢多" if is_bull else "🔴空",
                            "門檻": _bull_threshold_desc(fname),
                            "權重": f"{weights.get(fname, 0)*100:.0f}%",
                        })
                    st.dataframe(
                        pd.DataFrame(rows_data),
                        use_container_width=True,
                        hide_index=True,
                    )
            except Exception:
                pass

    # ── Live TAIEX ─────────────────────────────────────────────────────────
    with col_live:
        st.markdown("### 即時大盤")
        with st.spinner("載入中..."):
            live = get_taiex_live()

        if live["current_level"] is not None:
            change_pts = live["change_pts"] or 0
            change_pct = live["change_pct"] or 0
            lvl_color  = "green" if change_pts >= 0 else "red"
            arrow      = "▲" if change_pts >= 0 else "▼"
            st.metric(
                label=f"台灣加權指數 ({live['last_updated']} TST)",
                value=f"{live['current_level']:,.1f}",
                delta=f"{change_pts:+.1f}點 ({change_pct:+.2f}%)",
                delta_color="normal",
            )

            # Intraday chart
            intra = live["intraday_df"]
            if not intra.empty:
                fig = go.Figure()
                # Color based on day change
                colors = ["#26a69a" if c >= (intra["Close"].iloc[0]) else "#ef5350"
                          for c in intra["Close"]]
                fig.add_trace(go.Scatter(
                    x=intra.index,
                    y=intra["Close"],
                    mode="lines",
                    line=dict(color="#26a69a" if change_pts >= 0 else "#ef5350", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(38,166,154,0.10)" if change_pts >= 0 else "rgba(239,83,80,0.10)",
                    name="TAIEX",
                ))
                fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="#0d1117",
                    plot_bgcolor="#0d1117",
                    margin=dict(l=10, r=10, t=10, b=30),
                    height=250,
                    showlegend=False,
                    xaxis=dict(gridcolor="#2a2a2a"),
                    yaxis=dict(gridcolor="#2a2a2a"),
                )
                st.plotly_chart(fig, use_container_width=True)

            # Potential score
            if not today_rows.empty and today_rows.iloc[-1].get("status") == "pending":
                pot_score = abs(change_pts) * 10
                st.markdown(
                    f"**潛在積分** (若方向正確): "
                    f"<span style='font-size:22px;color:#ffa726'><b>+{pot_score:.0f}分</b></span>",
                    unsafe_allow_html=True,
                )
        else:
            st.warning("無法取得即時大盤資料 (yfinance 15分鐘延遲，盤中才有資料)")

    # Stats ribbon
    stats = oracle_stats(str(BASE_DIR))
    if stats["total"] > 0:
        st.markdown("---")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("總預測數", stats["total"])
        k2.metric("勝率", f"{stats['win_rate_pct']:.1f}%", f"{stats['wins']}勝{stats['losses']}負")
        k3.metric("累計積分", f"{stats['cumulative_score']:+,.0f}")
        k4.metric("連勝", stats["streak"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: History
# ─────────────────────────────────────────────────────────────────────────────

with tab_history:
    history = _load_history(str(BASE_DIR))
    resolved = history[history["status"] == "resolved"].copy() if not history.empty else pd.DataFrame()

    if resolved.empty:
        st.info("尚無已結算的預測紀錄。")
    else:
        resolved = resolved.sort_values("date")
        resolved["score_pts"]       = pd.to_numeric(resolved["score_pts"],       errors="coerce")
        resolved["cumulative_score"] = pd.to_numeric(resolved["cumulative_score"], errors="coerce")
        resolved["taiex_change_pts"] = pd.to_numeric(resolved["taiex_change_pts"], errors="coerce")

        # KPI row
        stats = oracle_stats(str(BASE_DIR))
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("勝率",      f"{stats['win_rate_pct']:.1f}%")
        k2.metric("累計積分",  f"{stats['cumulative_score']:+,.0f}")
        k3.metric("日均積分",  f"{stats['avg_score_per_day']:+.0f}")
        k4.metric("最佳單日",  f"{resolved['score_pts'].max():+.0f}")
        k5.metric("最差單日",  f"{resolved['score_pts'].min():+.0f}")

        # Score bar chart (green=correct, red=wrong)
        bar_colors = [
            "#26a69a" if v >= 0 else "#ef5350"
            for v in resolved["score_pts"].fillna(0)
        ]
        fig_bar = go.Figure(go.Bar(
            x=resolved["date"],
            y=resolved["score_pts"],
            marker_color=bar_colors,
            text=[f"{v:+.0f}" for v in resolved["score_pts"].fillna(0)],
            textposition="outside",
        ))
        fig_bar.update_layout(
            title="每日得分",
            template="plotly_dark",
            paper_bgcolor="#0d1117",
            plot_bgcolor="#0d1117",
            height=280,
            margin=dict(t=40, b=20),
            xaxis=dict(gridcolor="#2a2a2a"),
            yaxis=dict(gridcolor="#2a2a2a", zeroline=True, zerolinecolor="#555"),
            showlegend=False,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # Cumulative score line chart
        fig_cum = go.Figure(go.Scatter(
            x=resolved["date"],
            y=resolved["cumulative_score"],
            mode="lines+markers",
            line=dict(color="#ffa726", width=2),
            marker=dict(size=6),
            fill="tozeroy",
            fillcolor="rgba(255,167,38,0.1)",
        ))
        fig_cum.update_layout(
            title="累計積分走勢",
            template="plotly_dark",
            paper_bgcolor="#0d1117",
            plot_bgcolor="#0d1117",
            height=260,
            margin=dict(t=40, b=20),
            xaxis=dict(gridcolor="#2a2a2a"),
            yaxis=dict(gridcolor="#2a2a2a", zeroline=True, zerolinecolor="#555"),
            showlegend=False,
        )
        st.plotly_chart(fig_cum, use_container_width=True)

        # Raw data table
        with st.expander("原始紀錄"):
            disp = resolved[["date", "direction", "confidence_pct",
                             "taiex_change_pts", "score_pts", "cumulative_score",
                             "is_correct"]].copy()
            disp.columns = ["日期", "方向", "信心%", "大盤變動(pts)", "得分", "累計", "命中"]
            st.dataframe(disp, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: Stats
# ─────────────────────────────────────────────────────────────────────────────

with tab_stats:
    history = _load_history(str(BASE_DIR))
    resolved = history[history["status"] == "resolved"].copy() if not history.empty else pd.DataFrame()

    if resolved.empty or len(resolved) < 3:
        st.info("統計需要至少 3 筆已結算紀錄。")
    else:
        resolved["score_pts"] = pd.to_numeric(resolved["score_pts"], errors="coerce")
        resolved["is_correct"] = resolved["is_correct"].map(
            lambda x: True if str(x).lower() in ("true", "1") else False
        )
        resolved["dow"] = pd.to_datetime(resolved["date"]).dt.day_name()

        col_a, col_b = st.columns(2)

        # Win rate by direction
        with col_a:
            st.markdown("**方向勝率**")
            bull_rows = resolved[resolved["direction"] == "Bull"]
            bear_rows = resolved[resolved["direction"] == "Bear"]
            bull_wr   = bull_rows["is_correct"].mean() * 100 if len(bull_rows) else 0
            bear_wr   = bear_rows["is_correct"].mean() * 100 if len(bear_rows) else 0
            fig_dir = go.Figure(go.Bar(
                x=["🟢 多方 Bull", "🔴 空方 Bear"],
                y=[bull_wr, bear_wr],
                marker_color=["#26a69a", "#ef5350"],
                text=[f"{bull_wr:.1f}%  ({len(bull_rows)}次)", f"{bear_wr:.1f}%  ({len(bear_rows)}次)"],
                textposition="outside",
            ))
            fig_dir.update_layout(
                template="plotly_dark", paper_bgcolor="#0d1117",
                plot_bgcolor="#0d1117", height=260,
                margin=dict(t=10, b=20),
                yaxis=dict(range=[0, 110], gridcolor="#2a2a2a"),
                showlegend=False,
            )
            st.plotly_chart(fig_dir, use_container_width=True)

        # Win rate by day of week
        with col_b:
            st.markdown("**星期勝率**")
            dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            dow_labels = {"Monday": "一", "Tuesday": "二", "Wednesday": "三",
                          "Thursday": "四", "Friday": "五"}
            dow_wr = resolved.groupby("dow")["is_correct"].mean() * 100
            dow_wr = dow_wr.reindex([d for d in dow_order if d in dow_wr.index])
            fig_dow = go.Figure(go.Bar(
                x=[dow_labels.get(d, d) for d in dow_wr.index],
                y=dow_wr.values,
                marker_color="#42a5f5",
                text=[f"{v:.1f}%" for v in dow_wr.values],
                textposition="outside",
            ))
            fig_dow.update_layout(
                template="plotly_dark", paper_bgcolor="#0d1117",
                plot_bgcolor="#0d1117", height=260,
                margin=dict(t=10, b=20),
                yaxis=dict(range=[0, 110], gridcolor="#2a2a2a"),
                showlegend=False,
            )
            st.plotly_chart(fig_dow, use_container_width=True)

        # Score distribution
        st.markdown("**得分分布**")
        fig_hist = go.Figure(go.Histogram(
            x=resolved["score_pts"].dropna(),
            nbinsx=20,
            marker_color="#ab47bc",
        ))
        fig_hist.add_vline(x=0, line=dict(color="#ffa726", dash="dash", width=1.5))
        fig_hist.update_layout(
            template="plotly_dark", paper_bgcolor="#0d1117",
            plot_bgcolor="#0d1117", height=240,
            margin=dict(t=10, b=20),
            xaxis=dict(title="得分(分)", gridcolor="#2a2a2a"),
            yaxis=dict(title="頻次", gridcolor="#2a2a2a"),
            showlegend=False,
        )
        st.plotly_chart(fig_hist, use_container_width=True)
