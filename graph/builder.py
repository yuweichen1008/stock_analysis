"""
Knowledge Graph Builders.

Three graph types:

1. build_signal_graph(signals_df, max_nodes, min_similarity)
   Stocks as nodes; edges = cosine similarity on [RSI, bias, vol_ratio] > threshold.
   Reveals clusters of stocks with similar technical setups.

2. build_sector_graph(signals_df, mapping_df)
   Hierarchical DiGraph: MARKET → Sector → Industry → Stock.
   Shows where signals concentrate in the sector/industry tree.

3. build_agent_graph(agent_results_list)
   Bipartite: 6 agent philosophy nodes + N stock nodes.
   Edges: agent → stock where that agent said BUY.
   Reveals which philosophies agree on which stocks.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
import pandas as pd
import networkx as nx

logger = logging.getLogger(__name__)

SIGNAL_COLORS = {
    "BUY":     "#26a69a",
    "SELL":    "#ef5350",
    "HOLD":    "#90a4ae",
    "WATCH":   "#ffa726",
    "NEUTRAL": "#78909c",
}

AGENT_META = {
    "value":     {"label": "Value\n(Graham/Buffett)", "color": "#42a5f5"},
    "growth":    {"label": "Growth\n(Lynch/Wood)",    "color": "#66bb6a"},
    "technical": {"label": "Technical",               "color": "#ab47bc"},
    "sentiment": {"label": "Sentiment",               "color": "#ffa726"},
    "risk":      {"label": "Risk\n(Taleb)",           "color": "#ef5350"},
    "valuation": {"label": "Valuation\n(Damodaran)",  "color": "#26c6da"},
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _signal_from_row(row: pd.Series) -> str:
    """Derive a signal label from trending row."""
    if row.get("is_signal") in (True, 1, "True", "1"):
        score = _safe_float(row.get("score", 0))
        if score >= 6:
            return "BUY"
        return "WATCH"
    return "NEUTRAL"


def _color_for_signal(signal: str) -> str:
    return SIGNAL_COLORS.get(signal, SIGNAL_COLORS["NEUTRAL"])


# ── Graph 1: Signal Similarity ─────────────────────────────────────────────────

def build_signal_graph(
    signals_df:     pd.DataFrame,
    max_nodes:      int   = 50,
    min_similarity: float = 0.80,
) -> nx.Graph:
    """
    Build a graph where stocks are nodes and edges connect stocks with
    similar technical setups (cosine similarity on RSI, bias, vol_ratio).

    Parameters
    ----------
    signals_df     : merged TW+US signals DataFrame from load_all_signals()
    max_nodes      : cap at this many nodes (top by score, then by is_signal)
    min_similarity : minimum cosine similarity to draw an edge (0–1)
    """
    G = nx.Graph()
    G.graph["graph_type"] = "signal"

    if signals_df.empty:
        return G

    # Normalise cols
    df = signals_df.copy()
    for c in ["RSI", "bias", "vol_ratio", "score"]:
        df[c] = pd.to_numeric(df.get(c), errors="coerce").fillna(0)

    # Pick top N by score
    df = df.sort_values("score", ascending=False).head(max_nodes).reset_index(drop=True)

    # Add nodes
    for _, row in df.iterrows():
        ticker  = str(row.get("ticker", "?"))
        signal  = _signal_from_row(row)
        score   = _safe_float(row.get("score", 0))
        market  = str(row.get("market", "?"))
        sector  = str(row.get("industry", row.get("fv_sector", row.get("fv_sector_y", "Unknown"))))
        rsi     = _safe_float(row.get("RSI", 50))
        bias    = _safe_float(row.get("bias", 0))

        G.add_node(
            ticker,
            type       = "stock",
            label      = ticker,
            market     = market,
            signal     = signal,
            score      = round(score, 2),
            rsi        = round(rsi, 1),
            bias       = round(bias, 2),
            vol_ratio  = round(_safe_float(row.get("vol_ratio", 1)), 2),
            sector     = sector,
            title      = (
                f"<b>{ticker}</b> [{market}]<br/>"
                f"Signal: {signal}  Score: {score:.1f}<br/>"
                f"RSI: {rsi:.1f}  Bias: {bias:.1f}%<br/>"
                f"Sector: {sector}"
            ),
            size       = max(10, int(score * 4) + 10),
            color      = _color_for_signal(signal),
            font       = {"color": "white"},
        )

    # Compute pairwise cosine similarity on [RSI_norm, bias_norm, vol_ratio_norm]
    tickers = list(G.nodes())
    feature_cols = ["RSI", "bias", "vol_ratio"]
    feat_df = df.set_index("ticker")[feature_cols].reindex(tickers).fillna(0)

    # Normalise each feature to 0–1 range
    normed = feat_df.copy()
    for c in feature_cols:
        col_range = normed[c].max() - normed[c].min()
        if col_range > 0:
            normed[c] = (normed[c] - normed[c].min()) / col_range
        else:
            normed[c] = 0.5

    vectors = normed.values  # shape: (N, 3)

    # Cosine similarity
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    unit_vecs = vectors / norms
    sim_matrix = unit_vecs @ unit_vecs.T  # (N, N)

    # Add edges above threshold
    n = len(tickers)
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(sim_matrix[i, j])
            if sim >= min_similarity:
                G.add_edge(
                    tickers[i], tickers[j],
                    weight = round(sim, 3),
                    title  = f"Similarity: {sim:.3f}",
                    width  = max(1, int((sim - min_similarity) * 10)),
                )

    logger.info(
        "Signal graph: %d nodes, %d edges (min_sim=%.2f)",
        G.number_of_nodes(), G.number_of_edges(), min_similarity
    )
    return G


# ── Graph 2: Sector Hierarchy ─────────────────────────────────────────────────

def build_sector_graph(
    signals_df:  pd.DataFrame,
    mapping_df:  Optional[pd.DataFrame] = None,
    min_score:   float = 0.0,
) -> nx.DiGraph:
    """
    Build a hierarchical DiGraph: MARKET → Sector → Industry → Stock.
    Only includes stocks that have a signal or score > min_score.

    Parameters
    ----------
    signals_df : merged TW+US signals DataFrame
    mapping_df : optional company_mapping DataFrame for additional metadata
    min_score  : only include stocks with score >= this value
    """
    G = nx.DiGraph()
    G.graph["graph_type"] = "sector"

    if signals_df.empty:
        return G

    df = signals_df.copy()
    df["score"] = pd.to_numeric(df.get("score"), errors="coerce").fillna(0)

    # Filter
    df = df[
        (df.get("is_signal", False).isin([True, 1, "True", "1"])) |
        (df["score"] >= min_score)
    ].copy()

    if df.empty:
        return G

    # Enrich with mapping if provided
    if mapping_df is not None and not mapping_df.empty:
        merge_cols = [c for c in ["ticker", "industry", "name"] if c in mapping_df.columns]
        if "ticker" in merge_cols and "industry" in merge_cols:
            df = df.merge(
                mapping_df[merge_cols].rename(columns={"industry": "industry_map"}),
                on="ticker", how="left"
            )
            df["industry"] = df["industry"].fillna(df.get("industry_map", "Unknown"))

    # Root node
    G.add_node(
        "ALL_MARKETS",
        type   = "root",
        label  = "All Markets",
        title  = "All Markets — click to explore",
        size   = 45,
        color  = "#ffffff",
        font   = {"color": "black", "size": 16},
    )

    seen_sectors   = set()
    seen_industries = set()

    for _, row in df.iterrows():
        ticker   = str(row.get("ticker", "?"))
        market   = str(row.get("market", "?"))
        # Industry column varies by source
        industry = str(
            row.get("industry") or
            row.get("fv_industry") or
            row.get("fv_sector_y") or
            row.get("fv_sector_x") or
            "Unknown"
        )
        if industry in ("nan", "None", ""):
            industry = "Unknown"

        # Use market as sector level
        sector   = market
        sector_id = f"SECTOR_{market}"

        # Add market node
        if sector_id not in seen_sectors:
            G.add_node(
                sector_id,
                type   = "market",
                label  = market,
                title  = f"Market: {market}",
                size   = 30,
                color  = "#42a5f5" if market == "US" else "#ef5350",
                font   = {"color": "white"},
            )
            G.add_edge("ALL_MARKETS", sector_id)
            seen_sectors.add(sector_id)

        # Industry node
        industry_id = f"{market}_{industry}"
        if industry_id not in seen_industries:
            G.add_node(
                industry_id,
                type   = "industry",
                label  = industry[:25],   # truncate long names
                title  = f"Industry: {industry}\nMarket: {market}",
                size   = 20,
                color  = "#ffa726",
                font   = {"color": "white"},
            )
            G.add_edge(sector_id, industry_id)
            seen_industries.add(industry_id)

        # Stock node
        signal = _signal_from_row(row)
        score  = _safe_float(row.get("score", 0))
        rsi    = _safe_float(row.get("RSI", 50))

        if ticker not in G:
            G.add_node(
                ticker,
                type   = "stock",
                label  = ticker,
                market = market,
                signal = signal,
                score  = round(score, 2),
                rsi    = round(rsi, 1),
                title  = (
                    f"<b>{ticker}</b> [{market}]<br/>"
                    f"Signal: {signal}  Score: {score:.1f}<br/>"
                    f"RSI: {rsi:.1f}<br/>"
                    f"Industry: {industry}"
                ),
                size   = max(8, int(score * 3) + 8),
                color  = _color_for_signal(signal),
                font   = {"color": "white"},
            )
        G.add_edge(industry_id, ticker)

    logger.info(
        "Sector graph: %d nodes, %d edges",
        G.number_of_nodes(), G.number_of_edges()
    )
    return G


# ── Graph 3: Agent Consensus ───────────────────────────────────────────────────

def build_agent_graph(
    agent_results: List[dict],
    show_hold:     bool = False,
) -> nx.DiGraph:
    """
    Build a bipartite DiGraph: 6 agent nodes + N stock nodes.
    Directed edges: agent → stock where that agent says BUY (or HOLD if show_hold=True).

    Parameters
    ----------
    agent_results : list of OrchestratorResult dicts (from orchestrate_result_to_dict)
    show_hold     : also draw edges for HOLD signals (smaller weight)
    """
    G = nx.DiGraph()
    G.graph["graph_type"] = "agent"

    # Add 6 agent nodes (always — even if no stock results yet)
    for agent_name, meta in AGENT_META.items():
        G.add_node(
            f"AGENT_{agent_name}",
            type   = "agent",
            label  = meta["label"],
            title  = f"Agent: {meta['label']}",
            size   = 38,
            color  = meta["color"],
            font   = {"color": "white", "size": 14},
            shape  = "diamond",
        )

    # Add stock nodes + agent edges
    for result in agent_results:
        ticker       = result.get("ticker", "?")
        market       = result.get("market", "?")
        final_signal = result.get("final_signal", "HOLD")
        conviction   = int(result.get("conviction", 0))
        thesis       = (result.get("thesis") or "")[:120]

        if ticker not in G:
            G.add_node(
                ticker,
                type       = "stock",
                label      = ticker,
                market     = market,
                signal     = final_signal,
                conviction = conviction,
                title      = (
                    f"<b>{ticker}</b> [{market}]<br/>"
                    f"Final: {final_signal}  Conviction: {conviction}%<br/>"
                    f"{thesis}…"
                ),
                size       = max(12, conviction // 5 + 12),
                color      = _color_for_signal(final_signal),
                font       = {"color": "white"},
            )

        # Draw edges from agents to this stock
        for agent_result in result.get("agents", []):
            agent_name = agent_result.get("agent_name", "?")
            signal     = agent_result.get("signal", "HOLD")
            confidence = int(agent_result.get("confidence", 0))
            reasoning  = (agent_result.get("reasoning") or "")[:80]

            agent_node = f"AGENT_{agent_name}"
            if agent_node not in G:
                continue  # unknown agent name

            if signal == "BUY" or (show_hold and signal == "HOLD"):
                weight = confidence / 100 if signal == "BUY" else confidence / 200
                G.add_edge(
                    agent_node, ticker,
                    weight    = round(weight, 3),
                    signal    = signal,
                    confidence= confidence,
                    title     = (
                        f"{agent_name} → {ticker}<br/>"
                        f"{signal}  {confidence}%<br/>{reasoning}"
                    ),
                    width     = max(1, confidence // 20),
                    color     = _color_for_signal(signal),
                )

    logger.info(
        "Agent graph: %d nodes, %d edges",
        G.number_of_nodes(), G.number_of_edges()
    )
    return G


# ── Graph stats helper ────────────────────────────────────────────────────────

def graph_stats(G: nx.Graph) -> dict:
    """Return basic stats about a graph for display."""
    if G.number_of_nodes() == 0:
        return {"nodes": 0, "edges": 0, "components": 0, "density": 0.0}

    if G.is_directed():
        ug = G.to_undirected()
    else:
        ug = G

    try:
        components = nx.number_connected_components(ug)
    except Exception:
        components = 0

    density = nx.density(G)
    return {
        "nodes":      G.number_of_nodes(),
        "edges":      G.number_of_edges(),
        "components": components,
        "density":    round(density, 4),
    }
