"""
Knowledge Graph API endpoints.

GET /api/graph/signals?market=all&min_similarity=0.80&max_nodes=50
    Signal similarity graph as node-link JSON.

GET /api/graph/sectors?market=all&min_score=0
    Hierarchical sector/industry/stock tree as node-link JSON.

GET /api/graph/agents?market=US&show_hold=false
    Agent consensus bipartite graph as node-link JSON.
    Requires the agents cache (/api/agents/batch) to be warm.

All endpoints also accept ?format=html to return a self-contained
pyvis HTML page instead of JSON.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

router = APIRouter(prefix="/api/graph", tags=["graph"])

_graph_cache: dict = {}
_GRAPH_CACHE_TTL = 15 * 60  # 15 minutes


def _is_fresh(key: str) -> bool:
    return key in _graph_cache and (time.time() - _graph_cache[key]["ts"]) < _GRAPH_CACHE_TTL


def _graph_to_dict(G) -> dict:
    """Convert NetworkX graph to node-link JSON dict."""
    import networkx as nx
    node_link = nx.node_link_data(G)
    # Ensure all values are JSON-serialisable
    for node in node_link.get("nodes", []):
        for k, v in list(node.items()):
            if not isinstance(v, (str, int, float, bool, list, dict, type(None))):
                node[k] = str(v)
    return {
        "nodes":        [{"id": str(n["id"]), **{k: v for k, v in n.items() if k != "id"}}
                         for n in node_link.get("nodes", [])],
        "edges":        [{"source": str(e["source"]), "target": str(e["target"]),
                          **{k: v for k, v in e.items() if k not in ("source", "target")}}
                         for e in node_link.get("links", [])],
        "graph_type":   G.graph.get("graph_type", "unknown"),
        "node_count":   G.number_of_nodes(),
        "edge_count":   G.number_of_edges(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_signals(market: str):
    """Load and optionally filter signals DataFrame."""
    import pandas as pd
    dfs = []
    if market in ("TW", "all"):
        p = BASE_DIR / "current_trending.csv"
        if p.exists():
            df = pd.read_csv(p, dtype={"ticker": str})
            df["market"] = "TW"
            dfs.append(df)
    if market in ("US", "all"):
        p = BASE_DIR / "data_us" / "current_trending.csv"
        if p.exists():
            df = pd.read_csv(p, dtype={"ticker": str})
            df["market"] = "US"
            # Normalise _x/_y column duplicates from finviz merge
            col_map = {}
            for c in df.columns:
                base = c.rstrip("_xy").rstrip("_")
                if (c.endswith("_y") or c.endswith("_x")) and base not in col_map:
                    col_map[c] = base
            df = df.rename(columns=col_map).loc[:, ~df.rename(columns=col_map).columns.duplicated()]
            dfs.append(df)
    if not dfs:
        import pandas as pd
        return pd.DataFrame()
    import pandas as pd
    return pd.concat(dfs, ignore_index=True)


def _load_mapping(market: str):
    """Load company_mapping for enrichment."""
    import pandas as pd
    dfs = []
    if market in ("TW", "all"):
        p = BASE_DIR / "data" / "company" / "company_mapping.csv"
        if p.exists():
            df = pd.read_csv(p, dtype={"ticker": str}, encoding="utf-8-sig")
            df["market"] = "TW"
            dfs.append(df)
    if market in ("US", "all"):
        p = BASE_DIR / "data_us" / "company_mapping.csv"
        if p.exists():
            df = pd.read_csv(p, dtype={"ticker": str})
            df["market"] = "US"
            dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    import pandas as pd
    return pd.concat(dfs, ignore_index=True)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/signals")
def get_signal_graph(
    market:         str   = "all",
    min_similarity: float = 0.80,
    max_nodes:      int   = 50,
    format:         str   = "json",
):
    """Signal similarity graph — stocks clustered by similar technical setup."""
    market = market.upper()
    key = f"signal_{market}_{min_similarity}_{max_nodes}"
    if _is_fresh(key):
        cached = _graph_cache[key]["result"]
        if format == "html":
            return HTMLResponse(content=_graph_cache[key].get("html", ""))
        return cached

    signals_df = _load_signals(market)
    if signals_df.empty:
        raise HTTPException(status_code=404, detail="No signal data found. Run the pipeline first.")

    from graph.builder import build_signal_graph, graph_stats
    from graph.export  import to_pyvis_html

    G    = build_signal_graph(signals_df, max_nodes=max_nodes, min_similarity=min_similarity)
    data = _graph_to_dict(G)
    data["stats"] = graph_stats(G)
    html = to_pyvis_html(G)

    _graph_cache[key] = {"result": data, "html": html, "ts": time.time()}

    if format == "html":
        return HTMLResponse(content=html)
    return data


@router.get("/sectors")
def get_sector_graph(
    market:    str   = "all",
    min_score: float = 0.0,
    format:    str   = "json",
):
    """Hierarchical sector / industry / stock tree."""
    market = market.upper()
    key = f"sector_{market}_{min_score}"
    if _is_fresh(key):
        if format == "html":
            return HTMLResponse(content=_graph_cache[key].get("html", ""))
        return _graph_cache[key]["result"]

    signals_df = _load_signals(market)
    mapping_df = _load_mapping(market)

    if signals_df.empty:
        raise HTTPException(status_code=404, detail="No signal data found.")

    from graph.builder import build_sector_graph, graph_stats
    from graph.export  import to_pyvis_html

    G    = build_sector_graph(signals_df, mapping_df if not mapping_df.empty else None, min_score=min_score)
    data = _graph_to_dict(G)
    data["stats"] = graph_stats(G)
    html = to_pyvis_html(G, layout="hierarchical")

    _graph_cache[key] = {"result": data, "html": html, "ts": time.time()}

    if format == "html":
        return HTMLResponse(content=html)
    return data


@router.get("/agents")
def get_agent_graph(
    market:    str  = "US",
    show_hold: bool = False,
    format:    str  = "json",
):
    """
    Agent consensus bipartite graph.
    Requires /api/agents/batch to have been called first (warms the agent cache).
    Falls back to an empty agent graph with stock-only nodes if cache is cold.
    """
    market = market.upper()
    key = f"agent_{market}_{show_hold}"
    if _is_fresh(key):
        if format == "html":
            return HTMLResponse(content=_graph_cache[key].get("html", ""))
        return _graph_cache[key]["result"]

    # Pull from agent cache
    try:
        from api.routers.agents import _agent_cache as _ac
        agent_results = [
            v["result"]
            for k, v in _ac.items()
            if k.endswith(f"_{market}")
        ]
    except Exception:
        agent_results = []

    from graph.builder import build_agent_graph, graph_stats
    from graph.export  import to_pyvis_html

    G    = build_agent_graph(agent_results, show_hold=show_hold)
    data = _graph_to_dict(G)
    data["stats"]       = graph_stats(G)
    data["cache_warm"]  = len(agent_results) > 0
    html = to_pyvis_html(G, layout="force_atlas_2based")

    _graph_cache[key] = {"result": data, "html": html, "ts": time.time()}

    if format == "html":
        return HTMLResponse(content=html)
    return data


@router.delete("/cache")
def clear_graph_cache():
    """Clear all cached graph data."""
    _graph_cache.clear()
    return {"cleared": True}
