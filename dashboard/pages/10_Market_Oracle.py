"""
10_Market_Oracle.py — TAIEX Market Oracle Dashboard

Real-time bull/bear prediction · game scoring · backtesting simulator.
"""
import json
import os
import sys
import time
from datetime import datetime, date, timedelta
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
    SCORE_WIN, SCORE_LOSE,
    compute_prediction, save_prediction,
    get_taiex_live, oracle_stats,
    backtest_oracle, _load_history,
)

st.set_page_config(page_title="Market Oracle", page_icon="🔮", layout="wide")

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🔮 Market Oracle")
    auto_refresh = st.toggle("自動更新 (每5分)", value=False)
    if auto_refresh:
        st.caption("下次更新: 5分鐘後")
    st.markdown("---")
    st.markdown(f"**積分制度**")
    st.markdown(f"✅ 命中: **+{SCORE_WIN} pts**")
    st.markdown(f"❌ 未中: **{SCORE_LOSE} pts**")

if auto_refresh:
    time.sleep(300)
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

_FACTOR_LABELS = {
    "spx_overnight":  "SPX夜盤報酬",
    "taiex_momentum": "台股前日動能",
    "vix_fear":       "VIX恐慌指數",
    "signal_count":   "超跌訊號數",
    "tw_win_rate":    "近期TW勝率",
}
_FACTOR_UNITS = {
    "spx_overnight": "%", "taiex_momentum": "%",
    "vix_fear": "", "signal_count": "檔", "tw_win_rate": "%",
}
_THRESHOLD_DESC = {
    "spx_overnight":  "> +0.3%", "taiex_momentum": "> +0.5%",
    "vix_fear":       "< 20",    "signal_count":   "≥ 3",
    "tw_win_rate":    "> 55%",
}
_WEIGHTS = {"spx_overnight": 0.30, "taiex_momentum": 0.25,
            "vix_fear": 0.20, "signal_count": 0.15, "tw_win_rate": 0.10}


def _score_bar(score: float, max_pts: int = SCORE_WIN) -> str:
    """Return a visual filled bar proportional to score vs max."""
    pct = max(0, min(1, abs(score) / max(max_pts, 1)))
    filled = int(pct * 10)
    color  = "🟩" if score >= 0 else "🟥"
    return color * filled + "⬜" * (10 - filled)


def _is_tw_market_hours() -> bool:
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    return now.weekday() < 5 and 9 <= now.hour < 14


# ─────────────────────────────────────────────────────────────────────────────
# Page header
# ─────────────────────────────────────────────────────────────────────────────

st.title("🔮 台股大盤 Oracle")
st.caption("每日多空預測  ·  遊戲積分  ·  歷史回測")

