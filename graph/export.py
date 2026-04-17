"""
Graph export to pyvis interactive HTML.

Usage:
    from graph.builder import build_signal_graph
    from graph.export import to_pyvis_html

    G   = build_signal_graph(signals_df)
    html = to_pyvis_html(G)
    # Embed in Streamlit: st.components.v1.html(html, height=720)
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import networkx as nx

logger = logging.getLogger(__name__)


def to_pyvis_html(
    G:           nx.Graph,
    height:      str  = "700px",
    width:       str  = "100%",
    bgcolor:     str  = "#0d1117",
    font_color:  str  = "white",
    layout:      str  = "barnes_hut",   # "barnes_hut" | "hierarchical" | "force_atlas_2based"
    filter_menu: bool = False,
    buttons:     bool = False,
) -> str:
    """
    Convert a NetworkX graph to a self-contained pyvis interactive HTML string.

    Parameters
    ----------
    G           : NetworkX Graph or DiGraph
    height      : CSS height of the canvas (e.g. "700px")
    width       : CSS width (default "100%")
    bgcolor     : canvas background colour
    font_color  : default font colour for nodes/labels
    layout      : physics layout engine
    filter_menu : show pyvis built-in node/edge filter panel (adds side panel)
    buttons     : show pyvis physics control buttons

    Returns
    -------
    Self-contained HTML string suitable for st.components.v1.html()
    """
    from pyvis.network import Network

    directed = G.is_directed()
    net = Network(
        height      = height,
        width       = width,
        bgcolor     = bgcolor,
        font_color  = font_color,
        directed    = directed,
        filter_menu = filter_menu,
        select_menu = False,
    )

    # ── Physics options ───────────────────────────────────────────────────────
    graph_type = G.graph.get("graph_type", "signal")

    if layout == "hierarchical" or graph_type == "sector":
        options = {
            "layout": {
                "hierarchical": {
                    "enabled":           True,
                    "direction":         "UD",    # Up-Down tree
                    "sortMethod":        "directed",
                    "levelSeparation":   120,
                    "nodeSpacing":       100,
                    "treeSpacing":       150,
                    "blockShifting":     True,
                    "edgeMinimization":  True,
                    "parentCentralization": True,
                }
            },
            "physics": {"enabled": False},
            "edges":   {"smooth": {"type": "cubicBezier"}},
        }
    elif layout == "force_atlas_2based":
        options = {
            "physics": {
                "forceAtlas2Based": {
                    "gravitationalConstant": -50,
                    "centralGravity":        0.01,
                    "springLength":          100,
                    "springConstant":        0.08,
                    "avoidOverlap":          0.5,
                },
                "solver":               "forceAtlas2Based",
                "stabilization":        {"iterations": 200},
            }
        }
    else:
        # Barnes-Hut (default, fast for medium graphs)
        options = {
            "physics": {
                "barnesHut": {
                    "gravitationalConstant": -8000,
                    "centralGravity":        0.3,
                    "springLength":          150,
                    "springConstant":        0.04,
                    "damping":               0.09,
                    "avoidOverlap":          0.8,
                },
                "solver":        "barnesHut",
                "stabilization": {"iterations": 200, "updateInterval": 25},
            }
        }

    # Common visual options
    options.update({
        "interaction": {
            "hover":         True,
            "tooltipDelay":  100,
            "navigationButtons": False,
            "keyboard":      False,
        },
        "nodes": {
            "shape":   "dot",
            "font":    {"color": font_color, "size": 12},
            "scaling": {"min": 8, "max": 45},
        },
        "edges": {
            "color":  {"inherit": False},
            "width":  1,
            "arrows": {"to": {"enabled": directed, "scaleFactor": 0.5}},
            "smooth": {"enabled": True, "type": "dynamic"},
        },
    })

    net.set_options(json.dumps(options))

    # ── Transfer nodes + edges from NetworkX ─────────────────────────────────
    for node_id, attrs in G.nodes(data=True):
        node_kwargs = {
            "label": str(attrs.get("label", node_id)),
            "size":  int(attrs.get("size", 15)),
            "color": str(attrs.get("color", "#90a4ae")),
            "title": str(attrs.get("title", node_id)),
        }
        # Pass shape if set
        if "shape" in attrs:
            node_kwargs["shape"] = attrs["shape"]
        # Font override
        if "font" in attrs and isinstance(attrs["font"], dict):
            node_kwargs["font"] = attrs["font"]

        net.add_node(str(node_id), **node_kwargs)

    for src, dst, attrs in G.edges(data=True):
        edge_kwargs = {
            "weight": float(attrs.get("weight", 1.0)),
            "title":  str(attrs.get("title", "")),
            "width":  int(attrs.get("width", 1)),
        }
        if "color" in attrs:
            edge_kwargs["color"] = attrs["color"]

        net.add_edge(str(src), str(dst), **edge_kwargs)

    # ── Generate HTML ─────────────────────────────────────────────────────────
    try:
        # pyvis >= 0.3.0 supports generate_html() directly
        html = net.generate_html(local=True)
        return html
    except AttributeError:
        # Fallback for older pyvis: write to temp file then read back
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            tmp_path = f.name
        try:
            net.save_graph(tmp_path)
            return Path(tmp_path).read_text(encoding="utf-8")
        finally:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
