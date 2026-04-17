"""
Sentiment Agent — news sentiment, analyst consensus, and market mood.

Evaluates:
  - VADER news_sentiment score (already computed in current_trending.csv)
  - Recent news headlines
  - Analyst buy/sell/hold consensus (from company_mapping recommendation field)
  - Finviz analyst rating (fv_analyst_rating)
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ai.agents.base import (
    AgentResult, _AGENT_SYSTEM_PROMPT, _HAIKU, parse_agent_response
)
from ai.analyst import _get_client

logger = logging.getLogger(__name__)


def run_sentiment_agent(
    ticker:    str,
    market:    str,
    metrics:   dict,
    headlines: Optional[List[str]] = None,
) -> AgentResult:
    """
    Score a stock through a sentiment/narrative lens.

    Parameters
    ----------
    ticker    : stock symbol
    market    : "TW" or "US"
    metrics   : dict with news_sentiment (VADER), fv_analyst_rating,
                recommendation, score
    headlines : list of recent news headline strings (up to 8)
    """
    try:
        client = _get_client()

        vader     = metrics.get("news_sentiment",    "N/A")
        fv_rating = metrics.get("fv_analyst_rating", metrics.get("recommendation", "N/A"))
        rec       = metrics.get("recommendation",    "N/A")

        # VADER score label
        vader_label = ""
        try:
            v = float(str(vader))
            if v >= 0.05:
                vader_label = f"Positive (VADER {v:+.3f})"
            elif v <= -0.05:
                vader_label = f"Negative (VADER {v:+.3f})"
            else:
                vader_label = f"Neutral (VADER {v:+.3f})"
        except (ValueError, TypeError):
            vader_label = "N/A"

        news_block = (
            "\n".join(f"  - {h}" for h in (headlines or [])[:8])
            or "  No recent headlines available."
        )

        prompt = f"""\
Stock: {ticker} ({market})

Sentiment Indicators:
  VADER news sentiment: {vader_label}
  Analyst consensus:    {rec}
  Finviz analyst rating:{fv_rating}   [Strong Buy / Buy / Hold / Sell]

Recent News Headlines:
{news_block}

Evaluate this stock STRICTLY as a sentiment analyst.
Focus on: news tone (positive vs negative), analyst conviction,
any catalysts or red flags in the headlines.
Penalise missing data — reduce CONFIDENCE by 20 pts per missing signal.
"""
        msg = client.messages.create(
            model      = _HAIKU,
            max_tokens = 200,
            system     = _AGENT_SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": prompt}],
        )
        result = parse_agent_response(msg.content[0].text.strip(), "sentiment")

        missing = sum(1 for v in [vader, fv_rating, rec] if str(v) in ("N/A", "nan", "None", ""))
        result.data_quality = "sparse" if missing >= 2 else ("partial" if missing >= 1 else "complete")
        return result

    except Exception as e:
        logger.warning("sentiment_agent(%s) failed: %s", ticker, e)
        return AgentResult(
            agent_name   = "sentiment",
            signal       = "HOLD",
            confidence   = 0,
            reasoning    = f"Sentiment analysis unavailable: {e}",
            data_quality = "sparse",
        )
