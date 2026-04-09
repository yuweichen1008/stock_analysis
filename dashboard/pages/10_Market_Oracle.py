"""
10_Market_Oracle.py — TAIEX Market Oracle Dashboard

Real-time bull/bear prediction · game scoring · backtesting simulator.
"""
import json
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
# Global CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* Hero prediction card */
.hero-bull {
    text-align:center; padding:24px 16px; border-radius:16px;
    background:linear-gradient(135deg,rgba(38,166,154,0.18),rgba(38,166,154,0.06));
    border:1.5px solid #26a69a; margin-bottom:8px;
}
.hero-bear {
    text-align:center; padding:24px 16px; border-radius:16px;
    background:linear-gradient(135deg,rgba(239,83,80,0.18),rgba(239,83,80,0.06));
    border:1.5px solid #ef5350; margin-bottom:8px;
}
.hero-title { font-size:36px; font-weight:800; margin:6px 0; letter-spacing:1px; }
.hero-sub   { font-size:14px; color:#aaa; margin-top:4px; }

/* Factor rows */
.factor-row {
    display:flex; align-items:center; padding:9px 12px;
    margin:4px 0; border-radius:8px; background:rgba(255,255,255,0.04);
    border-left:3px solid transparent; font-size:14px;
}
.factor-bull { border-color:#26a69a; }
.factor-bear { border-color:#ef5350; }
.factor-name { flex:1; color:#ddd; }
.factor-val  { color:#fff; font-weight:600; min-width:60px; text-align:right; }
.factor-thr  { color:#888; font-size:11px; min-width:54px; text-align:center; }
.factor-vote { font-size:13px; min-width:44px; text-align:right; }
.factor-wt   { color:#ffa726; font-size:12px; min-width:36px; text-align:right; }

/* Result outcome banner */
.result-win  {
    padding:12px; border-radius:10px; text-align:center;
    background:rgba(38,166,154,0.15); border:1px solid #26a69a;
}
.result-lose {
    padding:12px; border-radius:10px; text-align:center;
    background:rgba(239,83,80,0.15); border:1px solid #ef5350;
}

/* Rank badge */
.rank-badge {
    display:inline-block; padding:4px 12px; border-radius:20px;
    font-size:13px; font-weight:700; letter-spacing:.5px;
}

/* Streak pill */
.streak-pill {
    display:inline-block; padding:3px 10px; border-radius:12px;
    background:rgba(255,167,38,0.2); border:1px solid #ffa726;
    color:#ffa726; font-size:12px; font-weight:600;
}

/* Score banner */
.score-big {
    font-size:42px; font-weight:900; line-height:1;
}

/* Divider */
.section-sep { border:none; border-top:1px solid #2a2a2a; margin:16px 0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Constants & helpers
# ─────────────────────────────────────────────────────────────────────────────

_FACTOR_LABELS = {
    "spx_overnight":  "SPX 夜盤報酬",
    "taiex_momentum": "台股前日動能",
    "vix_fear":       "VIX 恐慌指數",
    "signal_count":   "超跌訊號數",
    "tw_win_rate":    "近期TW勝率",
}
_FACTOR_UNITS = {
    "spx_overnight": "%", "taiex_momentum": "%",
    "vix_fear": "", "signal_count": "檔", "tw_win_rate": "%",
}
_THRESHOLD_DESC = {
    "spx_overnight":  ">+0.3%", "taiex_momentum": ">+0.5%",
    "vix_fear":       "<20",    "signal_count":   "≥3",
    "tw_win_rate":    ">55%",
}
_WEIGHTS = {
    "spx_overnight": 0.30, "taiex_momentum": 0.25,
    "vix_fear": 0.20, "signal_count": 0.15, "tw_win_rate": 0.10,
}

_PLOT_CFG = dict(
    template="plotly_dark", paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
)


def _rank(stats: dict) -> tuple[str, str]:
    """Return (badge_html, label) based on cumulative score + win rate."""
    total = stats.get("total", 0)
    if total < 5:
        return '<span class="rank-badge" style="background:rgba(100,100,100,.25);color:#aaa">🌱 新手</span>', "新手"
    wr  = stats.get("win_rate_pct", 0)
    cum = stats.get("cumulative_score", 0)
    if wr >= 70 and cum >= 5000:
        return '<span class="rank-badge" style="background:rgba(100,200,255,.15);color:#64d8ff">💎 鑽石</span>', "鑽石"
    if wr >= 60 and cum >= 2000:
        return '<span class="rank-badge" style="background:rgba(255,215,0,.15);color:#ffd700">🥇 金牌</span>', "金牌"
    if wr >= 52 and cum >= 500:
        return '<span class="rank-badge" style="background:rgba(192,192,192,.15);color:#c0c0c0">🥈 銀牌</span>', "銀牌"
    return '<span class="rank-badge" style="background:rgba(205,127,50,.15);color:#cd7f32">🥉 銅牌</span>', "銅牌"


def _streak_pill(n: int, win: bool = True) -> str:
    if n < 2:
        return ""
    label = f"🔥 {n}連{'勝' if win else '敗'}"
    color = "#ffa726" if win else "#ef5350"
    return f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;background:rgba({("255,167,38" if win else "239,83,80")},.2);border:1px solid {color};color:{color};font-size:13px;font-weight:600">{label}</span>'


def _factor_rows_html(factors: dict) -> str:
    rows = []
    for fname, finfo in factors.items():
        val  = finfo.get("value")
        bull = finfo.get("bull", False)
        unit = _FACTOR_UNITS.get(fname, "")
        val_s = f"{val:+.1f}{unit}" if isinstance(val, (int, float)) and val is not None else ("N/A" if val is None else f"{val}{unit}")
        vote  = "🟢 多" if bull else "🔴 空"
        row_cls = "factor-bull" if bull else "factor-bear"
        wt = _WEIGHTS.get(fname, 0)
        rows.append(
            f'<div class="factor-row {row_cls}">'
            f'<span class="factor-name">{_FACTOR_LABELS.get(fname, fname)}</span>'
            f'<span class="factor-val">{val_s}</span>'
            f'<span class="factor-thr">{_THRESHOLD_DESC.get(fname,"")}</span>'
            f'<span class="factor-vote">{vote}</span>'
            f'<span class="factor-wt">{wt*100:.0f}%</span>'
            f'</div>'
        )
    return "\n".join(rows)


def _gauge_fig(value: float, direction: str) -> go.Figure:
    color = "#26a69a" if direction == "Bull" else "#ef5350"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": "%", "font": {"size": 28, "color": color}},
        gauge={
            "axis": {"range": [50, 100], "tickwidth": 1,
                     "tickcolor": "#555", "tickfont": {"color": "#888", "size": 10}},
            "bar":  {"color": color, "thickness": 0.25},
            "bgcolor": "#1a1a2e",
            "borderwidth": 0,
            "steps": [
                {"range": [50, 65],  "color": "rgba(80,80,80,.3)"},
                {"range": [65, 80],  "color": "rgba(80,80,80,.5)"},
                {"range": [80, 100], "color": "rgba(80,80,80,.7)"},
            ],
            "threshold": {
                "line": {"color": color, "width": 3},
                "thickness": 0.8, "value": value,
            },
        },
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(
        height=180, margin=dict(l=20, r=20, t=10, b=10),
        paper_bgcolor="#0d1117", font={"color": "#eee"},
    )
    return fig


def _combo_chart(df: pd.DataFrame, title: str = "") -> go.Figure:
    """Dual-axis chart: daily score bars + cumulative line."""
    bar_colors = ["#26a69a" if v else "#ef5350" for v in df["is_correct_bool"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["date"], y=df["score_pts"],
        marker_color=bar_colors, name="每日積分",
        yaxis="y", opacity=0.75,
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["cumulative_score"],
        mode="lines+markers",
        line=dict(color="#ffa726", width=2.5),
        marker=dict(size=5, color=bar_colors),
        name="累計積分", yaxis="y2",
    ))
    fig.add_hline(y=0, line=dict(color="#555", dash="dot", width=1), yref="y")
    fig.update_layout(
        **_PLOT_CFG,
        title=title, height=320,
        margin=dict(t=40 if title else 10, b=20, l=10, r=60),
        xaxis=dict(gridcolor="#2a2a2a"),
        yaxis=dict(title="每日積分", gridcolor="#2a2a2a",
                   titlefont=dict(color="#888"), tickfont=dict(color="#888")),
        yaxis2=dict(title="累計積分", overlaying="y", side="right",
                    gridcolor="#1a1a1a",
                    titlefont=dict(color="#ffa726"), tickfont=dict(color="#ffa726")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🔮 Market Oracle")
    auto_refresh = st.toggle("自動更新 (每5分)", value=False)
    if auto_refresh:
        st.caption("下次更新: 5分鐘後")
    st.markdown("---")
    st.markdown("**積分制度**")
    st.markdown(f"✅ 命中 → **+{SCORE_WIN} pts**")
    st.markdown(f"❌ 未中 → **{SCORE_LOSE} pts**")
    st.markdown("---")
    st.markdown("**等級系統**")
    st.markdown("🌱 新手 · 🥉 銅牌 · 🥈 銀牌")
    st.markdown("🥇 金牌 · 💎 鑽石")

if auto_refresh:
    time.sleep(300)
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Page header
# ─────────────────────────────────────────────────────────────────────────────

today_str = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
history   = _load_history(str(BASE_DIR))
today_rows = history[history["date"] == today_str] if not history.empty else pd.DataFrame()
stats = oracle_stats(str(BASE_DIR))
rank_html, rank_label = _rank(stats)

h1, h2 = st.columns([3, 1])
with h1:
    st.title("🔮 台股大盤 Oracle")
    st.caption(f"每日多空預測  ·  遊戲積分  ·  歷史回測  ·  {today_str}")
with h2:
    st.markdown(f"<div style='text-align:right;padding-top:16px'>{rank_html}</div>",
                unsafe_allow_html=True)
    if stats["total"] > 0:
        streak = stats.get("streak", 0)
        if streak >= 2:
            st.markdown(f"<div style='text-align:right'>{_streak_pill(streak)}</div>",
                        unsafe_allow_html=True)

st.markdown("---")

tab_today, tab_history, tab_stats, tab_backtest, tab_subscribe = st.tabs([
    "🎯 今日預測", "📅 歷史戰績", "📊 統計分析", "🧪 回測模擬", "🔔 訂閱通知"
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Today's Prediction
# ─────────────────────────────────────────────────────────────────────────────

with tab_today:

    if today_rows.empty:
        # ── No prediction yet ─────────────────────────────────────────────────
        st.markdown(
            '<div style="text-align:center;padding:32px;border-radius:16px;'
            'background:rgba(255,255,255,0.03);border:1px dashed #444">'
            '<span style="font-size:40px">🔮</span><br>'
            '<span style="color:#aaa;font-size:16px">今日預測尚未生成</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        c = st.columns([1, 2, 1])
        with c[1]:
            if st.button("✨ 生成今日預測", type="primary", use_container_width=True):
                with st.spinner("分析市場因子中..."):
                    try:
                        pred = compute_prediction(str(BASE_DIR))
                        save_prediction(str(BASE_DIR), pred)
                        st.rerun()
                    except Exception as e:
                        st.error(f"生成失敗: {e}")
    else:
        row        = today_rows.iloc[-1]
        direction  = row.get("direction", "?")
        conf       = float(row.get("confidence_pct") or 0)
        status     = row.get("status", "pending")
        is_bull    = direction == "Bull"
        dir_color  = "#26a69a" if is_bull else "#ef5350"
        dir_cls    = "hero-bull" if is_bull else "hero-bear"
        dir_label  = "多方 BULL" if is_bull else "空方 BEAR"
        dir_icon   = "🟢" if is_bull else "🔴"

        # ── Hero card ─────────────────────────────────────────────────────────
        left, mid, right = st.columns([2, 3, 2])

        with mid:
            st.markdown(
                f'<div class="{dir_cls}">'
                f'<div style="font-size:52px">{dir_icon}</div>'
                f'<div class="hero-title" style="color:{dir_color}">{dir_label}</div>'
                f'<div class="hero-sub">{today_str}  ·  AI 多空預測</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Resolved result banner ────────────────────────────────────────────
        if status == "resolved":
            change_pts = float(row.get("taiex_change_pts") or 0)
            score_pts  = float(row.get("score_pts") or 0)
            is_correct = str(row.get("is_correct", "")).lower() in ("true", "1")
            s_color    = "#26a69a" if score_pts >= 0 else "#ef5350"
            res_cls    = "result-win" if is_correct else "result-lose"
            outcome    = "✅ 命中" if is_correct else "❌ 未命中"
            st.markdown(
                f'<div class="{res_cls}">'
                f'<b>{outcome}</b>  ·  '
                f'大盤 <b>{change_pts:+.0f} pts</b>  ·  '
                f'<span class="score-big" style="color:{s_color}">{score_pts:+.0f}</span>'
                f' <span style="color:#888;font-size:14px">分</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="text-align:center;padding:8px;border-radius:8px;'
                f'background:rgba(255,167,38,0.08);border:1px solid rgba(255,167,38,0.3);'
                f'color:#ffa726;font-size:13px">'
                f'⏳ 盤後自動結算  ·  命中 <b>+{SCORE_WIN}</b>  ·  未中 <b>{SCORE_LOSE}</b>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("")

        # ── Two-column body ───────────────────────────────────────────────────
        col_factors, col_live = st.columns([5, 4])

        with col_factors:
            # Confidence gauge
            st.plotly_chart(_gauge_fig(conf, direction),
                            use_container_width=True, config={"displayModeBar": False})

            # Factor breakdown
            st.markdown('<p style="color:#aaa;font-size:13px;margin-bottom:4px">因子分析  <span style="font-size:11px">(數值 · 門檻 · 投票 · 權重)</span></p>', unsafe_allow_html=True)
            try:
                factors = json.loads(str(row.get("factors_json") or "{}"))
                if factors:
                    st.markdown(_factor_rows_html(factors), unsafe_allow_html=True)
            except Exception:
                pass

        with col_live:
            st.markdown(f'<p style="color:#aaa;font-size:13px;margin-bottom:2px">即時大盤 <span style="font-size:11px">(15min延遲)</span></p>', unsafe_allow_html=True)
            with st.spinner(""):
                live = get_taiex_live()

            if live["current_level"] is not None:
                chg = live["change_pts"] or 0
                pct = live["change_pct"] or 0
                st.metric(
                    label=f"TAIEX  {live['last_updated']} TST",
                    value=f"{live['current_level']:,.1f}",
                    delta=f"{chg:+.1f} pts ({pct:+.2f}%)",
                )

                intra = live["intraday_df"]
                if not intra.empty:
                    base  = float(intra["Open"].iloc[0])
                    lc    = "#26a69a" if chg >= 0 else "#ef5350"
                    fc    = "rgba(38,166,154,0.10)" if chg >= 0 else "rgba(239,83,80,0.10)"
                    fig_i = go.Figure(go.Scatter(
                        x=intra.index, y=intra["Close"],
                        mode="lines", line=dict(color=lc, width=2),
                        fill="tozeroy", fillcolor=fc,
                    ))
                    fig_i.add_hline(y=base, line=dict(color="#555", dash="dot", width=1),
                                    annotation_text="開盤",
                                    annotation_font=dict(color="#777", size=10))
                    fig_i.update_layout(
                        **_PLOT_CFG, height=220,
                        margin=dict(l=10, r=10, t=6, b=30), showlegend=False,
                        xaxis=dict(gridcolor="#2a2a2a", tickfont=dict(size=10)),
                        yaxis=dict(gridcolor="#2a2a2a", tickfont=dict(size=10)),
                    )
                    st.plotly_chart(fig_i, use_container_width=True,
                                    config={"displayModeBar": False})

                # Leading indicator (pending only)
                if status == "pending":
                    actual_now = "Bull" if chg > 0 else "Bear"
                    leading    = direction == actual_now
                    l_color    = "#26a69a" if leading else "#ef5350"
                    l_icon     = "🎯" if leading else "😬"
                    l_text     = "目前領先" if leading else "目前落後"
                    l_score    = f"+{SCORE_WIN}" if leading else str(SCORE_LOSE)
                    st.markdown(
                        f'<div style="text-align:center;margin-top:6px;padding:10px;'
                        f'border-radius:10px;background:rgba({"38,166,154" if leading else "239,83,80"},.1);'
                        f'border:1px solid {l_color}">'
                        f'<span style="font-size:22px">{l_icon}</span> '
                        f'<span style="color:{l_color};font-weight:700">{l_text}</span><br>'
                        f'<span style="font-size:28px;font-weight:900;color:{l_color}">{l_score} 分</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("盤中或盤後才有 yfinance 即時資料")

        # ── Stats ribbon ──────────────────────────────────────────────────────
        if stats["total"] > 0:
            st.markdown('<hr class="section-sep">', unsafe_allow_html=True)
            k1, k2, k3, k4, k5, k6 = st.columns(6)
            k1.metric("預測天數",  stats["total"])
            k2.metric("勝率",     f"{stats['win_rate_pct']:.1f}%",
                      f"{stats['wins']}W  {stats['losses']}L")
            k3.metric("累計積分",  f"{stats['cumulative_score']:+,.0f}")
            k4.metric("日均積分",  f"{stats['avg_score_per_day']:+.0f}")
            k5.metric("連勝",     stats["streak"])
            k6.metric("等級",     rank_label)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — History
# ─────────────────────────────────────────────────────────────────────────────

with tab_history:
    history  = _load_history(str(BASE_DIR))
    resolved = history[history["status"] == "resolved"].copy() if not history.empty else pd.DataFrame()

    if resolved.empty:
        st.info("尚無已結算紀錄。每日盤後結算後自動出現。")
    else:
        resolved = resolved.sort_values("date").reset_index(drop=True)
        resolved["score_pts"]        = pd.to_numeric(resolved["score_pts"],        errors="coerce")
        resolved["cumulative_score"] = pd.to_numeric(resolved["cumulative_score"], errors="coerce")
        resolved["taiex_change_pts"] = pd.to_numeric(resolved["taiex_change_pts"], errors="coerce")
        resolved["is_correct_bool"]  = resolved["is_correct"].map(
            lambda x: str(x).lower() in ("true", "1")
        )

        # KPI row
        s = oracle_stats(str(BASE_DIR))
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("勝率",    f"{s['win_rate_pct']:.1f}%", f"{s['wins']}W / {s['losses']}L")
        k2.metric("累計積分", f"{s['cumulative_score']:+,.0f}")
        k3.metric("日均積分", f"{s['avg_score_per_day']:+.0f}")
        k4.metric("最長連勝", s["streak"])
        k5.metric("等級",    rank_label)

        # Combined daily + cumulative chart
        st.plotly_chart(_combo_chart(resolved), use_container_width=True,
                        config={"displayModeBar": False})

        # History table
        with st.expander("📋 逐日明細"):
            disp = resolved[["date", "direction", "confidence_pct",
                             "taiex_change_pts", "score_pts",
                             "cumulative_score", "is_correct_bool"]].copy()
            disp.columns = ["日期", "預測方向", "信心%", "大盤變動 pts", "積分", "累計積分", "命中"]
            st.dataframe(
                disp, use_container_width=True, hide_index=True,
                column_config={
                    "命中": st.column_config.CheckboxColumn("命中"),
                    "積分": st.column_config.NumberColumn("積分", format="%+d"),
                    "累計積分": st.column_config.NumberColumn("累計積分", format="%+,.0f"),
                },
            )

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Stats
# ─────────────────────────────────────────────────────────────────────────────

with tab_stats:
    history  = _load_history(str(BASE_DIR))
    resolved = history[history["status"] == "resolved"].copy() if not history.empty else pd.DataFrame()

    if resolved.empty or len(resolved) < 3:
        st.info("統計需要至少 3 筆已結算紀錄。預測愈多，分析愈準確。")
    else:
        resolved["score_pts"]    = pd.to_numeric(resolved["score_pts"], errors="coerce")
        resolved["is_correct_b"] = resolved["is_correct"].map(
            lambda x: str(x).lower() in ("true", "1")
        )
        resolved["dow"] = pd.to_datetime(resolved["date"]).dt.day_name()

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("#### 方向勝率")
            bull_rows = resolved[resolved["direction"] == "Bull"]
            bear_rows = resolved[resolved["direction"] == "Bear"]
            bull_wr   = bull_rows["is_correct_b"].mean() * 100 if len(bull_rows) else 0
            bear_wr   = bear_rows["is_correct_b"].mean() * 100 if len(bear_rows) else 0
            fig_dir = go.Figure(go.Bar(
                x=["🟢 多方 Bull", "🔴 空方 Bear"],
                y=[bull_wr, bear_wr],
                marker_color=["#26a69a", "#ef5350"],
                text=[f"{v:.1f}%<br><span style='font-size:11px'>({n}次)</span>"
                      for v, n in [(bull_wr, len(bull_rows)), (bear_wr, len(bear_rows))]],
                textposition="outside",
            ))
            fig_dir.update_layout(
                **_PLOT_CFG, height=300,
                margin=dict(t=10, b=10, l=10, r=10),
                yaxis=dict(range=[0, 118], gridcolor="#2a2a2a",
                           title="勝率 %", ticksuffix="%"),
                showlegend=False,
            )
            st.plotly_chart(fig_dir, use_container_width=True,
                            config={"displayModeBar": False})

        with col_b:
            st.markdown("#### 星期勝率")
            dow_order  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            dow_labels = {"Monday": "週一", "Tuesday": "週二", "Wednesday": "週三",
                          "Thursday": "週四", "Friday": "週五"}
            dow_wr = resolved.groupby("dow")["is_correct_b"].mean() * 100
            dow_wr = dow_wr.reindex([d for d in dow_order if d in dow_wr.index])
            fig_dow = go.Figure(go.Bar(
                x=[dow_labels.get(d, d) for d in dow_wr.index],
                y=dow_wr.values,
                marker_color=["#26a69a" if v >= 55 else "#ef5350" for v in dow_wr.values],
                text=[f"{v:.1f}%" for v in dow_wr.values],
                textposition="outside",
            ))
            fig_dow.add_hline(y=55, line=dict(color="#ffa726", dash="dot", width=1),
                              annotation_text="55% 基準",
                              annotation_font=dict(color="#ffa726", size=10))
            fig_dow.update_layout(
                **_PLOT_CFG, height=300,
                margin=dict(t=10, b=10, l=10, r=10),
                yaxis=dict(range=[0, 118], gridcolor="#2a2a2a",
                           title="勝率 %", ticksuffix="%"),
                showlegend=False,
            )
            st.plotly_chart(fig_dow, use_container_width=True,
                            config={"displayModeBar": False})

        st.markdown("#### 積分分布")
        fig_hist = go.Figure(go.Histogram(
            x=resolved["score_pts"].dropna(), nbinsx=10,
            marker=dict(color="#ab47bc", line=dict(color="#0d1117", width=1)),
        ))
        fig_hist.add_vline(x=0, line=dict(color="#ffa726", dash="dash", width=1.5),
                           annotation_text="損益平衡",
                           annotation_font=dict(color="#ffa726", size=11))
        fig_hist.update_layout(
            **_PLOT_CFG, height=220,
            margin=dict(t=10, b=20, l=10, r=10),
            xaxis=dict(title="積分", gridcolor="#2a2a2a"),
            yaxis=dict(title="次數", gridcolor="#2a2a2a"),
            showlegend=False,
        )
        st.plotly_chart(fig_hist, use_container_width=True,
                        config={"displayModeBar": False})

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — Backtesting
# ─────────────────────────────────────────────────────────────────────────────

with tab_backtest:
    st.markdown("### 🧪 策略回測模擬")
    st.caption(
        "使用歷史 TWII / SPX / VIX 數據模擬多空預測績效。"
        "  訊號數與勝率因子歷史無法取得，僅使用市場行情三因子。"
    )

    # ── Controls row ─────────────────────────────────────────────────────────
    ct1, ct2, ct3 = st.columns([2, 2, 3])

    with ct1:
        st.markdown("**日期區間**")
        default_end   = date.today()
        default_start = default_end - timedelta(days=365)
        start_d = st.date_input("開始", value=default_start, max_value=default_end,
                                label_visibility="collapsed")
        end_d   = st.date_input("結束", value=default_end,   max_value=default_end,
                                label_visibility="collapsed")
        st.caption(f"{start_d}  →  {end_d}")

    with ct2:
        st.markdown("**積分設定**")
        pts_win  = st.number_input("命中 (+)",  min_value=1,     max_value=10000,
                                   value=SCORE_WIN,  step=10, label_visibility="visible")
        pts_lose = st.number_input("未中 (−)",  min_value=-10000, max_value=-1,
                                   value=SCORE_LOSE, step=10, label_visibility="visible")

    with ct3:
        st.markdown("**因子權重**  _(相對值)_")
        w_spx = st.slider("📈 SPX夜盤報酬",   0.0, 1.0, 0.40, 0.05)
        w_tw  = st.slider("🇹🇼 台股前日動能", 0.0, 1.0, 0.35, 0.05)
        w_vix = st.slider("😨 VIX恐慌指數",  0.0, 1.0, 0.25, 0.05)

    st.markdown("")
    run_c = st.columns([1, 2, 1])
    with run_c[1]:
        run_btn = st.button("🚀 執行回測", type="primary", use_container_width=True)

    # ── Run ──────────────────────────────────────────────────────────────────
    if run_btn:
        if start_d >= end_d:
            st.error("結束日期必須晚於開始日期。")
        elif w_spx == 0 and w_tw == 0 and w_vix == 0:
            st.error("至少一個因子權重需大於 0。")
        else:
            with st.spinner("下載歷史數據並模擬中..."):
                try:
                    df_bt, summary = backtest_oracle(
                        start_date=start_d.strftime("%Y-%m-%d"),
                        end_date=end_d.strftime("%Y-%m-%d"),
                        weights={"spx_overnight": w_spx,
                                 "taiex_momentum": w_tw,
                                 "vix_fear": w_vix},
                        score_win=int(pts_win),
                        score_lose=int(pts_lose),
                    )
                except Exception as e:
                    st.error(f"回測失敗: {e}")
                    df_bt, summary = pd.DataFrame(), {}

            if df_bt.empty:
                st.warning("無足夠歷史數據，請調整日期區間。")
            else:
                df_bt["is_correct_bool"] = df_bt["is_correct"].astype(bool)

                st.markdown('<hr class="section-sep">', unsafe_allow_html=True)

                # KPI ribbon
                k1, k2, k3, k4, k5, k6 = st.columns(6)
                k1.metric("模擬天數",  summary["total"])
                k2.metric("勝率",     f"{summary['win_rate_pct']:.1f}%",
                          f"{summary['wins']}W / {summary['losses']}L")
                k3.metric("總積分",   f"{summary['cumulative_score']:+,.0f}")
                k4.metric("日均積分", f"{summary['avg_score_per_day']:+.1f}")
                k5.metric("最長連勝", summary["best_streak"])

                # Random baseline comparison (50% win rate)
                random_daily = pts_win * 0.5 + pts_lose * 0.5
                random_total = round(random_daily * summary["total"])
                delta_vs_random = summary["cumulative_score"] - random_total
                k6.metric("vs 隨機基準", f"{delta_vs_random:+,.0f}",
                          "優於隨機" if delta_vs_random >= 0 else "劣於隨機",
                          delta_color="normal" if delta_vs_random >= 0 else "inverse")

                # Combined chart (daily bar + cumulative line)
                st.plotly_chart(
                    _combo_chart(df_bt, f"策略回測  {start_d} → {end_d}"),
                    use_container_width=True, config={"displayModeBar": False},
                )

                # Random baseline overlay
                random_cum = [random_daily * (i + 1) for i in range(len(df_bt))]
                fig_cmp = go.Figure()
                fig_cmp.add_trace(go.Scatter(
                    x=df_bt["date"], y=df_bt["cumulative_score"],
                    mode="lines", line=dict(color="#ffa726", width=2.5),
                    name="策略", fill="tozeroy", fillcolor="rgba(255,167,38,0.06)",
                ))
                fig_cmp.add_trace(go.Scatter(
                    x=df_bt["date"], y=random_cum,
                    mode="lines", line=dict(color="#888", width=1.5, dash="dash"),
                    name="隨機基準 (50%)",
                ))
                fig_cmp.add_hline(y=0, line=dict(color="#555", dash="dot", width=1))
                fig_cmp.update_layout(
                    **_PLOT_CFG, height=260,
                    title="策略 vs 隨機基準 (50%勝率)",
                    margin=dict(t=45, b=20, l=10, r=10),
                    xaxis=dict(gridcolor="#2a2a2a"),
                    yaxis=dict(gridcolor="#2a2a2a", zeroline=True, zerolinecolor="#555",
                               title="累計積分"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    hovermode="x unified",
                )
                st.plotly_chart(fig_cmp, use_container_width=True,
                                config={"displayModeBar": False})

                # Detail table
                with st.expander("📋 逐日明細"):
                    disp_bt = df_bt[[
                        "date", "direction", "actual_dir", "confidence_pct",
                        "spx_ret", "taiex_mom", "vix",
                        "taiex_change_pts", "score_pts", "cumulative_score", "is_correct",
                    ]].copy()
                    disp_bt.columns = [
                        "日期", "預測", "實際", "信心%",
                        "SPX%", "台股%", "VIX",
                        "大盤變動", "積分", "累計", "命中",
                    ]
                    st.dataframe(
                        disp_bt, use_container_width=True, hide_index=True,
                        column_config={
                            "命中":  st.column_config.CheckboxColumn("命中"),
                            "積分":  st.column_config.NumberColumn("積分",  format="%+d"),
                            "累計":  st.column_config.NumberColumn("累計",  format="%+,.0f"),
                            "大盤變動": st.column_config.NumberColumn("大盤變動", format="%+.0f"),
                        },
                    )

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — Subscribe
# ─────────────────────────────────────────────────────────────────────────────

with tab_subscribe:
    st.markdown("### 🔔 訂閱 Oracle 每日通知")
    st.markdown(
        "每個交易日 **08:00** 送出當日多空預測，**14:05** 結算通知。"
        "  \n透過 **Telegram** 私訊接收，完全免費。"
    )

    st.markdown("---")

    col_sub, col_info = st.columns([1, 1], gap="large")

    with col_sub:
        st.markdown("#### 📬 Telegram 訂閱")
        tid_input = st.text_input(
            "你的 Telegram Chat ID",
            placeholder="例：123456789",
            help="不知道你的 Chat ID？請見右側說明",
        )
        lbl_input = st.text_input("顯示名稱（選填）", placeholder="例：Sami")

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            sub_btn = st.button("📬 訂閱", type="primary", use_container_width=True)
        with col_btn2:
            unsub_btn = st.button("🔕 取消訂閱", use_container_width=True)

        if sub_btn:
            if not tid_input.strip():
                st.error("請輸入 Telegram Chat ID")
            else:
                try:
                    import requests as _req
                    resp = _req.post(
                        "http://localhost:8000/api/subscribe",
                        json={"telegram_id": tid_input.strip(), "label": lbl_input.strip() or None},
                        timeout=8,
                    )
                    if resp.status_code == 200:
                        st.success("✅ 訂閱成功！請查看你的 Telegram — 已傳送確認訊息。")
                    elif resp.status_code == 409:
                        st.info("ℹ️ 此 Chat ID 已訂閱。")
                    else:
                        detail = resp.json().get("detail", "訂閱失敗")
                        st.error(f"❌ {detail}")
                except Exception as e:
                    st.error(f"無法連線至 API：{e}")

        if unsub_btn:
            if not tid_input.strip():
                st.error("請輸入 Telegram Chat ID")
            else:
                try:
                    import requests as _req
                    resp = _req.delete(
                        f"http://localhost:8000/api/subscribe/{tid_input.strip()}",
                        timeout=8,
                    )
                    if resp.status_code == 200:
                        st.success("已取消訂閱。")
                    else:
                        st.error("找不到此訂閱。")
                except Exception as e:
                    st.error(f"無法連線至 API：{e}")

    with col_info:
        st.markdown("#### 📖 如何取得 Telegram Chat ID")
        st.markdown("""
1. 在 Telegram 搜尋 **@userinfobot**
2. 傳送任意訊息（例如 `/start`）
3. Bot 會回覆你的 **Chat ID**（純數字）
4. 將該數字貼入左側欄位

---
**通知內容**
| 時間 | 訊息 |
|------|------|
| 08:00 TST | 🔮 今日多空預測 + 信心指數 |
| 14:05 TST | 📊 結算 + 大盤變動 + 積分 |

---
**手機 App**
下載 Oracle App 直接在手機接收推播通知，並可參與虛擬押注遊戲。
        """)

    # Current subscriber count (admin view)
    try:
        import requests as _req
        subs_resp = _req.get("http://localhost:8000/api/subscribe/list", timeout=4)
        if subs_resp.ok:
            subs = subs_resp.json()
            st.markdown(f"---\n**目前訂閱人數：{len(subs)}**")
    except Exception:
        pass
