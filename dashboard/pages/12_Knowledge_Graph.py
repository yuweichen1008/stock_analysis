"""
Financial Knowledge Graph — interactive network visualization of stocks,
sectors, and multi-agent consensus.

Three graph views:
  Signal Similarity   — stocks clustered by similar RSI/bias/volume setup
  Sector Hierarchy    — tree: All Markets → Sector → Industry → Stock
  Agent Consensus     — bipartite: 6 agent philosophy nodes → stocks they recommend
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from dashboard.data_helpers import BASE_DIR

st.set_page_config(page_title="Knowledge Graph", page_icon="🕸️", layout="wide")

# ── Env ───────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

# ── Imports ───────────────────────────────────────────────────────────────────
from ai.unified_signals import load_all_signals


@st.cache_data(ttl=300, show_spinner=False)
def _load_all():
    return load_all_signals(str(BASE_DIR))


@st.cache_data(ttl=900, show_spinner="Building graph…")
def _build_signal_html(market: str, min_sim: float, max_nodes: int) -> tuple[str, dict]:
    from graph.builder import build_signal_graph, graph_stats
    from graph.export  import to_pyvis_html
    import pandas as pd

    df = _load_all()
    if market != "All":
        df = df[df["market"] == market]

    G    = build_signal_graph(df, max_nodes=max_nodes, min_similarity=min_sim)
    html = to_pyvis_html(G)
    return html, graph_stats(G)


@st.cache_data(ttl=900, show_spinner="Building sector tree…")
def _build_sector_html(market: str, min_score: float) -> tuple[str, dict]:
    from graph.builder import build_sector_graph, graph_stats
    from graph.export  import to_pyvis_html
    import pandas as pd

    df = _load_all()
    if market != "All":
        df = df[df["market"] == market]

    # Load mapping for richer industry labels
    mapping_dfs = []
    tw_map = BASE_DIR / "data" / "company" / "company_mapping.csv"
    us_map = BASE_DIR / "data_us" / "company_mapping.csv"
    if tw_map.exists():
        m = pd.read_csv(tw_map, dtype={"ticker": str}, encoding="utf-8-sig")
        m["market"] = "TW"
        mapping_dfs.append(m)
    if us_map.exists():
        m = pd.read_csv(us_map, dtype={"ticker": str})
        m["market"] = "US"
        mapping_dfs.append(m)
    mapping_df = pd.concat(mapping_dfs, ignore_index=True) if mapping_dfs else pd.DataFrame()

    G    = build_sector_graph(df, mapping_df if not mapping_df.empty else None, min_score=min_score)
    html = to_pyvis_html(G, layout="hierarchical")
    return html, graph_stats(G)


@st.cache_data(ttl=900, show_spinner="Building agent graph…")
def _build_agent_html(market: str, show_hold: bool) -> tuple[str, dict]:
    from graph.builder import build_agent_graph, graph_stats
    from graph.export  import to_pyvis_html

    # Try to pull from agents API cache
    try:
        from api.routers.agents import _agent_cache as _ac
        agent_results = [
            v["result"]
            for k, v in _ac.items()
            if market == "All" or k.endswith(f"_{market}")
        ]
    except Exception:
        agent_results = []

    G    = build_agent_graph(agent_results, show_hold=show_hold)
    html = to_pyvis_html(G, layout="force_atlas_2based")
    return html, graph_stats(G)


# ══════════════════════════════════════════════════════════════════════════════
# Page layout
# ══════════════════════════════════════════════════════════════════════════════
st.title("🕸️ Financial Knowledge Graph")
st.caption(
    "Interactive network visualization — explore relationships between stocks, "
    "sectors, and investment agent philosophies"
)

st.divider()

# ── Controls ──────────────────────────────────────────────────────────────────
ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([3, 2, 2, 1])

graph_type = ctrl_col1.selectbox(
    "Graph View",
    ["Signal Similarity", "Sector Hierarchy", "Agent Consensus"],
    help=(
        "**Signal Similarity** — stocks with similar RSI/bias/vol setups cluster together. "
        "**Sector Hierarchy** — tree: Market → Industry → Stock. "
        "**Agent Consensus** — which investment agents recommend which stocks."
    ),
)

market_filter = ctrl_col2.radio("Market", ["All", "US", "TW"], horizontal=True)

refresh_btn = ctrl_col4.button("🔄 Rebuild", use_container_width=True)
if refresh_btn:
    st.cache_data.clear()
    st.rerun()

# ── Graph-specific options ────────────────────────────────────────────────────
html    = ""
stats   = {"nodes": 0, "edges": 0, "components": 0, "density": 0.0}
warning = ""

if graph_type == "Signal Similarity":
    with ctrl_col3:
        min_sim = st.slider("Min similarity", 0.70, 0.99, 0.80, 0.01,
                            help="Higher = fewer but stronger edges between stocks")

    max_nodes = st.sidebar.slider("Max stocks shown", 10, 100, 50, 5)

    if _load_all().empty:
        warning = "No signal data found. Run `python master_run.py` first."
    else:
        html, stats = _build_signal_html(market_filter, min_sim, max_nodes)

    with st.sidebar:
        st.markdown("### Signal Similarity Legend")
        st.markdown(
            "- 🟢 **Teal** = BUY signal (score ≥ 6)\n"
            "- 🟡 **Orange** = WATCH (is_signal, lower score)\n"
            "- ⚫ **Gray** = Neutral\n"
            "- **Node size** = score × 4\n"
            "- **Edge thickness** = similarity strength\n"
            "- **Clusters** = stocks with similar technical setup"
        )

elif graph_type == "Sector Hierarchy":
    with ctrl_col3:
        min_score_opt = st.slider("Min score filter", 0.0, 8.0, 0.0, 0.5,
                                  help="Only show stocks with score above this threshold")

    if _load_all().empty:
        warning = "No signal data found. Run `python master_run.py` first."
    else:
        html, stats = _build_sector_html(market_filter, min_score_opt)

    with st.sidebar:
        st.markdown("### Sector Hierarchy Legend")
        st.markdown(
            "- ⬜ **White** = Market root (All)\n"
            "- 🔵 **Blue** = US market\n"
            "- 🔴 **Red** = TW market\n"
            "- 🟡 **Orange** = Industry nodes\n"
            "- 🟢 **Teal** = BUY signal stocks\n"
            "- **Node size** = signal score"
        )

else:  # Agent Consensus
    with ctrl_col3:
        show_hold_opt = st.checkbox("Show HOLD edges", value=False,
                                    help="Also draw edges for agents that say HOLD (lighter weight)")

    html, stats = _build_agent_html(market_filter, show_hold_opt)

    if stats["edges"] == 0:
        warning = (
            "No agent results found. "
            "Go to **Agent Consensus** page and run batch analysis first, "
            "then return here to see the agent-stock relationship graph."
        )

    with st.sidebar:
        st.markdown("### Agent Consensus Legend")
        st.markdown(
            "- 💎 **Diamond nodes** = Investment agents (6 philosophies)\n"
            "- ● **Circle nodes** = Stocks (sized by conviction)\n"
            "- **Edge** = agent says BUY for that stock\n"
            "- **Edge thickness** = confidence level\n\n"
            "**Agent colors:**\n"
            "- 🔵 Value (Graham/Buffett)\n"
            "- 🟢 Growth (Lynch/Wood)\n"
            "- 🟣 Technical\n"
            "- 🟡 Sentiment\n"
            "- 🔴 Risk (Taleb)\n"
            "- 🩵 Valuation (Damodaran)"
        )

# ── Warning banner ────────────────────────────────────────────────────────────
if warning:
    st.warning(warning, icon="⚠️")

# ── Graph canvas ──────────────────────────────────────────────────────────────
if html:
    components.html(html, height=720, scrolling=False)
else:
    st.info("Graph will appear here once data is available.", icon="🕸️")

# ── Stats row ─────────────────────────────────────────────────────────────────
st.divider()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Nodes",      stats.get("nodes",      0))
m2.metric("Edges",      stats.get("edges",      0))
m3.metric("Clusters",   stats.get("components", 0))
m4.metric("Density",    f"{stats.get('density', 0.0):.4f}")

# ── How-to guide ─────────────────────────────────────────────────────────────
with st.expander("How to read this graph"):
    if graph_type == "Signal Similarity":
        st.markdown("""
