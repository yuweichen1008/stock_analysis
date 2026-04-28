"""
Options screener universe — pre-filters to ~200 liquid US stocks.

Three-layer union (priority order):
  1. Finviz unusual options volume  (~30-80 tickers, highest signal)
  2. Recent WeeklySignal tickers    (continuity with weekly pipeline)
  3. S&P 500 components             (broad, always-liquid fallback)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

MAX_UNIVERSE = 200


def _finviz_unusual_options() -> list[str]:
    try:
        from us.finviz_data import get_screener_results
        df = get_screener_results(
            filters={
                "Option/Short": "Unusual Volume",
                "Market Cap.":  "+Small (over $300mln)",
            },
            order_by="Volume",
        )
        if df.empty or "Ticker" not in df.columns:
            return []
        return [str(t).upper() for t in df["Ticker"].dropna().tolist()]
    except Exception as exc:
        logger.warning("Finviz unusual options fetch failed: %s", exc)
        return []


def _recent_weekly_signal_tickers(db) -> list[str]:
    try:
        from api.db import WeeklySignal
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=14)
        rows = (
            db.query(WeeklySignal.ticker)
            .filter(
                WeeklySignal.signal_type.isnot(None),
                WeeklySignal.created_at >= cutoff,
            )
            .distinct()
            .all()
        )
        return [r.ticker for r in rows]
    except Exception as exc:
        logger.warning("Weekly signal ticker fetch failed: %s", exc)
        return []


def _sp500_tickers() -> list[str]:
    try:
        from us.core import USStockEngine
        engine = USStockEngine(base_dir=".")
        return engine.get_sp500_tickers()
    except Exception as exc:
        logger.warning("S&P 500 ticker fetch failed: %s", exc)
        return []


def get_options_universe(db) -> list[str]:
    """Return up to MAX_UNIVERSE deduplicated US stock tickers for options scanning."""
    layer1 = _finviz_unusual_options()
    layer2 = _recent_weekly_signal_tickers(db)

    seen: set[str] = set()
    ordered: list[str] = []

    for t in layer1 + layer2:
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)

    if len(ordered) < MAX_UNIVERSE:
        layer3 = _sp500_tickers()
        for t in layer3:
            if len(ordered) >= MAX_UNIVERSE:
                break
            if t and t not in seen:
                seen.add(t)
                ordered.append(t)

    logger.info(
        "Options universe: %d tickers (finviz=%d, weekly=%d)",
        len(ordered), len(layer1), len(layer2),
    )
    return ordered[:MAX_UNIVERSE]
