"""
Taiwan Market Map — interactive Plotly treemap + RSI signal board.

Tabs:
  1. Market Map   — full TWSE ~1000 stocks, red/green % change, hover details
  2. Signal Board — RSI bar chart for all tracked tickers (signal / watch / neutral)
  3. Sector Zoom  — click any sector for a focused treemap
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

st.set_page_config(page_title="TW Market Map", page_icon="🗺️", layout="wide")

st.title("🗺️ Taiwan Market Map")
st.caption("Interactive TWSE heatmap — hover any tile for details, select sectors for zoom")

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner="Fetching TWSE market data…")
def _load_market(date_str: str) -> pd.DataFrame:
    return fetch_twse_all_prices(date_str)


@st.cache_data(ttl=300, show_spinner="Loading universe snapshot…")
def _load_universe() -> pd.DataFrame:
    p = BASE_DIR / "data" / "company" / "universe_snapshot.csv"
    if not p.exists():
        # fallback to today's signals only
        p2 = BASE_DIR / "current_trending.csv"
        if not p2.exists():
            return pd.DataFrame()
        df = pd.read_csv(p2, dtype={"ticker": str})
        df["is_signal"] = True
        return df
    df = pd.read_csv(p, dtype={"ticker": str})
    df["is_signal"] = df["is_signal"].astype(str).str.lower().isin(["true", "1", "yes"])
    return df


trading_date = get_last_trading_date()
date_str     = trading_date.strftime("%Y%m%d")
date_label   = trading_date.strftime("%Y-%m-%d")

col_date, col_refresh = st.columns([5, 1])
col_date.caption(f"Trading date: **{date_label}**")
if col_refresh.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

price_df   = _load_market(date_str)
mapping_df = load_company_mapping()
universe_df = _load_universe()

st.divider()

# ── Colorscale (shared by market map + sector zoom) ───────────────────────────
_DIVERGING = [
    [0.00, "#b71c1c"],   # -10% deep red
    [0.25, "#ef5350"],   # -5%
    [0.43, "#ffcdd2"],   # -2% light red
    [0.50, "#424242"],   #  0% dark gray
    [0.57, "#c8e6c9"],   # +2% light green
    [0.75, "#43a047"],   # +5%
    [1.00, "#00e676"],   # +10% bright green / 漲停
]

_SIGNAL_SCALE = [
    [0.00, "#3a3a3a"],
    [0.07, "#3a3a3a"],
    [0.09, "#0d2b0d"],
    [0.30, "#1b5e20"],
    [0.60, "#2e7d32"],
    [0.82, "#43a047"],
    [1.00, "#00e676"],
]

# ══════════════════════════════════════════════════════════════════════════════
tab_map, tab_board, tab_zoom = st.tabs([
    "🌏 Market Map", "📊 Signal Board", "🔍 Sector Zoom"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Full TWSE market treemap
# ══════════════════════════════════════════════════════════════════════════════
with tab_map:
    if price_df.empty:
        st.info(
            "No market data found for today. "
            "TWSE usually publishes data after 14:30 TST on trading days."
        )
    else:
        merged = price_df.copy()
        if not mapping_df.empty and "industry" in mapping_df.columns:
            merged = merged.merge(
                mapping_df[["ticker", "name", "industry"]].rename(columns={"name": "co_name"}),
                on="ticker", how="left",
            )
        else:
            merged["co_name"]  = merged.get("name", merged["ticker"])
            merged["industry"] = "其他"

        merged["industry"]    = merged["industry"].fillna("其他").str.strip()
        merged["display_name"] = merged["co_name"].where(
            merged["co_name"].notna(), merged.get("name", merged["ticker"])
        )
        merged["change_pct"] = pd.to_numeric(merged["change_pct"], errors="coerce").fillna(0)
        merged["value"]      = pd.to_numeric(merged["value"],      errors="coerce").fillna(0)
        merged["tile_size"]  = np.log1p(merged["value"] / 1_000_000).clip(lower=0.3)

        industries = sorted(merged["industry"].unique().tolist())

        labels  = ["大盤"] + industries + merged["ticker"].tolist()
        parents = [""]    + ["大盤"] * len(industries) + merged["industry"].tolist()
        values  = [0]     + [0] * len(industries)     + merged["tile_size"].tolist()
        colors  = [np.nan] + [np.nan] * len(industries) + merged["change_pct"].clip(-10, 10).tolist()

        def _tile_text(row):
            arrow = "▲" if row["change_pct"] > 0 else ("▼" if row["change_pct"] < 0 else "─")
            limit = " 🔥" if row.get("is_limit_up") else (" 🧊" if row.get("is_limit_down") else "")
            return (
                f"<b>{row['ticker']}</b><br>{row['display_name']}<br>"
                f"{arrow}{row['change_pct']:+.1f}%{limit}"
            )

        def _hover_text(row):
            return (
                f"<b>{row['ticker']} {row['display_name']}</b><br>"
                f"產業: {row['industry']}<br>"
                f"收盤: {row.get('close', 'N/A')}  {row['change_pct']:+.2f}%<br>"
                f"成交值: {row['value'] / 1e8:.1f} 億"
            )

        tile_texts  = [""] + [f"<b>{i}</b>" for i in industries] + [_tile_text(r)  for _, r in merged.iterrows()]
        hover_texts = [""] + industries                          + [_hover_text(r) for _, r in merged.iterrows()]

        n_up  = int((merged["change_pct"] > 0).sum())
        n_dn  = int((merged["change_pct"] < 0).sum())
        n_lu  = int(merged.get("is_limit_up",  pd.Series(dtype=bool)).sum()) if "is_limit_up"  in merged.columns else 0
        n_ld  = int(merged.get("is_limit_down", pd.Series(dtype=bool)).sum()) if "is_limit_down" in merged.columns else 0

        fig_map = go.Figure(go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            text=tile_texts,
            customdata=hover_texts,
            textinfo="text",
            hovertemplate="%{customdata}<extra></extra>",
            textfont=dict(size=12, color="white", family="sans-serif"),
            marker=dict(
                colors=colors,
                colorscale=_DIVERGING,
                cmin=-10, cmax=10,
                showscale=True,
                colorbar=dict(
                    title=dict(text="% Change", font=dict(color="#ccc", size=11)),
                    thickness=14,
                    tickvals=[-10, -5, 0, 5, 10],
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
        fig_map.update_layout(
            title=dict(
                text=(
                    f"TWSE Market Map — {date_label} | "
                    f"▲ {n_up}  ▼ {n_dn}  🔥漲停 {n_lu}  🧊跌停 {n_ld}"
                ),
                font=dict(color="#eee", size=15),
                x=0.5, xanchor="center",
            ),
            template="plotly_dark",
            paper_bgcolor="#111111",
            height=720,
            margin=dict(l=8, r=8, t=52, b=8),
        )
        st.plotly_chart(fig_map, use_container_width=True)
        st.caption(
            "Click any **industry sector** tile to drill in. "
            "Tile size = log(trading value). Hover for ticker details."
        )

        # Market stats strip
        avg_chg = merged["change_pct"].mean()
        tot_val = merged["value"].sum() / 1e12  # 兆
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total Securities", len(merged))
        s2.metric("Advancing / Declining", f"{n_up} / {n_dn}")
        s3.metric("Market Avg Change", f"{avg_chg:+.2f}%")
        s4.metric("Total Trading Value", f"{tot_val:.2f} 兆 NTD")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — RSI Signal Board
# ══════════════════════════════════════════════════════════════════════════════
with tab_board:
    if universe_df.empty:
        st.info("No universe data found. Run `python master_run.py` to generate signals.")
    else:
        df = universe_df.copy()

        # Merge display names
        if not mapping_df.empty and "name" in mapping_df.columns:
            df = df.merge(mapping_df[["ticker", "name"]], on="ticker", how="left")
            df["label"] = df["ticker"] + " " + df["name"].fillna(df["ticker"])
        else:
            df["label"] = df["ticker"]

        for col in ["RSI", "MA120", "price", "bias", "score"]:
            df[col] = pd.to_numeric(df.get(col, pd.Series(dtype=float)), errors="coerce")
        df["score"]     = df["score"].fillna(0)
        df["is_signal"] = df["is_signal"].astype(str).str.lower().isin(["true", "1", "yes"])

        # ── Filter controls ───────────────────────────────────────────────────
        f_col1, f_col2, f_col3 = st.columns([2, 2, 2])
        zone_filter = f_col1.selectbox(
            "Show",
            ["All", "Signals only", "Watch zone (RSI < 50)", "Below MA120"],
        )
        if not mapping_df.empty and "industry" in mapping_df.columns:
            industries_avail = ["All sectors"] + sorted(
                df.merge(mapping_df[["ticker", "industry"]], on="ticker", how="left")["industry"]
                .dropna().unique().tolist()
            )
        else:
            industries_avail = ["All sectors"]
        sector_filter = f_col2.selectbox("Sector", industries_avail)
        rsi_max = f_col3.slider("RSI max", 10, 100, 100, step=5)

        # Merge industry for filtering
        if not mapping_df.empty and "industry" in mapping_df.columns:
            df = df.merge(mapping_df[["ticker", "industry"]], on="ticker", how="left")

        if sector_filter != "All sectors" and "industry" in df.columns:
            df = df[df["industry"] == sector_filter]

        df = df[df["RSI"].notna() & (df["RSI"] <= rsi_max)]

        if zone_filter == "Signals only":
            df = df[df["is_signal"]]
        elif zone_filter == "Watch zone (RSI < 50)":
            df = df[df["RSI"] < 50]
        elif zone_filter == "Below MA120":
            df = df[df["price"].notna() & df["MA120"].notna() & (df["price"] <= df["MA120"])]

        df = df.sort_values("RSI").reset_index(drop=True)

        if df.empty:
            st.info("No tickers match the selected filters.")
        else:
            def _bar_color(row):
                if row["is_signal"]:
                    return "#00e676"
                if pd.notna(row["price"]) and pd.notna(row["MA120"]) and row["price"] <= row["MA120"]:
                    return "#ef5350"
                if row["RSI"] < 50:
                    return "#ffa726"
                return "#78909c"

            def _annotation(row):
                parts = []
                if pd.notna(row["bias"]):
                    parts.append(f"Bias {row['bias']:.1f}%")
                if row["is_signal"]:
                    parts.append(f"⭐{row['score']:.1f}")
                return "  ".join(parts)

            colors = [_bar_color(r) for _, r in df.iterrows()]
            annots = [_annotation(r) for _, r in df.iterrows()]
            n_sig  = int(df["is_signal"].sum())
            n_tot  = len(df)

            bar_h   = max(20, min(36, 600 // max(n_tot, 1)))
            chart_h = max(400, n_tot * bar_h + 120)

            fig_board = go.Figure()
            fig_board.add_trace(go.Bar(
                x=df["RSI"],
                y=df["label"],
                orientation="h",
                marker_color=colors,
                text=annots,
                textposition="outside",
                textfont=dict(color="#cccccc", size=10),
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "RSI: %{x:.1f}<br>"
                    "<extra></extra>"
                ),
                customdata=df[["score", "bias", "is_signal"]].values,
            ))
            fig_board.add_vline(x=35, line=dict(color="#00e676", width=1.5, dash="dash"),
                                annotation_text="Oversold 35",
                                annotation_font=dict(color="#00e676", size=11),
                                annotation_position="top right")
            fig_board.add_vline(x=50, line=dict(color="#ffa726", width=1, dash="dot"),
                                annotation_text="Mid 50",
                                annotation_font=dict(color="#ffa726", size=11),
                                annotation_position="top right")
            fig_board.update_layout(
                title=dict(
                    text=f"TWS Signal Board — {n_sig} 訊號 / {n_tot} tracked  ({date_label})",
                    font=dict(color="#eee", size=14),
                    x=0.5, xanchor="center",
                ),
                xaxis=dict(
                    title="RSI (14)", range=[0, 118],
                    gridcolor="#2a2a2a",
                    tickfont=dict(color="#aaa"),
                    titlefont=dict(color="#aaa"),
                ),
                yaxis=dict(tickfont=dict(color="#cccccc", size=10), automargin=True),
                template="plotly_dark",
                paper_bgcolor="#0d1117",
                plot_bgcolor="#0d1117",
                height=chart_h,
                margin=dict(l=10, r=140, t=55, b=30),
                showlegend=False,
            )
            st.plotly_chart(fig_board, use_container_width=True)

            # Legend
            leg_cols = st.columns(4)
            leg_cols[0].markdown("🟢 **Signal** — RSI<35 + Bias<-2% + above MA120")
            leg_cols[1].markdown("🟠 **Watch** — RSI<50, above MA120")
            leg_cols[2].markdown("🔴 **Below MA120** — trend broken")
            leg_cols[3].markdown("⬜ **Neutral** — RSI≥50")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Sector Zoom
# ══════════════════════════════════════════════════════════════════════════════
with tab_zoom:
    if price_df.empty or mapping_df.empty:
        st.info("Market data or company mapping not available.")
    else:
        merged_z = price_df.merge(
            mapping_df[["ticker", "name", "industry"]].rename(columns={"name": "co_name"}),
            on="ticker", how="left",
        )
        merged_z["industry"]    = merged_z["industry"].fillna("其他").str.strip()
        merged_z["change_pct"]  = pd.to_numeric(merged_z["change_pct"], errors="coerce").fillna(0)
        merged_z["value"]       = pd.to_numeric(merged_z["value"],      errors="coerce").fillna(0)
        merged_z["display_name"] = merged_z["co_name"].where(
            merged_z["co_name"].notna(), merged_z.get("name", merged_z["ticker"])
        )

        # Sector selector — sorted by avg change desc (most active sector first)
        sector_stats = (
            merged_z.groupby("industry")
            .agg(avg_chg=("change_pct", "mean"), count=("ticker", "count"), total_val=("value", "sum"))
            .sort_values("total_val", ascending=False)
            .reset_index()
        )
        sector_list = sector_stats["industry"].tolist()

        z_col1, z_col2 = st.columns([3, 1])
        chosen_sector = z_col1.selectbox(
            "Select sector",
            sector_list,
            format_func=lambda s: (
                f"{s}  "
                f"({sector_stats.loc[sector_stats['industry']==s, 'count'].values[0]:.0f} stocks,  "
                f"avg {sector_stats.loc[sector_stats['industry']==s, 'avg_chg'].values[0]:+.2f}%)"
            ),
        )

        sector_df = merged_z[merged_z["industry"] == chosen_sector].copy()
        sector_df["tile_size"] = np.log1p(sector_df["value"] / 1_000_000).clip(lower=0.3)

        if len(sector_df) < 2:
            st.info("Not enough stocks in this sector to display.")
        else:
            n_up_z = int((sector_df["change_pct"] > 0).sum())
            n_dn_z = int((sector_df["change_pct"] < 0).sum())
            avg_z  = sector_df["change_pct"].mean()

            labels_z  = [chosen_sector] + sector_df["ticker"].tolist()
            parents_z = [""]            + [chosen_sector] * len(sector_df)
            values_z  = [0]             + sector_df["tile_size"].tolist()
            colors_z  = [np.nan]        + sector_df["change_pct"].clip(-10, 10).tolist()

            def _sz_tile(row):
                arrow = "▲" if row["change_pct"] > 0 else ("▼" if row["change_pct"] < 0 else "─")
                limit = " 🔥" if row.get("is_limit_up") else (" 🧊" if row.get("is_limit_down") else "")
                return (
                    f"<b>{row['ticker']}</b><br>{row['display_name']}<br>"
                    f"{arrow}{row['change_pct']:+.1f}%{limit}"
                )

            def _sz_hover(row):
                return (
                    f"<b>{row['ticker']} {row['display_name']}</b><br>"
                    f"收盤: {row.get('close', 'N/A')}  {row['change_pct']:+.2f}%<br>"
                    f"成交值: {row['value'] / 1e8:.1f} 億"
                )

            tile_texts_z  = [f"<b>{chosen_sector}</b>"] + [_sz_tile(r)  for _, r in sector_df.iterrows()]
            hover_texts_z = [chosen_sector]              + [_sz_hover(r) for _, r in sector_df.iterrows()]

            fig_zoom = go.Figure(go.Treemap(
                labels=labels_z,
                parents=parents_z,
                values=values_z,
                text=tile_texts_z,
                customdata=hover_texts_z,
                textinfo="text",
                hovertemplate="%{customdata}<extra></extra>",
                textfont=dict(size=14, color="white", family="sans-serif"),
                marker=dict(
                    colors=colors_z,
                    colorscale=_DIVERGING,
                    cmin=-10, cmax=10,
                    showscale=True,
                    colorbar=dict(
                        title=dict(text="% Change", font=dict(color="#ccc", size=11)),
                        thickness=14,
                        tickvals=[-10, -5, 0, 5, 10],
                        ticktext=["-10%", "-5%", "0%", "+5%", "+10%"],
                        tickfont=dict(color="#ccc", size=10),
                        bgcolor="rgba(0,0,0,0)",
                    ),
                    line=dict(color="#111", width=1),
                    pad=dict(t=24, l=5, r=5, b=5),
                ),
                root_color="#111111",
                pathbar=dict(visible=False),
            ))
            fig_zoom.update_layout(
                title=dict(
                    text=(
                        f"{chosen_sector} — {date_label} | "
                        f"▲{n_up_z}  ▼{n_dn_z}  avg {avg_z:+.2f}%  "
                        f"({len(sector_df)} stocks)"
                    ),
                    font=dict(color="#eee", size=14),
                    x=0.5, xanchor="center",
                ),
                template="plotly_dark",
                paper_bgcolor="#111111",
                height=580,
                margin=dict(l=8, r=8, t=52, b=8),
            )
            st.plotly_chart(fig_zoom, use_container_width=True)

            # Top movers table for this sector
            top = sector_df.nlargest(5, "change_pct")[["ticker", "display_name", "change_pct", "value"]]
            bot = sector_df.nsmallest(5, "change_pct")[["ticker", "display_name", "change_pct", "value"]]

            t1, t2 = st.columns(2)
            with t1:
                st.markdown("**Top gainers**")
                st.dataframe(
                    top.rename(columns={"display_name": "name", "change_pct": "chg%", "value": "value(NTD)"})
                    .style.format({"chg%": "{:+.2f}%", "value(NTD)": "{:,.0f}"})
                    .applymap(lambda v: "color:#00e676" if isinstance(v, float) and v > 0 else "", subset=["chg%"]),
                    hide_index=True, use_container_width=True,
                )
            with t2:
                st.markdown("**Top decliners**")
                st.dataframe(
                    bot.rename(columns={"display_name": "name", "change_pct": "chg%", "value": "value(NTD)"})
                    .style.format({"chg%": "{:+.2f}%", "value(NTD)": "{:,.0f}"})
                    .applymap(lambda v: "color:#ef5350" if isinstance(v, float) and v < 0 else "", subset=["chg%"]),
                    hide_index=True, use_container_width=True,
                )
