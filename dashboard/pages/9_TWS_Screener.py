"""
TWS Screener — Taiwan's version of Finviz.

Tabs:
  1. 📊 Screener     — full TWSE ~1000 stocks, multi-filter table
  2. 🌏 Heat Map     — interactive Plotly treemap (same as Market Map)
  3. 💎 千元股        — high-price moat leaders (price ≥ 500 TWD)
  4. 📈 Sectors      — sector-level performance analytics
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime
from pathlib import Path

from dashboard.data_helpers import BASE_DIR, load_company_mapping
from tws.utils import fetch_twse_all_prices, get_last_trading_date

st.set_page_config(page_title="TWS Screener", page_icon="🔍", layout="wide")
st.title("🔍 TWS Screener")
st.caption("Taiwan Finviz — full TWSE universe screener, heatmap, moat leaders & sector analytics")

# ── Shared data loading ────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner="Fetching TWSE market data…")
def _load_market(date_str: str) -> pd.DataFrame:
    return fetch_twse_all_prices(date_str)


@st.cache_data(ttl=300, show_spinner="Loading universe snapshot…")
def _load_universe() -> pd.DataFrame:
    p = BASE_DIR / "data" / "company" / "universe_snapshot.csv"
    if not p.exists():
        p = BASE_DIR / "current_trending.csv"
        if not p.exists():
            return pd.DataFrame()
    df = pd.read_csv(p, dtype={"ticker": str})
    df["is_signal"] = df["is_signal"].astype(str).str.lower().isin(["true", "1", "yes"])
    return df


trading_date = get_last_trading_date()
date_str     = trading_date.strftime("%Y%m%d")
date_label   = trading_date.strftime("%Y-%m-%d")

col_d, col_r = st.columns([6, 1])
col_d.caption(f"Trading date: **{date_label}**")
if col_r.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

# Data freshness warning
_now_tst = datetime.now()
_market_close_today = _now_tst.replace(hour=14, minute=30, second=0, microsecond=0)
if _now_tst < _market_close_today:
    st.info(
        "⏳ TWSE market data updates after **14:30 TST**. "
        "Prices shown are from the last completed trading session.",
        icon="ℹ️",
    )

price_df    = _load_market(date_str)
mapping_df  = load_company_mapping()
universe_df = _load_universe()

# ── Merge price + mapping + universe into master frame ─────────────────────────
# Avoid JSON round-trip (lossy for dtypes); merge DataFrames directly.
# Wrapped in a helper so the merge logic is easy to test standalone.

def _build_master(
    price:   pd.DataFrame,
    mapping: pd.DataFrame,
    univ:    pd.DataFrame,
) -> pd.DataFrame:
    if price.empty:
        return pd.DataFrame()

    df = price.copy()
    df["ticker"] = df["ticker"].astype(str)

    # Merge company fundamentals
    if not mapping.empty and "industry" in mapping.columns:
        keep = [c for c in ["ticker", "name", "industry", "pe_ratio", "roe", "dividend_yield"]
                if c in mapping.columns]
        m = mapping[keep].copy()
        m["ticker"] = m["ticker"].astype(str)
        if "name" in m.columns:
            m = m.rename(columns={"name": "co_name"})
        df = df.merge(m, on="ticker", how="left")

    if "co_name" not in df.columns:
        df["co_name"] = df.get("name", df["ticker"])
    df["co_name"]  = df["co_name"].fillna(df["ticker"])
    df["industry"] = df.get("industry", pd.Series("其他", index=df.index)).fillna("其他").str.strip()

    # Merge technical signals from universe snapshot
    if not univ.empty:
        univ_cols = [c for c in ["ticker", "RSI", "bias", "score", "is_signal", "category",
                                  "MA120", "f60", "f_zscore", "vol_ratio", "short_interest",
                                  "news_sentiment"]
                     if c in univ.columns]
        u = univ[univ_cols].copy()
        u["ticker"] = u["ticker"].astype(str)
        df = df.merge(u, on="ticker", how="left")

    # Ensure required columns exist with sensible defaults
    df["is_signal"] = df.get("is_signal", False)
    df["is_signal"] = df["is_signal"].astype(str).str.lower().isin(["true", "1", "yes"])
    df["category"]  = df.get("category",  pd.Series("", index=df.index)).fillna("")

    # Coerce all numeric columns
    for col in ["change_pct", "value", "close", "open", "high", "low", "volume",
                "RSI", "bias", "score", "pe_ratio", "roe", "dividend_yield",
                "f60", "f_zscore", "vol_ratio", "MA120", "short_interest"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.reset_index(drop=True)


master = _build_master(price_df, mapping_df, universe_df)

# ── Colour scale for treemap ───────────────────────────────────────────────────
_DIVERGING = [
    [0.00, "#b71c1c"], [0.25, "#ef5350"], [0.43, "#ffcdd2"],
    [0.50, "#424242"], [0.57, "#c8e6c9"], [0.75, "#43a047"],
    [1.00, "#00e676"],
]

# ── Finviz-style moat data card (no AI needed) ────────────────────────────────

def _finviz_moat_card(row, ticker, name, ind, price, roe, score):
    """
    Display a finviz-style fundamentals card for a 高價潛力股.
    Shows all available quantitative data — no external API calls required.
    """
    def _v(col, fmt=None, suffix=""):
        val = row.get(col)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "—"
        try:
            f = float(val)
            return (format(f, fmt) if fmt else str(val)) + suffix
        except (ValueError, TypeError):
            return str(val)

    # ── Row 1: price metrics ──────────────────────────────────────────────────
    r1a, r1b, r1c, r1d, r1e = st.columns(5)
    r1a.metric("Price (TWD)", f"{price:.0f}")
    r1b.metric("Change%",     _v("change_pct", ".2f", "%"))
    r1c.metric("P/E Ratio",   _v("pe_ratio",   ".1f"))
    r1d.metric("ROE%",        f"{roe}%" if roe not in ("N/A", None, "") else "—")
    r1e.metric("Dividend%",   _v("dividend_yield", ".2f", "%"))

    st.divider()

    # ── Row 2: technicals ─────────────────────────────────────────────────────
    r2a, r2b, r2c, r2d, r2e = st.columns(5)
    rsi  = row.get("RSI")
    bias = row.get("bias")
    ma120 = row.get("MA120")
    vol_r = row.get("vol_ratio")
    ma120_pct = (
        f"{(price - float(ma120)) / float(ma120) * 100:+.1f}%"
        if ma120 and float(ma120) > 0 else "—"
    )
    r2a.metric("RSI (14)",      f"{rsi:.1f}"  if pd.notna(rsi)  else "—")
    r2b.metric("Bias vs MA20",  f"{bias:.1f}%" if pd.notna(bias) else "—")
    r2c.metric("vs MA120",      ma120_pct)
    r2d.metric("Vol Ratio",     f"{vol_r:.2f}x" if pd.notna(vol_r) else "—")
    r2e.metric("Moat Score",    f"{score:.0f} / 100")

    st.divider()

    # ── Row 3: institutional flow ─────────────────────────────────────────────
    r3a, r3b, r3c, r3d = st.columns(4)
    f5   = row.get("f5",  0) or 0
    f20  = row.get("f20", 0) or 0
    f60  = row.get("f60", 0) or 0
    fz   = row.get("f_zscore", 0) or 0

    def _flow(v):
        if v > 0:  return f"🟢 +{v/1e6:.1f}M"
        if v < 0:  return f"🔴 {v/1e6:.1f}M"
        return "⬜ —"

    r3a.metric("Foreign 5D",  _flow(f5))
    r3b.metric("Foreign 20D", _flow(f20))
    r3c.metric("Foreign 60D", _flow(f60))
    r3d.metric("F-ZScore",    f"{fz:.2f}  {'📈' if fz > 1 else ('📉' if fz < -1 else '➡️')}")

    st.caption(
        f"**{ticker} {name}** | {ind} | "
        f"Moat Score = ROE rank + Foreign Z-Score + MA120 margin + RSI momentum"
    )


# ══════════════════════════════════════════════════════════════════════════════
tab_screen, tab_map, tab_moat, tab_sector = st.tabs([
    "📊 Screener", "🌏 Heat Map", "💎 千元股 Moat", "📈 Sectors"
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Screener
# ══════════════════════════════════════════════════════════════════════════════
with tab_screen:
    st.subheader("Stock Screener")

    with st.sidebar:
        st.header("🔧 Filters")

        all_industries = sorted(master["industry"].dropna().unique().tolist())
        sel_industries = st.multiselect("Industry 產業", all_industries, placeholder="All industries")

        price_min, price_max = st.slider("Price Range (TWD)", 0, 2000, (0, 2000), step=10)
        chg_min, chg_max     = st.slider("Change % Range",   -10.0, 10.0, (-10.0, 10.0), step=0.5)

        has_rsi = master["RSI"].notna().any()
        rsi_min, rsi_max = (0, 100)
        if has_rsi:
            rsi_min, rsi_max = st.slider("RSI Range", 0, 100, (0, 100), step=5)

        pe_max = st.number_input("Max P/E Ratio", min_value=0.0, value=0.0, step=5.0,
                                  help="0 = no filter")

        signal_only = st.toggle("Signal stocks only 🚀", value=False)

        cat_opts = ["全部"] + sorted([c for c in master["category"].dropna().unique() if c])
        sel_cat  = st.selectbox("Category", cat_opts)

    # Apply filters
    fdf = master.copy()
    if sel_industries:
        fdf = fdf[fdf["industry"].isin(sel_industries)]
    if "close" in fdf.columns:
        fdf = fdf[fdf["close"].fillna(0).between(price_min, price_max)]
    if "change_pct" in fdf.columns:
        fdf = fdf[fdf["change_pct"].fillna(0).between(chg_min, chg_max)]
    if has_rsi:
        mask = fdf["RSI"].isna() | fdf["RSI"].between(rsi_min, rsi_max)
        fdf = fdf[mask]
    if pe_max > 0 and "pe_ratio" in fdf.columns:
        fdf = fdf[fdf["pe_ratio"].fillna(999) <= pe_max]
    if signal_only:
        fdf = fdf[fdf["is_signal"] == True]
    if sel_cat != "全部":
        fdf = fdf[fdf["category"] == sel_cat]

    st.caption(f"Showing **{len(fdf)}** stocks  (total universe: {len(master)})")

    # Build display dataframe
    display_cols = {
        "ticker":        "Ticker",
        "co_name":       "Name",
        "industry":      "Industry",
        "close":         "Price",
        "change_pct":    "Chg%",
        "volume":        "Volume",
        "pe_ratio":      "P/E",
        "roe":           "ROE%",
        "RSI":           "RSI",
        "bias":          "Bias%",
        "score":         "Score",
        "category":      "Category",
    }
    show_cols = [c for c in display_cols if c in fdf.columns]
    disp = fdf[show_cols].rename(columns=display_cols).reset_index(drop=True)

    col_cfg = {
        "Ticker":   st.column_config.TextColumn("Ticker", width="small"),
        "Name":     st.column_config.TextColumn("Name", width="medium"),
        "Industry": st.column_config.TextColumn("Industry", width="medium"),
        "Price":    st.column_config.NumberColumn("Price (TWD)", format="%.1f"),
        "Chg%":     st.column_config.NumberColumn("Chg%", format="%.2f%%"),
        "Volume":   st.column_config.NumberColumn("Volume", format="%d"),
        "P/E":      st.column_config.NumberColumn("P/E", format="%.1f"),
        "ROE%":     st.column_config.NumberColumn("ROE%", format="%.1f"),
        "RSI":      st.column_config.NumberColumn("RSI", format="%.1f"),
        "Bias%":    st.column_config.NumberColumn("Bias%", format="%.1f"),
        "Score":    st.column_config.NumberColumn("Score", format="%.2f"),
        "Category": st.column_config.TextColumn("Category"),
    }

    st.dataframe(
        disp,
        column_config=col_cfg,
        use_container_width=True,
        height=520,
    )

    # Download button
    csv = disp.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇ Download CSV", csv, f"tws_screener_{date_label}.csv", "text/csv")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Heat Map
# ══════════════════════════════════════════════════════════════════════════════
with tab_map:
    if master.empty or "change_pct" not in master.columns:
        st.info("No market data available.")
    else:
        m = master.copy()
        m["industry"]   = m["industry"].fillna("其他").str.strip()
        m["change_pct"] = m["change_pct"].fillna(0)
        m["value"]      = m.get("value", pd.Series(0, index=m.index)).fillna(0)
        m["tile_size"]  = np.log1p(m["value"] / 1_000_000).clip(lower=0.3)
        m["display"]    = m["co_name"].fillna(m["ticker"])

        industries = sorted(m["industry"].unique().tolist())
        labels  = ["大盤"] + industries + m["ticker"].tolist()
        parents = [""]    + ["大盤"] * len(industries) + m["industry"].tolist()
        values  = [0]     + [0] * len(industries)      + m["tile_size"].tolist()
        colors  = [np.nan]+ [np.nan] * len(industries) + m["change_pct"].clip(-10, 10).tolist()

        def _tile(r):
            a = "▲" if r["change_pct"] > 0 else ("▼" if r["change_pct"] < 0 else "─")
            lu = " 🔥" if r.get("is_limit_up") else (" 🧊" if r.get("is_limit_down") else "")
            return f"<b>{r['ticker']}</b><br>{r['display']}<br>{a}{r['change_pct']:+.1f}%{lu}"

        def _hover(r):
            return (
                f"<b>{r['ticker']} {r['display']}</b><br>"
                f"產業: {r['industry']}<br>"
                f"收盤: {r.get('close', 'N/A')}  {r['change_pct']:+.2f}%<br>"
                f"成交值: {r.get('value', 0) / 1e8:.1f} 億"
            )

        tile_texts  = [""] + [f"<b>{i}</b>" for i in industries] + [_tile(r)  for _, r in m.iterrows()]
        hover_texts = [""] + industries                           + [_hover(r) for _, r in m.iterrows()]

        n_up = int((m["change_pct"] > 0).sum())
        n_dn = int((m["change_pct"] < 0).sum())

        fig = go.Figure(go.Treemap(
            labels=labels, parents=parents, values=values,
            text=tile_texts, customdata=hover_texts,
            textinfo="text",
            hovertemplate="%{customdata}<extra></extra>",
            textfont=dict(size=12, color="white", family="sans-serif"),
            marker=dict(
                colors=colors, colorscale=_DIVERGING, cmin=-10, cmax=10,
                showscale=True,
                colorbar=dict(
                    title=dict(text="% Change", font=dict(color="#ccc", size=11)),
                    thickness=14, tickvals=[-10, -5, 0, 5, 10],
                    ticktext=["-10%", "-5%", "0%", "+5%", "+10%"],
                    tickfont=dict(color="#ccc", size=10),
                    bgcolor="rgba(0,0,0,0)",
                ),
                line=dict(color="#111", width=0.8),
                pad=dict(t=22, l=4, r=4, b=4),
            ),
            root_color="#111111",
            pathbar=dict(visible=True, thickness=20),
        ))
        fig.update_layout(
            title=dict(
                text=f"TWSE Market Map — {date_label} | ▲ {n_up}  ▼ {n_dn}",
                font=dict(color="#eee", size=15), x=0.5, xanchor="center",
            ),
            template="plotly_dark", paper_bgcolor="#111111",
            height=740, margin=dict(l=8, r=8, t=52, b=8),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Click any industry sector to drill down. Tile size = log(trading value).")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — 千元股 Moat Leaders
# ══════════════════════════════════════════════════════════════════════════════
with tab_moat:
    st.subheader("💎 高價潛力股 — Tech Moat Leaders (Price ≥ 500 TWD)")
    st.caption(
        "Companies trading above 500 TWD typically have strong technological moats. "
        "Near/above 1000 TWD (千元股) are Taiwan's undisputed industry leaders."
    )

    MOAT_THRESHOLD = st.slider("Min Price Threshold (TWD)", 300, 1500, 500, step=100)

    if "close" not in master.columns:
        st.info("Price data not available.")
    else:
        hv = master[master["close"].fillna(0) >= MOAT_THRESHOLD].copy()

        if hv.empty:
            st.info(f"No stocks ≥ {MOAT_THRESHOLD} TWD found in today's data.")
        else:
            # Compute composite moat score (normalized 0–100)
            def _moat_score(row):
                s = 0.0
                # 1. ROE quality (0–30 pts)
                try:
                    roe = float(row.get("roe", 0) or 0)
                    s += min(30, max(0, roe * 1.5))
                except Exception:
                    pass
                # 2. Foreign 60-day flow (0–30 pts)
                try:
                    f_z = float(row.get("f_zscore", 0) or 0)
                    s += min(30, max(0, f_z * 15))
                except Exception:
                    pass
                # 3. Price above MA120 margin (0–20 pts)
                try:
                    price = float(row.get("close", 0) or 0)
                    ma120 = float(row.get("MA120", price) or price)
                    if ma120 > 0:
                        margin_pct = (price - ma120) / ma120 * 100
                        s += min(20, max(0, margin_pct * 2))
                except Exception:
                    pass
                # 4. Momentum RSI 50–75 zone (0–20 pts)
                try:
                    rsi = float(row.get("RSI", 50) or 50)
                    if 50 <= rsi <= 75:
                        s += min(20, (rsi - 50) / 25 * 20)
                except Exception:
                    pass
                return round(min(s, 100), 1)

            hv["moat_score"] = hv.apply(_moat_score, axis=1)
            hv = hv.sort_values("moat_score", ascending=False)

            # Summary metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total 高價股", f"{len(hv)}")
            c2.metric("千元股 (≥1000)", f"{(hv['close'] >= 1000).sum()}")
            hv_signals = (hv["category"] == "high_value_moat").sum()
            c3.metric("Today's Moat Signals", f"{hv_signals}")
            avg_rsi = hv["RSI"].dropna().mean()
            c4.metric("Avg RSI", f"{avg_rsi:.1f}" if not np.isnan(avg_rsi) else "N/A")

            st.divider()

            # Display table
            hv_disp_cols = {
                "ticker": "Ticker", "co_name": "Name", "industry": "Industry",
                "close": "Price", "change_pct": "Chg%", "pe_ratio": "P/E",
                "roe": "ROE%", "dividend_yield": "Div%",
                "RSI": "RSI", "f_zscore": "F-ZScore",
                "moat_score": "Moat Score",
                "category": "Signal",
            }
            show_hv = [c for c in hv_disp_cols if c in hv.columns]
            hv_table = hv[show_hv].rename(columns=hv_disp_cols).reset_index(drop=True)

            hv_cfg = {
                "Ticker":     st.column_config.TextColumn("Ticker", width="small"),
                "Name":       st.column_config.TextColumn("Name",   width="medium"),
                "Industry":   st.column_config.TextColumn("Industry"),
                "Price":      st.column_config.NumberColumn("Price",      format="%.1f TWD"),
                "Chg%":       st.column_config.NumberColumn("Chg%",       format="%.2f%%"),
                "P/E":        st.column_config.NumberColumn("P/E",        format="%.1f"),
                "ROE%":       st.column_config.NumberColumn("ROE%",       format="%.1f"),
                "Div%":       st.column_config.NumberColumn("Div%",       format="%.2f"),
                "RSI":        st.column_config.NumberColumn("RSI",        format="%.1f"),
                "F-ZScore":   st.column_config.NumberColumn("F-ZScore",   format="%.2f"),
                "Moat Score": st.column_config.ProgressColumn("Moat Score", min_value=0, max_value=100, format="%.1f"),
                "Signal":     st.column_config.TextColumn("Signal"),
            }
            st.dataframe(hv_table, column_config=hv_cfg, use_container_width=True, height=480)

            # Moat explanations for top 5
            st.divider()
            st.subheader("🏰 Why These Stocks Have Moats")
            top5 = hv.head(5)
            for _, row in top5.iterrows():
                ticker = str(row["ticker"])
                name   = row.get("co_name", ticker)
                price  = row.get("close", 0)
                roe    = row.get("roe", "N/A")
                ind    = row.get("industry", "")
                score  = row.get("moat_score", 0)

                with st.expander(
                    f"{'⭐' if row.get('category') == 'high_value_moat' else '💎'} "
                    f"{ticker} {name} — {price:.0f} TWD  |  Moat: {score:.0f}/100"
                ):
                    _finviz_moat_card(row, ticker, name, ind, price, roe, score)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Sectors
# ══════════════════════════════════════════════════════════════════════════════
with tab_sector:
    st.subheader("📈 Sector Performance")

    if master.empty or "industry" not in master.columns:
        st.info("No sector data available.")
    else:
        sec = (
            master.groupby("industry")
            .agg(
                avg_chg=("change_pct", "mean"),
                avg_pe =("pe_ratio",   "mean"),
                avg_roe=("roe",        "mean"),
                n_up   =("change_pct", lambda x: (x > 0).sum()),
                n_dn   =("change_pct", lambda x: (x < 0).sum()),
                total  =("ticker",     "count"),
                total_val=("value",    "sum"),
            )
            .reset_index()
            .sort_values("avg_chg", ascending=False)
        )

        # Best ticker per sector
        if "close" in master.columns:
            best = (
                master.sort_values("change_pct", ascending=False)
                .groupby("industry")
                .first()[["ticker", "co_name", "change_pct"]]
                .reset_index()
                .rename(columns={"ticker": "best_ticker", "co_name": "best_name", "change_pct": "best_chg"})
            )
            sec = sec.merge(best, on="industry", how="left")

        # Bar chart
        fig_sec = go.Figure(go.Bar(
            x=sec["avg_chg"].round(2),
            y=sec["industry"],
            orientation="h",
            marker_color=["#43a047" if v > 0 else "#ef5350" for v in sec["avg_chg"]],
            text=[f"{v:+.2f}%" for v in sec["avg_chg"]],
            textposition="outside",
        ))
        fig_sec.update_layout(
            title=f"Sector Avg Change% — {date_label}",
            template="plotly_dark",
            paper_bgcolor="#111111",
            height=max(400, len(sec) * 22),
            margin=dict(l=160, r=60, t=40, b=20),
            xaxis_title="Avg Change %",
        )
        st.plotly_chart(fig_sec, use_container_width=True)

        st.divider()

        # Summary table
        disp_sec = sec.copy()
        rename_map = {
            "industry":  "Sector",
            "avg_chg":   "Avg Chg%",
            "avg_pe":    "Avg P/E",
            "avg_roe":   "Avg ROE%",
            "n_up":      "↑ Up",
            "n_dn":      "↓ Down",
            "total":     "# Stocks",
            "total_val": "Total Value",
        }
        if "best_ticker" in disp_sec.columns:
            rename_map["best_ticker"] = "Best Ticker"
        disp_sec = disp_sec[[c for c in rename_map if c in disp_sec.columns]].rename(columns=rename_map)

        sec_cfg = {
            "Sector":      st.column_config.TextColumn("Sector", width="medium"),
            "Avg Chg%":    st.column_config.NumberColumn("Avg Chg%", format="%.2f%%"),
            "Avg P/E":     st.column_config.NumberColumn("Avg P/E",  format="%.1f"),
            "Avg ROE%":    st.column_config.NumberColumn("Avg ROE%", format="%.1f"),
            "↑ Up":        st.column_config.NumberColumn("↑ Up",    format="%d"),
            "↓ Down":      st.column_config.NumberColumn("↓ Down",  format="%d"),
            "# Stocks":    st.column_config.NumberColumn("# Stocks", format="%d"),
            "Total Value": st.column_config.NumberColumn("Total Value (億)", format="%.0f"),
            "Best Ticker": st.column_config.TextColumn("Best Ticker"),
        }
        if "Total Value" in disp_sec.columns:
            disp_sec["Total Value"] = disp_sec["Total Value"] / 1e8

        st.dataframe(disp_sec, column_config=sec_cfg, use_container_width=True, height=500)
