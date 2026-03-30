"""
Unified cross-market signal loader.

Merges Taiwan (TW) and US signals into a single DataFrame with a `market` column,
enriches with company name + industry where available, and optionally
adds AI one-liners via bulk_analyze_signals().
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────────────────────────────────────

def _load_one(path: str, market: str) -> pd.DataFrame:
    """Load a single signal CSV and tag it with `market`."""
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, dtype={"ticker": str})
        df["market"] = market
        return df
    except Exception as e:
        logger.warning("_load_one(%s) failed: %s", path, e)
        return pd.DataFrame()


def _load_mapping(path: str) -> pd.DataFrame:
    """Load a company mapping CSV, return empty DF if missing."""
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype={"ticker": str})
    except Exception:
        return pd.DataFrame()


def load_all_signals(base_dir: str) -> pd.DataFrame:
    """
    Load and merge TW + US signal CSVs into one DataFrame.

    Adds columns:
      market   — "TW" or "US"
      name     — company name (from mapping if available)
      industry — sector / industry string

    Returns empty DataFrame if no signals are found in either market.
    """
    base = Path(base_dir)

    tw_df = _load_one(str(base / "current_trending.csv"),            "TW")
    us_df = _load_one(str(base / "data_us" / "current_trending.csv"), "US")

    # Enrich TW with company mapping
    tw_mapping = _load_mapping(str(base / "data" / "company" / "company_mapping.csv"))
    if not tw_df.empty and not tw_mapping.empty:
        cols = [c for c in ["ticker", "name", "industry"] if c in tw_mapping.columns]
        tw_df = tw_df.merge(tw_mapping[cols], on="ticker", how="left")

    # Enrich US with company mapping (built by us/company_mapper.py)
    us_mapping = _load_mapping(str(base / "data_us" / "company_mapping.csv"))
    if not us_df.empty and not us_mapping.empty:
        cols = [c for c in ["ticker", "name", "industry"] if c in us_mapping.columns]
        us_df = us_df.merge(us_mapping[cols], on="ticker", how="left")

    parts = [df for df in [tw_df, us_df] if not df.empty]
    if not parts:
        return pd.DataFrame()

    merged = pd.concat(parts, ignore_index=True)

    # Normalise numeric columns
    for col in ["score", "RSI", "bias", "price", "vol_ratio"]:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    # Sort: signals first (highest score), then by market
    merged = merged.sort_values("score", ascending=False).reset_index(drop=True)
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# AI enrichment (optional — requires ANTHROPIC_API_KEY)
# ─────────────────────────────────────────────────────────────────────────────

def enrich_with_ai(df: pd.DataFrame, max_tickers: int = 15) -> pd.DataFrame:
    """
    Add an `ai_summary` column to the signals DataFrame using bulk analysis.

    Safe to call even when the API key is missing — returns the input DF
    with ai_summary="N/A" if the call fails.
    """
    if df.empty:
        return df
    try:
        from ai.analyst import bulk_analyze_signals, is_configured
        if not is_configured():
            df = df.copy()
            df["ai_summary"] = "Configure ANTHROPIC_API_KEY to enable AI analysis."
            return df

        summaries = bulk_analyze_signals(df, max_tickers=max_tickers)
        df = df.copy()
        df["ai_summary"] = df["ticker"].map(
            lambda t: summaries.get(t.upper(), "—")
        )
    except Exception as e:
        logger.warning("enrich_with_ai failed: %s", e)
        df = df.copy()
        df["ai_summary"] = f"AI error: {e}"
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Context builder (for AI chat)
# ─────────────────────────────────────────────────────────────────────────────

def build_context_summary(df: pd.DataFrame) -> str:
    """
    Build a compact text summary of current signals — injected as context
    into the AI chat system prompt.
    """
    if df.empty:
        return "No signals today across TW or US markets."

    tw = df[df["market"] == "TW"]
    us = df[df["market"] == "US"]

    lines = [f"Today's signals: {len(df)} total ({len(tw)} TW, {len(us)} US)"]

    for mkt, sub in [("Taiwan", tw), ("US", us)]:
        if sub.empty:
            continue
        top3 = sub.head(3)
        tickers = ", ".join(
            f"{r['ticker']} (score {r.get('score','?'):.1f}, RSI {r.get('RSI','?'):.0f})"
            for _, r in top3.iterrows()
        )
        avg_score = sub["score"].mean() if "score" in sub else 0
        lines.append(f"{mkt}: avg score {avg_score:.1f} | top: {tickers}")

    return "\n".join(lines)
