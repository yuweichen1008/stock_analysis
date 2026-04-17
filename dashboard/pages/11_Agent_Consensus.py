"""
Multi-Agent Investment Consensus — 6 specialist AI agents evaluate each stock
through a distinct investment philosophy, then a Portfolio Manager synthesises
a final recommendation.

Agents:
  Value      — Graham / Buffett criteria (P/E, ROE, debt safety, margin of safety)
  Growth     — Lynch / Wood criteria (PEG, analyst upside, sector tailwinds)
  Technical  — MA crossover, RSI, bias depth, volume confirmation
  Sentiment  — VADER news score, analyst consensus, headlines
  Risk       — Taleb fat-tail (volatility, leverage, position sizing)
  Valuation  — Damodaran (earnings yield, DCF proxy, total shareholder yield)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dashboard.data_helpers import BASE_DIR

st.set_page_config(page_title="Agent Consensus", page_icon="🧠", layout="wide")

# ── Env + AI check ────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")
from ai.analyst import is_configured as ai_ok
AI_ON = ai_ok()

if not AI_ON:
    st.error(
        "**ANTHROPIC_API_KEY not set.** This page requires the Claude API.\n\n"
        "Add `ANTHROPIC_API_KEY=sk-ant-...` to your `.env` file and restart.",
        icon="🔑",
    )
    st.stop()

# ── Helpers ───────────────────────────────────────────────────────────────────
from ai.unified_signals import load_all_signals

SIGNAL_COLORS = {"BUY": "#26a69a", "SELL": "#ef5350", "HOLD": "#90a4ae"}
SIGNAL_ICONS  = {"BUY": "📈", "SELL": "📉", "HOLD": "⏸️"}
QUALITY_ICONS = {"complete": "✅", "partial": "⚠️", "sparse": "❌"}

AGENT_META = {
    "value":     {"label": "Value (Graham/Buffett)",    "icon": "💰"},
    "growth":    {"label": "Growth (Lynch/Wood)",       "icon": "🚀"},
    "technical": {"label": "Technical Analysis",        "icon": "📊"},
    "sentiment": {"label": "Sentiment & News",          "icon": "📰"},
    "risk":      {"label": "Risk (Taleb)",              "icon": "🛡️"},
    "valuation": {"label": "Valuation (Damodaran)",     "icon": "🔢"},
}


@st.cache_data(ttl=300, show_spinner=False)
def _load_signals():
    return load_all_signals(str(BASE_DIR))


def _run_analysis(ticker: str, market: str) -> dict:
    """Run the full 6-agent + orchestrator pipeline for one ticker."""
    from ai.agents import analyze_ticker, _load_ticker_data, orchestrate_result_to_dict
    metrics, fundamentals, headlines = _load_ticker_data(ticker, market, str(BASE_DIR))
    result = analyze_ticker(ticker, market, metrics, fundamentals, headlines)
    return orchestrate_result_to_dict(result)


def _donut_chart(agent_results: list) -> go.Figure:
    """Plotly donut chart of BUY/HOLD/SELL vote distribution."""
    counts = {"BUY": 0, "HOLD": 0, "SELL": 0}
    for a in agent_results:
        sig = a.get("signal", "HOLD")
        if sig in counts:
            counts[sig] += 1
    fig = go.Figure(go.Pie(
        labels    = list(counts.keys()),
        values    = list(counts.values()),
        hole      = 0.55,
        marker    = dict(colors=[SIGNAL_COLORS[k] for k in counts]),
        textinfo  = "label+value",
        hoverinfo = "label+percent",
    ))
    fig.update_layout(
        margin          = dict(t=0, b=0, l=0, r=0),
        height          = 200,
        showlegend      = False,
        paper_bgcolor   = "rgba(0,0,0,0)",
        plot_bgcolor    = "rgba(0,0,0,0)",
        font            = dict(color="white"),
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Page
# ══════════════════════════════════════════════════════════════════════════════
st.title("🧠 Multi-Agent Investment Consensus")
st.caption("6 specialist AI agents evaluate each stock — a Portfolio Manager synthesises the final call")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_single, tab_batch = st.tabs(["🔍 Single Ticker", "📋 Batch Analysis"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Single Ticker Analysis
# ══════════════════════════════════════════════════════════════════════════════
with tab_single:
    st.subheader("Analyse a Single Stock")

    # Controls
    c1, c2, c3 = st.columns([3, 2, 1])
    with c1:
        all_sigs = _load_signals()
        if not all_sigs.empty:
            ticker_options = all_sigs.sort_values("score", ascending=False)["ticker"].tolist()
        else:
            ticker_options = []
        ticker_input = st.text_input(
            "Ticker symbol",
            value=ticker_options[0] if ticker_options else "AAPL",
            placeholder="e.g. AAPL, TSLA, 2330",
        )
    with c2:
        market_sel = st.radio("Market", ["US", "TW"], horizontal=True)
    with c3:
        st.write("")  # spacer
        run_btn = st.button("▶ Run Analysis", type="primary", use_container_width=True)

    if not run_btn:
        st.info("Select a ticker and click **Run Analysis** to see the 6-agent breakdown.")
    else:
        ticker = ticker_input.strip().upper()
        if not ticker:
            st.warning("Please enter a ticker symbol.")
        else:
            result = None
            # ── Progress feedback ─────────────────────────────────────────────
            agent_names = ["value", "growth", "technical", "sentiment", "risk", "valuation"]
            with st.status(f"Analysing **{ticker}** ({market_sel}) …", expanded=True) as status:
                for step, name in enumerate(agent_names, 1):
                    meta = AGENT_META.get(name, {})
                    st.write(f"{meta.get('icon','•')} Running **{meta.get('label', name)}** agent…")
                st.write("🔮 Synthesising with Portfolio Manager (Sonnet)…")
                try:
                    result = _run_analysis(ticker, market_sel)
                    status.update(label=f"Analysis complete for **{ticker}**", state="complete")
                except Exception as e:
                    status.update(label=f"Analysis failed: {e}", state="error")
                    st.error(str(e))

            if result:
                # ── Orchestrator summary banner ───────────────────────────────
                final_sig = result.get("final_signal", "HOLD")
                conviction = result.get("conviction", 0)
                consensus  = result.get("consensus_score", 0.0)

                sig_color = SIGNAL_COLORS.get(final_sig, "#90a4ae")
                sig_icon  = SIGNAL_ICONS.get(final_sig, "⏸️")

                st.markdown("---")
                b1, b2, b3, b4 = st.columns(4)
                b1.metric("Final Signal", f"{sig_icon} {final_sig}")
                b2.metric("Conviction",   f"{conviction}%")
                b3.metric("Consensus",    f"{consensus*6:.0f}/6 agents")
                b4.metric("Ticker",       ticker)

                # Thesis
                thesis = result.get("thesis", "")
                if thesis:
                    st.info(f"**Portfolio Manager thesis:**\n\n{thesis}", icon="🔮")

                st.markdown("---")

                # ── 6-agent grid ──────────────────────────────────────────────
                st.subheader("Agent Breakdown")
                agents = result.get("agents", [])

                # 3 columns × 2 rows
                for row_start in range(0, min(len(agents), 6), 3):
                    cols = st.columns(3)
                    for i, col in enumerate(cols):
                        idx = row_start + i
                        if idx >= len(agents):
                            break
                        a = agents[idx]
                        name      = a.get("agent_name", "?")
                        signal    = a.get("signal",     "HOLD")
                        conf      = a.get("confidence", 0)
                        reasoning = a.get("reasoning",  "")
                        quality   = a.get("data_quality", "complete")
                        meta      = AGENT_META.get(name, {"label": name, "icon": "•"})

                        with col:
                            sig_col = SIGNAL_COLORS.get(signal, "#90a4ae")
                            st.markdown(
                                f"""<div style="border:1px solid {sig_col}; border-radius:8px;
                                    padding:12px; margin-bottom:8px;">
                                    <b>{meta['icon']} {meta['label']}</b><br/>
                                    <span style="color:{sig_col}; font-size:1.2em; font-weight:bold">
                                        {signal}
                                    </span>
                                    &nbsp; {QUALITY_ICONS.get(quality,'')}
                                </div>""",
                                unsafe_allow_html=True,
                            )
                            st.progress(conf / 100, text=f"Confidence: {conf}%")
                            with st.expander("Reasoning"):
                                st.markdown(reasoning or "_No reasoning available._")

                # ── Donut vote chart ──────────────────────────────────────────
                st.markdown("---")
                d1, d2 = st.columns([1, 2])
                with d1:
                    st.subheader("Vote Distribution")
                    fig = _donut_chart(agents)
                    st.plotly_chart(fig, use_container_width=True)
                with d2:
                    st.subheader("Agent Summary Table")
                    rows = [
                        {
                            "Agent":       AGENT_META.get(a["agent_name"], {}).get("label", a["agent_name"]),
                            "Signal":      a["signal"],
                            "Confidence":  a["confidence"],
                            "Data Quality":a["data_quality"],
                        }
                        for a in agents
                    ]
                    df_agents = pd.DataFrame(rows)

                    def _color_signal(val):
                        c = SIGNAL_COLORS.get(val, "#90a4ae")
                        return f"color: {c}; font-weight: bold"

                    st.dataframe(
                        df_agents.style.applymap(_color_signal, subset=["Signal"]),
                        use_container_width=True,
                        hide_index=True,
                    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Batch Consensus Table
# ══════════════════════════════════════════════════════════════════════════════
with tab_batch:
    st.subheader("Batch Agent Analysis — Top Signal Stocks")
    st.caption(
        "Runs the full 6-agent framework on today's top signals. "
        "Results cached 1 hour. Each ticker takes ~10–15 s."
    )

    b1, b2, b3 = st.columns([2, 2, 1])
    batch_market = b1.radio("Market", ["US", "TW"], horizontal=True, key="batch_market")
    batch_n      = b2.slider("Max tickers", 3, 20, 5)
    run_batch    = b3.button("▶ Run Batch", type="primary", use_container_width=True)

    if not run_batch:
        st.info("Click **Run Batch** to analyse the top signal stocks via all 6 agents.")
    else:
        import requests

        api_url  = "http://localhost:8000"
        endpoint = f"{api_url}/api/agents/batch?market={batch_market}&max_tickers={batch_n}"

        with st.spinner(f"Analysing top {batch_n} {batch_market} signals…"):
            try:
                resp = requests.get(endpoint, timeout=300)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                # Fallback: run directly (no API server running)
                st.warning(f"API call failed ({e}), running inline…")
                from ai.agents import analyze_ticker, _load_ticker_data, orchestrate_result_to_dict
                from dashboard.data_helpers import load_signals
                sigs = load_signals(batch_market)
                if sigs.empty:
                    st.error("No signals found. Run the pipeline first.")
                    st.stop()
                tickers = sigs.sort_values("score", ascending=False).head(batch_n)["ticker"].str.upper().tolist()
                results = []
                prog = st.progress(0)
                for i, t in enumerate(tickers):
                    metrics, fundamentals, headlines = _load_ticker_data(t, batch_market, str(BASE_DIR))
                    r = analyze_ticker(t, batch_market, metrics, fundamentals, headlines)
                    results.append(orchestrate_result_to_dict(r))
                    prog.progress((i + 1) / len(tickers), text=f"Analysed {t}")
                data = {"results": results, "market": batch_market, "count": len(results)}

        results = data.get("results", [])
        if not results:
            st.warning("No results returned.")
        else:
            # Build summary table
            rows = []
            for r in results:
                sig      = r.get("final_signal", "HOLD")
                buy_v    = sum(1 for a in r.get("agents", []) if a.get("signal") == "BUY")
                sell_v   = sum(1 for a in r.get("agents", []) if a.get("signal") == "SELL")
                hold_v   = sum(1 for a in r.get("agents", []) if a.get("signal") == "HOLD")
                rows.append({
                    "Ticker":       r.get("ticker", "?"),
                    "Market":       r.get("market", batch_market),
                    "Final Signal": sig,
                    "Conviction":   r.get("conviction", 0),
                    "BUY votes":    buy_v,
                    "HOLD votes":   hold_v,
                    "SELL votes":   sell_v,
                    "Consensus":    f"{r.get('consensus_score', 0)*100:.0f}%",
                    "Thesis (brief)": (r.get("thesis", "") or "")[:120] + "…",
                })

            df_batch = pd.DataFrame(rows).sort_values("Conviction", ascending=False)

            def _color_sig(val):
                c = SIGNAL_COLORS.get(val, "#90a4ae")
                return f"color: {c}; font-weight: bold"

            st.markdown(f"**{len(df_batch)} tickers analysed** — sorted by conviction")
            st.dataframe(
                df_batch.style.applymap(_color_sig, subset=["Final Signal"]),
                use_container_width=True,
                hide_index=True,
            )

            # Detail expanders
            st.markdown("---")
            st.subheader("Detailed Results")
            for r in sorted(results, key=lambda x: -x.get("conviction", 0)):
                sig  = r.get("final_signal", "HOLD")
                icon = SIGNAL_ICONS.get(sig, "⏸️")
                conv = r.get("conviction", 0)
                with st.expander(
                    f"{icon} **{r.get('ticker')}** — {sig} (conviction {conv}%)"
                ):
                    st.markdown(f"**Thesis:** {r.get('thesis', '_N/A_')}")
                    st.markdown("**Agent votes:**")
                    for a in r.get("agents", []):
                        meta = AGENT_META.get(a["agent_name"], {"label": a["agent_name"], "icon": "•"})
                        c    = SIGNAL_COLORS.get(a["signal"], "#90a4ae")
                        st.markdown(
                            f"- {meta['icon']} **{meta['label']}**: "
                            f"<span style='color:{c}'>{a['signal']}</span> "
                            f"({a['confidence']}%) — {a['reasoning']}",
                            unsafe_allow_html=True,
                        )