**Signal Similarity Graph**

Each node is a stock. Edges connect stocks that have similar technical setups
(measured by cosine similarity of RSI, bias%, and volume ratio).

- **Clusters** reveal groups of stocks that are in the same technical "zone"
  (e.g. all deeply oversold, or all in mild pullback with low volume)
- **Isolated nodes** are stocks with unique technical profiles
- **Teal nodes** (score ≥ 6) are active buy signals — check if they cluster
  with other teal nodes for confirmation

**Interaction tips:**
- Hover a node to see RSI, bias, and sector
- Drag nodes to rearrange
- Scroll to zoom in/out
- Double-click a node to highlight its neighbours
""")
    elif graph_type == "Sector Hierarchy":
        st.markdown("""
**Sector Hierarchy Graph**

A top-down tree showing which sectors and industries contain today's signal stocks.

- **Root** (white, top) → **Market** (blue=US, red=TW) → **Industry** (orange) → **Stock** (colored by signal)
- Wider branches = more signal stocks in that industry
- Use this to spot sector concentration in today's signals

**Interaction tips:**
- Click any node to see details
- Drag to rearrange sub-trees
- The layout is hierarchical top-down by default
""")
    else:
        st.markdown("""
**Agent Consensus Graph**

A bipartite network showing which investment agents recommend which stocks.

- **Diamond nodes** (large, colored) = 6 investment philosophy agents
- **Circle nodes** = stocks analysed by the batch analysis
- **Edges** = that agent says BUY for that stock (thickness = confidence)

Stocks connected to many agents have **broad consensus** — multiple philosophies agree.
Stocks connected to only 1-2 agents have a **narrow thesis** — worth investigating why
the other agents disagree.

Run **Agent Consensus → Batch Analysis** first to populate this graph.
""")