tab_today, tab_history, tab_stats, tab_backtest = st.tabs([
    "🎯 今日預測", "📅 歷史戰績", "📊 統計分析", "🧪 回測模擬"
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: Today's prediction
# ─────────────────────────────────────────────────────────────────────────────

with tab_today:
    today_str = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
    history   = _load_history(str(BASE_DIR))
    today_rows = history[history["date"] == today_str] if not history.empty else pd.DataFrame()

    col_pred, col_live = st.columns([1, 1])

    # ── Prediction card ───────────────────────────────────────────────────────
    with col_pred:
        if today_rows.empty:
            st.info("今日預測尚未生成。")
            if st.button("🔮 生成今日預測", type="primary"):
                with st.spinner("計算中..."):
                    try:
                        pred = compute_prediction(str(BASE_DIR))
                        save_prediction(str(BASE_DIR), pred)
                        st.success("預測已生成！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"生成失敗: {e}")
        else:
            row        = today_rows.iloc[-1]
            direction  = row.get("direction", "?")
            conf       = float(row.get("confidence_pct") or 0)
            status     = row.get("status", "pending")

            # Direction badge
            if direction == "Bull":
                st.markdown(
                    f'<div style="text-align:center;padding:16px;border-radius:12px;'
                    f'background:rgba(38,166,154,0.15);border:1px solid #26a69a">'
                    f'<span style="font-size:48px">🟢</span><br>'
                    f'<b style="font-size:28px;color:#26a69a">多方 BULL</b></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="text-align:center;padding:16px;border-radius:12px;'
                    f'background:rgba(239,83,80,0.15);border:1px solid #ef5350">'
                    f'<span style="font-size:48px">🔴</span><br>'
                    f'<b style="font-size:28px;color:#ef5350">空方 BEAR</b></div>',
                    unsafe_allow_html=True,
                )

            st.metric("信心指數", f"{conf:.0f}%", label_visibility="visible")

            if status == "resolved":
                change_pts = float(row.get("taiex_change_pts") or 0)
                score_pts  = float(row.get("score_pts") or 0)
                is_correct = str(row.get("is_correct", "")).lower() in ("true", "1")
                score_color = "#26a69a" if score_pts >= 0 else "#ef5350"
                outcome     = "✅ 命中" if is_correct else "❌ 未命中"
                st.markdown(
                    f"**今日結果:** {outcome}  \n"
                    f"大盤: **{change_pts:+.0f} pts**  \n"
                    f'<span style="font-size:26px;color:{score_color}"><b>{score_pts:+.0f} 分</b></span>',
                    unsafe_allow_html=True,
                )
            else:
                st.info(f"盤後自動結算  ·  命中得 +{SCORE_WIN}  ·  未中得 {SCORE_LOSE}")

            # Factor breakdown
            try:
                factors = json.loads(str(row.get("factors_json") or "{}"))
                if factors:
                    st.markdown("---")
                    st.markdown("**因子分析**")
                    tbl = []
                    for fname, finfo in factors.items():
                        val   = finfo.get("value")
                        bull  = finfo.get("bull", False)
                        unit  = _FACTOR_UNITS.get(fname, "")
                        tbl.append({
                            "因子": _FACTOR_LABELS.get(fname, fname),
                            "數值": f"{val}{unit}" if val is not None else "N/A",
                            "門檻": _THRESHOLD_DESC.get(fname, ""),
                            "投票": "🟢 多" if bull else "🔴 空",
                            "權重": f"{_WEIGHTS.get(fname, 0)*100:.0f}%",
                        })
                    st.dataframe(pd.DataFrame(tbl), use_container_width=True, hide_index=True)
            except Exception:
                pass

    # ── Live TAIEX ───────────────────────────────────────────────────────────
    with col_live:
        st.markdown(f"### 即時大盤 ({today_str})")
        with st.spinner("載入..."):
            live = get_taiex_live()

        if live["current_level"] is not None:
            chg = live["change_pts"] or 0
            pct = live["change_pct"] or 0
            st.metric(
                label=f"台灣加權指數 ({live['last_updated']} TST, 15min延遲)",
                value=f"{live['current_level']:,.1f}",
                delta=f"{chg:+.1f}pts ({pct:+.2f}%)",
            )

            intra = live["intraday_df"]
            if not intra.empty:
                base_price = float(intra["Open"].iloc[0])
                line_color = "#26a69a" if chg >= 0 else "#ef5350"
                fill_color = "rgba(38,166,154,0.10)" if chg >= 0 else "rgba(239,83,80,0.10)"
                fig = go.Figure(go.Scatter(
                    x=intra.index, y=intra["Close"],
                    mode="lines", line=dict(color=line_color, width=2),
                    fill="tozeroy", fillcolor=fill_color, name="TAIEX",
                ))
                fig.add_hline(y=base_price,
                              line=dict(color="#aaa", dash="dot", width=1),
                              annotation_text="開盤", annotation_font=dict(color="#aaa", size=10))
                fig.update_layout(
                    template="plotly_dark", paper_bgcolor="#0d1117",
                    plot_bgcolor="#0d1117", height=260,
                    margin=dict(l=10, r=10, t=10, b=30), showlegend=False,
                    xaxis=dict(gridcolor="#2a2a2a"),
                    yaxis=dict(gridcolor="#2a2a2a"),
                )
                st.plotly_chart(fig, use_container_width=True)

            # Potential score
            if not today_rows.empty and today_rows.iloc[-1].get("status") == "pending":
                direction_now = today_rows.iloc[-1].get("direction", "?")
                actual_dir    = "Bull" if chg > 0 else "Bear"
                leading       = direction_now == actual_dir
                lead_text     = "目前領先 🎯" if leading else "目前落後 😬"
                lead_color    = "#26a69a" if leading else "#ef5350"
                st.markdown(
                    f"**{lead_text}**  ·  待結算積分: "
                    f'<span style="font-size:20px;color:{lead_color}">'
                    f'<b>{"+" if leading else ""}{SCORE_WIN if leading else SCORE_LOSE} 分</b></span>',
                    unsafe_allow_html=True,
                )
        else:
            st.warning("無即時資料 (盤中或盤後才有 yfinance 數據)")

    # Stats ribbon
    stats = oracle_stats(str(BASE_DIR))
    if stats["total"] > 0:
        st.markdown("---")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("已預測", stats["total"])
        k2.metric("勝率",   f"{stats['win_rate_pct']:.1f}%")
        k3.metric("累計積分", f"{stats['cumulative_score']:+,.0f}")
        k4.metric("日均",   f"{stats['avg_score_per_day']:+.0f}")
        k5.metric("連勝",   stats["streak"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: History
# ─────────────────────────────────────────────────────────────────────────────

with tab_history:
    history  = _load_history(str(BASE_DIR))
    resolved = history[history["status"] == "resolved"].copy() if not history.empty else pd.DataFrame()

    if resolved.empty:
        st.info("尚無已結算紀錄。")
    else:
        resolved = resolved.sort_values("date").reset_index(drop=True)
        resolved["score_pts"]        = pd.to_numeric(resolved["score_pts"],        errors="coerce")
        resolved["cumulative_score"] = pd.to_numeric(resolved["cumulative_score"], errors="coerce")
        resolved["taiex_change_pts"] = pd.to_numeric(resolved["taiex_change_pts"], errors="coerce")
        resolved["is_correct_bool"]  = resolved["is_correct"].map(
            lambda x: str(x).lower() in ("true", "1")
        )

        # KPIs
        stats = oracle_stats(str(BASE_DIR))
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("勝率",   f"{stats['win_rate_pct']:.1f}%", f"{stats['wins']}W/{stats['losses']}L")
        k2.metric("累計積分", f"{stats['cumulative_score']:+,.0f}")
        k3.metric("日均積分", f"{stats['avg_score_per_day']:+.0f}")
        k4.metric("最佳",   f"+{int(SCORE_WIN)}")
        k5.metric("最差",   f"{int(SCORE_LOSE)}")

        # Per-day score bar chart
        bar_colors = ["#26a69a" if v else "#ef5350" for v in resolved["is_correct_bool"]]
        fig_bar = go.Figure(go.Bar(
            x=resolved["date"], y=resolved["score_pts"],
            marker_color=bar_colors,
            text=[f"{'+' if v >= 0 else ''}{int(v)}" for v in resolved["score_pts"].fillna(0)],
            textposition="outside",
        ))
        fig_bar.update_layout(
            title="每日積分", template="plotly_dark",
            paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", height=280,
            margin=dict(t=40, b=20),
            xaxis=dict(gridcolor="#2a2a2a"),
            yaxis=dict(gridcolor="#2a2a2a", zeroline=True, zerolinecolor="#555"),
            showlegend=False,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        # Cumulative score line
        fig_cum = go.Figure(go.Scatter(
            x=resolved["date"], y=resolved["cumulative_score"],
            mode="lines+markers",
            line=dict(color="#ffa726", width=2.5),
            marker=dict(size=7, color=["#26a69a" if v else "#ef5350"
                                       for v in resolved["is_correct_bool"]]),
            fill="tozeroy", fillcolor="rgba(255,167,38,0.08)",
        ))
        fig_cum.add_hline(y=0, line=dict(color="#555", dash="dot", width=1))
        fig_cum.update_layout(
            title="累計積分走勢", template="plotly_dark",
            paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", height=260,
            margin=dict(t=40, b=20),
            xaxis=dict(gridcolor="#2a2a2a"),
            yaxis=dict(gridcolor="#2a2a2a"),
            showlegend=False,
        )
        st.plotly_chart(fig_cum, use_container_width=True)

        # Raw table
        with st.expander("原始紀錄"):
            disp = resolved[["date", "direction", "confidence_pct",
                             "taiex_change_pts", "score_pts", "cumulative_score",
                             "is_correct_bool"]].copy()
            disp.columns = ["日期", "預測", "信心%", "大盤變動pts", "積分", "累計", "命中"]
            st.dataframe(disp, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: Stats
# ─────────────────────────────────────────────────────────────────────────────

with tab_stats:
    history  = _load_history(str(BASE_DIR))
    resolved = history[history["status"] == "resolved"].copy() if not history.empty else pd.DataFrame()

    if resolved.empty or len(resolved) < 3:
        st.info("統計需要至少 3 筆已結算紀錄。")
    else:
        resolved["score_pts"]   = pd.to_numeric(resolved["score_pts"], errors="coerce")
        resolved["is_correct_b"] = resolved["is_correct"].map(
            lambda x: str(x).lower() in ("true", "1")
        )
        resolved["dow"] = pd.to_datetime(resolved["date"]).dt.day_name()

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("**方向勝率**")
            bull_rows = resolved[resolved["direction"] == "Bull"]
            bear_rows = resolved[resolved["direction"] == "Bear"]
            bull_wr   = bull_rows["is_correct_b"].mean() * 100 if len(bull_rows) else 0
            bear_wr   = bear_rows["is_correct_b"].mean() * 100 if len(bear_rows) else 0
            fig_dir = go.Figure(go.Bar(
                x=["🟢 多方 Bull", "🔴 空方 Bear"],
                y=[bull_wr, bear_wr],
                marker_color=["#26a69a", "#ef5350"],
                text=[f"{bull_wr:.1f}% ({len(bull_rows)}次)", f"{bear_wr:.1f}% ({len(bear_rows)}次)"],
                textposition="outside",
            ))
            fig_dir.update_layout(
                template="plotly_dark", paper_bgcolor="#0d1117",
                plot_bgcolor="#0d1117", height=280, margin=dict(t=10, b=20),
                yaxis=dict(range=[0, 115], gridcolor="#2a2a2a"), showlegend=False,
            )
            st.plotly_chart(fig_dir, use_container_width=True)

        with col_b:
            st.markdown("**星期勝率**")
            dow_order  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            dow_labels = {"Monday": "一", "Tuesday": "二", "Wednesday": "三",
                          "Thursday": "四", "Friday": "五"}
            dow_wr = resolved.groupby("dow")["is_correct_b"].mean() * 100
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
                plot_bgcolor="#0d1117", height=280, margin=dict(t=10, b=20),
                yaxis=dict(range=[0, 115], gridcolor="#2a2a2a"), showlegend=False,
            )
            st.plotly_chart(fig_dow, use_container_width=True)

        st.markdown("**得分分布**")
        fig_hist = go.Figure(go.Histogram(
            x=resolved["score_pts"].dropna(), nbinsx=10, marker_color="#ab47bc",
        ))
        fig_hist.add_vline(x=0, line=dict(color="#ffa726", dash="dash", width=1.5))
        fig_hist.update_layout(
            template="plotly_dark", paper_bgcolor="#0d1117",
            plot_bgcolor="#0d1117", height=220, margin=dict(t=10, b=20),
            xaxis=dict(title="積分", gridcolor="#2a2a2a"),
            yaxis=dict(title="次數", gridcolor="#2a2a2a"),
            showlegend=False,
        )
        st.plotly_chart(fig_hist, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: Backtesting
# ─────────────────────────────────────────────────────────────────────────────

with tab_backtest:
    st.markdown("### 🧪 策略回測模擬")
    st.caption(
        "使用歷史 TWII / SPX / VIX 數據，模擬多空預測策略的表現。"
        "  訊號數量和勝率因子歷史上無法取得，僅使用市場行情三因子。"
    )

    # ── Controls ─────────────────────────────────────────────────────────────
    with st.form("backtest_form"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**回測日期區間**")
            default_end   = date.today()
            default_start = default_end - timedelta(days=365)
            start_d = st.date_input("開始日期", value=default_start, max_value=default_end)
            end_d   = st.date_input("結束日期", value=default_end,   max_value=default_end)

        with c2:
            st.markdown("**積分設定**")
            pts_win  = st.number_input("命中積分 (+)", min_value=1,    max_value=10000, value=SCORE_WIN,  step=10)
            pts_lose = st.number_input("未中積分 (−)", min_value=-10000, max_value=-1,  value=SCORE_LOSE, step=10)

        st.markdown("**因子權重**  _(相對值，不需加總至 1)_")
        w1, w2, w3 = st.columns(3)
        with w1:
            w_spx  = st.slider("SPX夜盤報酬",  0.0, 1.0, 0.40, 0.05)
        with w2:
            w_tw   = st.slider("台股前日動能",  0.0, 1.0, 0.35, 0.05)
        with w3:
            w_vix  = st.slider("VIX恐慌指數",   0.0, 1.0, 0.25, 0.05)

        run_btn = st.form_submit_button("🚀 執行回測", type="primary", use_container_width=True)

    if run_btn:
        if start_d >= end_d:
            st.error("結束日期必須晚於開始日期。")
        elif w_spx == 0 and w_tw == 0 and w_vix == 0:
            st.error("至少一個因子權重需大於 0。")
        else:
            with st.spinner("下載歷史數據並執行回測..."):
                try:
                    bt_weights = {
                        "spx_overnight":  w_spx,
                        "taiex_momentum": w_tw,
                        "vix_fear":       w_vix,
                    }
                    df_bt, summary = backtest_oracle(
                        start_date = start_d.strftime("%Y-%m-%d"),
                        end_date   = end_d.strftime("%Y-%m-%d"),
                        weights    = bt_weights,
                        score_win  = int(pts_win),
                        score_lose = int(pts_lose),
                    )
                except Exception as e:
                    st.error(f"回測失敗: {e}")
                    df_bt, summary = pd.DataFrame(), {}

            if df_bt.empty:
                st.warning("無足夠歷史數據，請調整日期區間。")
            else:
                # KPI ribbon
                st.markdown("---")
                st.markdown("#### 回測結果")
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("模擬天數", summary["total"])
                k2.metric("勝率",     f"{summary['win_rate_pct']:.1f}%",
                          f"{summary['wins']}W / {summary['losses']}L")
                k3.metric("總積分",   f"{summary['cumulative_score']:+,.0f}")
                k4.metric("日均積分", f"{summary['avg_score_per_day']:+.1f}")
                k5.metric("最長連勝", summary["best_streak"])

                # Cumulative score chart
                fig_cum = go.Figure()
                df_bt["color"] = df_bt["is_correct"].map(
                    lambda x: "#26a69a" if x else "#ef5350"
                )
                fig_cum.add_trace(go.Scatter(
                    x=df_bt["date"], y=df_bt["cumulative_score"],
                    mode="lines+markers",
                    line=dict(color="#ffa726", width=2),
                    marker=dict(size=5, color=df_bt["color"].tolist()),
                    fill="tozeroy", fillcolor="rgba(255,167,38,0.08)",
                    name="累計積分",
                ))
                fig_cum.add_hline(y=0, line=dict(color="#555", dash="dot", width=1))
                fig_cum.update_layout(
                    title=f"累計積分走勢 ({start_d} → {end_d})",
                    template="plotly_dark", paper_bgcolor="#0d1117",
                    plot_bgcolor="#0d1117", height=300,
                    margin=dict(t=45, b=20),
                    xaxis=dict(gridcolor="#2a2a2a"),
                    yaxis=dict(gridcolor="#2a2a2a", zeroline=True, zerolinecolor="#555"),
                    showlegend=False,
                )
                st.plotly_chart(fig_cum, use_container_width=True)

                # Per-day bar chart
                bar_colors_bt = ["#26a69a" if v else "#ef5350" for v in df_bt["is_correct"]]
                fig_bar_bt = go.Figure(go.Bar(
                    x=df_bt["date"], y=df_bt["score_pts"],
                    marker_color=bar_colors_bt, name="每日積分",
                ))
                fig_bar_bt.add_hline(y=0, line=dict(color="#555", dash="dot", width=1))
                fig_bar_bt.update_layout(
                    title="每日積分", template="plotly_dark",
                    paper_bgcolor="#0d1117", plot_bgcolor="#0d1117", height=240,
                    margin=dict(t=40, b=20),
                    xaxis=dict(gridcolor="#2a2a2a"),
                    yaxis=dict(gridcolor="#2a2a2a"),
                    showlegend=False,
                )
                st.plotly_chart(fig_bar_bt, use_container_width=True)

                # Detail table
                with st.expander("逐日明細"):
                    disp_bt = df_bt[[
                        "date", "direction", "actual_dir", "confidence_pct",
                        "spx_ret", "taiex_mom", "vix",
                        "taiex_change_pts", "score_pts", "cumulative_score", "is_correct",
                    ]].copy()
                    disp_bt.columns = [
                        "日期", "預測", "實際", "信心%",
                        "SPX%", "台股動能%", "VIX",
                        "大盤變動pts", "積分", "累計", "命中",
                    ]
                    # Color-code Correct column
                    st.dataframe(
                        disp_bt,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "命中": st.column_config.CheckboxColumn("命中"),
                        },
                    )
