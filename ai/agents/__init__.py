"""
Multi-Agent Investment Framework — public API.

Usage:
    from ai.agents import analyze_ticker, _load_ticker_data

    metrics, fundamentals, headlines = _load_ticker_data("AAPL", "US", base_dir)
    result = analyze_ticker("AAPL", "US", metrics, fundamentals, headlines)
    # result is an OrchestratorResult
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from ai.agents.base import AgentResult, OrchestratorResult
from ai.agents.value_agent     import run_value_agent
from ai.agents.growth_agent    import run_growth_agent
from ai.agents.technical_agent import run_technical_agent
from ai.agents.sentiment_agent import run_sentiment_agent
from ai.agents.risk_agent      import run_risk_agent
from ai.agents.valuation_agent import run_valuation_agent
from ai.agents.orchestrator    import run_orchestrator

logger = logging.getLogger(__name__)

__all__ = ["analyze_ticker", "_load_ticker_data", "AgentResult", "OrchestratorResult"]


# ── Data Loader ───────────────────────────────────────────────────────────────

def _load_ticker_data(
    ticker:   str,
    market:   str,
    base_dir: str,
) -> Tuple[dict, dict, List[str]]:
    """
    Assemble metrics, fundamentals, and headlines for a single ticker.

    Returns
    -------
    (metrics, fundamentals, headlines)
      metrics      — dict from current_trending.csv row
      fundamentals — dict from company_mapping.csv row (may have N/A values)
      headlines    — list of recent news headline strings (up to 8)
    """
    base = Path(base_dir)

    # ── 1. metrics from current_trending.csv ─────────────────────────────────
    metrics: dict = {}
    try:
        if market == "TW":
            trending_path = base / "current_trending.csv"
        else:
            trending_path = base / "data_us" / "current_trending.csv"

        if trending_path.exists():
            df = pd.read_csv(trending_path, dtype={"ticker": str})
            # Normalise column suffixes from Finviz merge (_x/_y duplicates)
            col_map = {}
            for c in df.columns:
                base_col = c.rstrip("_xy").rstrip("_")
                if c.endswith("_y") and base_col not in col_map:
                    col_map[c] = base_col
                elif c.endswith("_x") and base_col not in col_map:
                    col_map[c] = base_col
            df = df.rename(columns=col_map)
            # Drop duplicate columns after rename
            df = df.loc[:, ~df.columns.duplicated()]

            row = df[df["ticker"].str.upper() == ticker.upper()]
            if not row.empty:
                metrics = row.iloc[0].to_dict()
    except Exception as e:
        logger.warning("_load_ticker_data metrics(%s): %s", ticker, e)

    # ── 2. fundamentals from company_mapping.csv ──────────────────────────────
    fundamentals: dict = {}
    try:
        if market == "TW":
            mapping_path = base / "data" / "company" / "company_mapping.csv"
        else:
            mapping_path = base / "data_us" / "company_mapping.csv"

        if mapping_path.exists():
            mdf = pd.read_csv(mapping_path, dtype={"ticker": str}, encoding="utf-8-sig")
            row = mdf[mdf["ticker"].str.upper() == ticker.upper()]
            if not row.empty:
                fundamentals = row.iloc[0].to_dict()
    except Exception as e:
        logger.warning("_load_ticker_data fundamentals(%s): %s", ticker, e)

    # ── 3. Headlines from Google News ────────────────────────────────────────
    headlines: List[str] = []
    try:
        from tws.utils import fetch_google_news_many
        name = str(fundamentals.get("name", "")) if fundamentals else ""
        headlines = fetch_google_news_many(ticker, name, days=7, max_items=8)
    except Exception as e:
        logger.debug("_load_ticker_data headlines(%s): %s", ticker, e)

    return metrics, fundamentals, headlines


# ── Main Entry Point ──────────────────────────────────────────────────────────

def analyze_ticker(
    ticker:       str,
    market:       str,
    metrics:      dict,
    fundamentals: dict,
    headlines:    Optional[List[str]] = None,
) -> OrchestratorResult:
    """
    Run all 6 specialist agents then the Portfolio Manager orchestrator.

    This makes 7 Claude API calls total (6× Haiku + 1× Sonnet).
    Expected runtime: ~10–15 seconds.

    Parameters
    ----------
    ticker       : stock symbol (e.g. "AAPL", "2330")
    market       : "TW" or "US"
    metrics      : dict from current_trending.csv row
    fundamentals : dict from company_mapping.csv row
    headlines    : list of recent news headline strings

    Returns
    -------
    OrchestratorResult with final_signal, conviction, thesis, and agent_results
    """
    headlines = headlines or []
    agent_results: List[AgentResult] = []

    agents = [
        ("value",      lambda: run_value_agent(ticker, market, fundamentals, metrics)),
        ("growth",     lambda: run_growth_agent(ticker, market, fundamentals, metrics)),
        ("technical",  lambda: run_technical_agent(ticker, market, metrics)),
        ("sentiment",  lambda: run_sentiment_agent(ticker, market, metrics, headlines)),
        ("risk",       lambda: run_risk_agent(ticker, market, metrics, fundamentals)),
        ("valuation",  lambda: run_valuation_agent(ticker, market, fundamentals, metrics)),
    ]

    for name, fn in agents:
        logger.info("Running %s agent for %s (%s)", name, ticker, market)
        try:
            result = fn()
        except Exception as e:
            logger.warning("Agent %s crashed for %s: %s", name, ticker, e)
            result = AgentResult(
                agent_name   = name,
                signal       = "HOLD",
                confidence   = 0,
                reasoning    = f"Agent error: {e}",
                data_quality = "sparse",
            )
        agent_results.append(result)
        # Brief pause to avoid overwhelming the API
        time.sleep(0.15)

    logger.info("Running orchestrator for %s (%s)", ticker, market)
    return run_orchestrator(ticker, market, agent_results)


def orchestrate_result_to_dict(result: OrchestratorResult) -> dict:
    """Convert an OrchestratorResult to a JSON-serialisable dict."""
    return {
        "ticker":          result.ticker,
        "market":          result.market,
        "final_signal":    result.final_signal,
        "conviction":      result.conviction,
        "thesis":          result.thesis,
        "consensus_score": round(result.consensus_score, 3),
        "agents": [
            {
                "agent_name":   a.agent_name,
                "signal":       a.signal,
                "confidence":   a.confidence,
                "reasoning":    a.reasoning,
                "raw_scores":   a.raw_scores,
                "data_quality": a.data_quality,
            }
            for a in result.agent_results
        ],
    }
