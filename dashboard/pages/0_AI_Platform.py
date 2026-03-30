"""
AI Platform — unified TW + US signal view powered by Claude.

Sections:
  1. Unified Signal Board  — TW + US signals merged, ranked by score, with AI one-liners
  2. Cross-Market View     — Claude's cross-market commentary + scatter plot
  3. Stock Deep Dive       — select any ticker → full AI analysis
  4. Portfolio AI          — Claude commentary on current holdings
  5. AI Chat               — streaming Q&A grounded in today's signals + portfolio
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dashboard.data_helpers import get_broker_manager, BASE_DIR

st.set_page_config(page_title="AI Platform", page_icon="🤖", layout="wide")

# ── API key check ─────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from ai.analyst import is_configured as ai_ok
AI_ON = ai_ok()

if not AI_ON:
    st.warning(
        "🔑 **ANTHROPIC_API_KEY not set** — AI analysis features are disabled.\n\n"
        "Add `ANTHROPIC_API_KEY=sk-ant-...` to your `.env` file and restart the dashboard.",
        icon="⚠️",
    )

# ── Load unified signals ───────────────────────────────────────────────────────
from ai.unified_signals import load_all_signals, enrich_with_ai, build_context_summary

@st.cache_data(ttl=300, show_spinner="Loading signals…")
def _signals():
    return load_all_signals(str(BASE_DIR))

all_signals = _signals()
tw_signals  = all_signals[all_signals["market"] == "TW"] if not all_signals.empty else pd.DataFrame()
us_signals  = all_signals[all_signals["market"] == "US"] if not all_signals.empty else pd.DataFrame()

# ── Page title ────────────────────────────────────────────────────────────────
st.title("🤖 AI Trading Platform")
st.caption("Unified Taiwan × US mean-reversion signals — powered by Claude")

col_ref, col_aistat = st.columns([3, 1])
col_ref.markdown(
    f"**Today's signals:** {len(tw_signals)} TW · {len(us_signals)} US · "
    f"{len(all_signals)} total"
)
col_aistat.markdown("🟢 AI On" if AI_ON else "🔴 AI Off")

if st.button("🔄 Refresh data + AI"):
    st.cache_data.clear()
    st.rerun()

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Signal Board", "🌍 Cross-Market", "🔍 Deep Dive", "💼 Portfolio AI", "💬 Chat"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Unified Signal Board
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Unified Signal Board — TW + US")

    if all_signals.empty:
        st.info("No signals found. Run `python master_run.py` to generate today's signals.")
    else:
        # AI enrichment (cached separately)
        @st.cache_data(ttl=600, show_spinner="Running AI analysis…")
        def _enriched():
            if not AI_ON:
                df = all_signals.copy()
                df["ai_summary"] = "—"
                return df
            return enrich_with_ai(all_signals.copy())

        enriched = _enriched()

        # ── Scatter: RSI vs Bias, colored by market ──────────────────────────
        fig = px.scatter(
            enriched,
            x="bias", y="RSI",
            size="score",
            color="market",
            symbol="market",
            hover_name="ticker",
            hover_data={
                "score": ":.1f",
                "price": ":.2f",
                "bias":  ":.1f",
                "RSI":   ":.1f",
                "name":  True,
            },
            color_discrete_map={"TW": "#00b4d8", "US": "#f77f00"},
            title="Signal Landscape — RSI vs Bias (bubble size = score)",
            labels={"bias": "Bias vs MA20 (%)", "RSI": "RSI (14)"},
            template="plotly_dark",
        )
        fig.add_hline(y=35,  line=dict(color="#00e676", dash="dash", width=1),
                      annotation_text="RSI 35", annotation_font_color="#00e676")
        fig.add_vline(x=-2,  line=dict(color="#ffa726", dash="dot",  width=1),
                      annotation_text="Bias -2%", annotation_font_color="#ffa726")
        fig.update_layout(paper_bgcolor="#0d1117", height=380)
        st.plotly_chart(fig, use_container_width=True)

        # ── Table ─────────────────────────────────────────────────────────────
        display_cols = [c for c in [
            "market", "ticker", "name", "industry",
            "score", "price", "RSI", "bias", "vol_ratio",
            "news_sentiment", "ai_summary",
        ] if c in enriched.columns]

        def _score_bg(val):
            try:
                v = float(val)
                if v >= 7:   return "background-color: #1b5e20; color: white"
                elif v >= 4: return "background-color: #33691e; color: white"
                else:        return "background-color: #263238"
            except Exception:
                return ""

        styled = (
            enriched[display_cols]
            .style
            .applymap(_score_bg, subset=["score"])
            .format({
                "score": "{:.1f}",
                "price": "{:.2f}",
                "RSI":   "{:.1f}",
                "bias":  "{:.1f}%",
                "vol_ratio":      lambda v: f"{v:.1f}x" if pd.notna(v) else "N/A",
                "news_sentiment": lambda v: f"{v:+.2f}" if pd.notna(v) else "N/A",
            }, na_rep="N/A")
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)
        st.caption(f"{len(enriched)} signals — sorted by score descending")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Cross-Market Commentary
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("🌍 Cross-Market Opportunity View")

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Taiwan Signals",  len(tw_signals))
        st.metric("TW Avg Score",    f"{tw_signals['score'].mean():.1f}" if not tw_signals.empty and "score" in tw_signals else "N/A")
        st.metric("TW Avg RSI",      f"{tw_signals['RSI'].mean():.1f}"   if not tw_signals.empty and "RSI"   in tw_signals else "N/A")
    with c2:
        st.metric("US Signals",      len(us_signals))
        st.metric("US Avg Score",    f"{us_signals['score'].mean():.1f}" if not us_signals.empty and "score" in us_signals else "N/A")
        st.metric("US Avg RSI",      f"{us_signals['RSI'].mean():.1f}"   if not us_signals.empty and "RSI"   in us_signals else "N/A")

    # Market comparison bar
    if not all_signals.empty and "score" in all_signals.columns:
        fig_bar = px.bar(
            all_signals.head(20),
            x="ticker", y="score",
            color="market",
            color_discrete_map={"TW": "#00b4d8", "US": "#f77f00"},
            title="Top 20 Signals by Score",
            labels={"score": "Signal Score (0-10)", "ticker": "Ticker"},
            template="plotly_dark",
        )
        fig_bar.update_layout(paper_bgcolor="#0d1117", height=300)
        st.plotly_chart(fig_bar, use_container_width=True)

    # AI commentary
    st.markdown("#### 🤖 AI Cross-Market Commentary")
    if AI_ON:
        @st.cache_data(ttl=600, show_spinner="Claude is thinking…")
        def _cross_market_commentary():
            from ai.analyst import compare_markets
            return compare_markets(tw_signals, us_signals)

        commentary = _cross_market_commentary()
        st.markdown(commentary)
    else:
        st.info("Enable ANTHROPIC_API_KEY to get AI cross-market commentary.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Stock Deep Dive
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🔍 Stock Deep Dive")

    if all_signals.empty:
        st.info("No signals available.")
    else:
        ticker_options = all_signals["ticker"].tolist()
        selected = st.selectbox("Select signal stock", ticker_options,
                                format_func=lambda t: f"{t}  [{all_signals[all_signals['ticker']==t]['market'].values[0]}]  score {all_signals[all_signals['ticker']==t]['score'].values[0]:.1f}")

        row = all_signals[all_signals["ticker"] == selected].iloc[0]
        market = row.get("market", "?")

        # Metrics strip
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Price",     f"{row.get('price','N/A')}")
        m2.metric("RSI",       f"{row.get('RSI','N/A'):.1f}" if pd.notna(row.get("RSI")) else "N/A")
        m3.metric("Bias",      f"{row.get('bias','N/A'):.1f}%" if pd.notna(row.get("bias")) else "N/A")
        m4.metric("Score",     f"⭐ {row.get('score',0):.1f}")
        m5.metric("Vol Ratio", f"{row.get('vol_ratio','N/A'):.1f}x" if pd.notna(row.get("vol_ratio")) else "N/A")
        m6.metric("Market",    market)

        # Load OHLCV chart
        import glob as _glob
        ohlcv_dir = str(BASE_DIR / ("data/ohlcv" if market == "TW" else "data_us/ohlcv"))
        ohlcv_files = _glob.glob(os.path.join(ohlcv_dir, f"{selected}_*.csv"))
        if ohlcv_files:
            try:
                ohlcv_df = pd.read_csv(ohlcv_files[0], index_col=0)
                ohlcv_df.index = pd.to_datetime(ohlcv_df.index, errors="coerce")
                ohlcv_df = ohlcv_df.tail(60)
                for col in ["Open", "High", "Low", "Close"]:
                    ohlcv_df[col] = pd.to_numeric(ohlcv_df[col], errors="coerce")
                ohlcv_df["MA20"]  = ohlcv_df["Close"].rolling(20).mean()
                ohlcv_df["MA120"] = ohlcv_df["Close"].rolling(120).mean()

                fig_c = go.Figure()
                fig_c.add_trace(go.Candlestick(
                    x=ohlcv_df.index,
                    open=ohlcv_df["Open"], high=ohlcv_df["High"],
                    low=ohlcv_df["Low"],   close=ohlcv_df["Close"],
                    increasing_line_color="#26a69a",
                    decreasing_line_color="#ef5350",
                    name=selected,
                ))
                fig_c.add_trace(go.Scatter(x=ohlcv_df.index, y=ohlcv_df["MA20"],
                                           line=dict(color="#ffa726", width=1.2), name="MA20"))
                fig_c.add_trace(go.Scatter(x=ohlcv_df.index, y=ohlcv_df["MA120"],
                                           line=dict(color="#42a5f5", width=1.2), name="MA120"))
                fig_c.update_layout(
                    title=f"{selected} — 60-day Chart",
                    template="plotly_dark", paper_bgcolor="#0d1117",
                    xaxis_rangeslider_visible=False,
                    height=380, margin=dict(l=40, r=40, t=40, b=30),
                )
                st.plotly_chart(fig_c, use_container_width=True)
            except Exception:
                pass

        # AI analysis
        st.markdown("#### 🤖 AI Trade Thesis")
        if AI_ON:
            if st.button(f"Analyse {selected}", key="dive_btn"):
                with st.spinner("Claude is writing the analysis…"):
                    from ai.analyst import analyze_signal

                    # Gather fundamentals from mapping
                    fund = {}
                    try:
                        mapping_path = (
                            BASE_DIR / "data" / "company" / "company_mapping.csv"
                            if market == "TW"
                            else BASE_DIR / "data_us" / "company_mapping.csv"
                        )
                        if mapping_path.exists():
                            mdf = pd.read_csv(str(mapping_path), dtype={"ticker": str})
                            mrow = mdf[mdf["ticker"] == selected]
                            if not mrow.empty:
                                fund = mrow.iloc[0].to_dict()
                    except Exception:
                        pass

                    # Gather headlines
                    headlines = []
                    try:
                        from tws.utils import fetch_google_news_many
                        name_val = str(row.get("name", ""))
                        headlines = fetch_google_news_many(selected, name_val, days=7, max_items=5)
                    except Exception:
                        pass

                    analysis = analyze_signal(
                        ticker       = selected,
                        market       = market,
                        metrics      = row.to_dict(),
                        headlines    = headlines,
                        fundamentals = fund,
                    )
                st.markdown(analysis)
        else:
            st.info("Enable ANTHROPIC_API_KEY for AI analysis.")

        # Trade shortcut
        if st.button(f"⚡ Trade {selected}", key="dive_trade"):
            st.session_state["prefill_ticker"] = selected
            st.switch_page("pages/3_Trading.py")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Portfolio AI
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("💼 Portfolio AI")

    if AI_ON:
        if st.button("🤖 Analyse my portfolio", type="primary"):
            mgr = get_broker_manager()
            with st.spinner("Fetching portfolio data…"):
                positions = mgr.get_all_positions()
                balances  = mgr.get_all_balances()
            with st.spinner("Claude is reviewing your portfolio…"):
                from ai.analyst import portfolio_insights
                analysis = portfolio_insights(positions, balances)
            st.markdown(analysis)
            if not positions.empty:
                st.dataframe(positions, use_container_width=True, hide_index=True)
    else:
        st.info("Enable ANTHROPIC_API_KEY to get AI portfolio commentary.")
        mgr = get_broker_manager()
        positions = mgr.get_all_positions()
        if not positions.empty:
            st.dataframe(positions, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Streaming AI Chat
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("💬 AI Chat")
    st.caption(
        "Ask Claude anything about today's signals, your portfolio, "
        "strategy ideas, or market conditions."
    )

    if not AI_ON:
        st.info("Enable ANTHROPIC_API_KEY to use the chat interface.")
        st.stop()

    # Build context once per session
    if "chat_context" not in st.session_state:
        st.session_state["chat_context"] = build_context_summary(all_signals)

    # Initialize message history
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Render history
    for msg in st.session_state["chat_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input
    if prompt := st.chat_input("Ask about signals, portfolio, strategies…"):
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            from ai.analyst import chat_stream
            placeholder = st.empty()
            full_text = ""
            for chunk in chat_stream(
                messages = st.session_state["chat_messages"],
                context  = st.session_state["chat_context"],
            ):
                full_text += chunk
                placeholder.markdown(full_text + "▌")
            placeholder.markdown(full_text)

        st.session_state["chat_messages"].append(
            {"role": "assistant", "content": full_text}
        )

    if st.button("🗑️ Clear chat"):
        st.session_state["chat_messages"] = []
        st.rerun()
