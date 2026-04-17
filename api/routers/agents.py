"""
Multi-Agent Investment Analysis endpoints.

GET /api/agents/analyze?ticker=AAPL&market=US
    Run 6-agent analysis + orchestrator for a single ticker.
    Results cached for 1 hour.

GET /api/agents/batch?market=US&max_tickers=10
    Run agent analysis on today's top N signal stocks.
    Returns list of OrchestratorResult dicts.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

router = APIRouter(prefix="/api/agents", tags=["agents"])

# ── In-memory cache: {f"{ticker}_{market}": {"result": dict, "ts": float}} ──
_agent_cache: dict = {}
_AGENT_CACHE_TTL = 3600  # 1 hour — 7 Claude calls per ticker is expensive


def _is_fresh(key: str) -> bool:
    return key in _agent_cache and (time.time() - _agent_cache[key]["ts"]) < _AGENT_CACHE_TTL


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_and_cache(ticker: str, market: str) -> dict:
    from ai.agents import analyze_ticker, _load_ticker_data, orchestrate_result_to_dict
    metrics, fundamentals, headlines = _load_ticker_data(ticker, market, str(BASE_DIR))
    result  = analyze_ticker(ticker, market, metrics, fundamentals, headlines)
    payload = orchestrate_result_to_dict(result)
    payload["cached_at"] = datetime.now(timezone.utc).isoformat()
    key = f"{ticker.upper()}_{market.upper()}"
    _agent_cache[key] = {"result": payload, "ts": time.time()}
    return payload


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/analyze")
def analyze_ticker_endpoint(ticker: str, market: str = "US"):
    """
    Run 6-agent + orchestrator analysis for a single ticker.
    Results are cached for 1 hour.
    """
    key = f"{ticker.upper()}_{market.upper()}"
    if _is_fresh(key):
        return _agent_cache[key]["result"]

    try:
        return _run_and_cache(ticker.upper(), market.upper())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent analysis failed: {e}")


@router.get("/batch")
def batch_analyze(market: str = "US", max_tickers: int = 10):
    """
    Run agent analysis on today's top N signal stocks.
    Stocks are sourced from current_trending.csv (highest score first).
    Skips tickers already in cache.
    """
    import pandas as pd

    market = market.upper()
    max_tickers = min(max_tickers, 20)  # hard cap

    # Load signal list
    if market == "TW":
        path = BASE_DIR / "current_trending.csv"
    elif market == "US":
        path = BASE_DIR / "data_us" / "current_trending.csv"
    else:
        raise HTTPException(status_code=400, detail="market must be TW or US")

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Signal file not found: {path}")

    df = pd.read_csv(path, dtype={"ticker": str})
    df = df.sort_values("score", ascending=False).head(max_tickers)
    tickers = df["ticker"].str.upper().tolist()

    results = []
    for ticker in tickers:
        key = f"{ticker}_{market}"
        if _is_fresh(key):
            results.append(_agent_cache[key]["result"])
        else:
            try:
                payload = _run_and_cache(ticker, market)
                results.append(payload)
                time.sleep(0.2)  # brief pause between tickers
            except Exception as e:
                results.append({
                    "ticker":       ticker,
                    "market":       market,
                    "final_signal": "HOLD",
                    "conviction":   0,
                    "thesis":       f"Analysis failed: {e}",
                    "consensus_score": 0.0,
                    "agents":       [],
                    "error":        str(e),
                })

    return {
        "market":      market,
        "count":       len(results),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results":     results,
    }


@router.get("/cache/status")
def cache_status():
    """Show which tickers are currently cached and when they expire."""
    now = time.time()
    status = []
    for key, val in _agent_cache.items():
        age     = now - val["ts"]
        expires = max(0, _AGENT_CACHE_TTL - age)
        status.append({
            "key":         key,
            "final_signal": val["result"].get("final_signal"),
            "conviction":   val["result"].get("conviction"),
            "age_seconds":  round(age),
            "expires_in":   round(expires),
        })
    return {"cached_count": len(status), "entries": status}


@router.delete("/cache")
def clear_cache():
    """Clear all cached agent results (forces re-analysis on next request)."""
    _agent_cache.clear()
    return {"cleared": True}
