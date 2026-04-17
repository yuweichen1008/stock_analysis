"""
Growth Agent — Peter Lynch / Cathie Wood perspective.

Evaluates: analyst target upside (proxy for growth expectation), PEG ratio
(P/E ÷ estimated growth from analyst consensus), industry tailwinds,
and analyst buy/sell ratio.
"""

from __future__ import annotations

import logging

from ai.agents.base import (
    AgentResult, _AGENT_SYSTEM_PROMPT, _HAIKU, parse_agent_response
)
from ai.analyst import _get_client

logger = logging.getLogger(__name__)


def run_growth_agent(
    ticker:       str,
    market:       str,
    fundamentals: dict,
    metrics:      dict,
) -> AgentResult:
    """
    Score a stock through a growth-investor lens (Lynch / Wood criteria).

    Parameters
    ----------
    ticker       : stock symbol
    market       : "TW" or "US"
    fundamentals : dict with pe_ratio, target_price, recommendation, industry
    metrics      : dict with price, fv_analyst_rating, fv_pe, fv_sector,
                   fv_industry, score
    """
    try:
        client = _get_client()

        pe          = fundamentals.get("pe_ratio",        metrics.get("fv_pe",    "N/A"))
        target      = fundamentals.get("target_price",    "N/A")
        rec         = fundamentals.get("recommendation",  metrics.get("fv_analyst_rating", "N/A"))
        industry    = fundamentals.get("industry",        metrics.get("fv_industry", metrics.get("fv_sector", "N/A")))
        price       = metrics.get("price", fundamentals.get("price", "N/A"))

        # Estimate target upside %
        upside_line = "Target upside: N/A"
        try:
            t_val = float(str(target).replace(",", ""))
            p_val = float(str(price).replace(",", ""))
            if t_val > 0 and p_val > 0:
                upside = (t_val - p_val) / p_val * 100
                upside_line = f"Target upside: {upside:+.1f}% (target {t_val:.2f} vs price {p_val:.2f})"
        except (ValueError, TypeError):
            pass

        # Rough PEG note (P/E ÷ assumed analyst-implied growth)
        peg_line = "PEG ratio: N/A (insufficient data)"
        try:
            pe_val = float(str(pe).replace(",", ""))
            t_val  = float(str(target).replace(",", ""))
            p_val  = float(str(price).replace(",", ""))
            if pe_val > 0 and p_val > 0 and t_val > p_val:
                implied_growth = (t_val - p_val) / p_val * 100
                peg = pe_val / implied_growth if implied_growth > 0 else float("inf")
                peg_line = f"Implied PEG: {peg:.2f} (P/E {pe_val:.1f} ÷ implied growth {implied_growth:.1f}%)"
        except (ValueError, TypeError):
            pass

        prompt = f"""\
Stock: {ticker} ({market})

Growth Metrics:
  P/E ratio:       {pe}
  Analyst target:  {target}
  Analyst rec:     {rec}    [Lynch: strong buy = growth consensus]
  Industry:        {industry}
  Current price:   {price}
  {upside_line}
  {peg_line}

Evaluate this stock STRICTLY as a growth investor (Lynch / Wood school).
Focus on: earnings growth potential, industry tailwind, analyst conviction,
and whether the price justifies the growth story.
Lynch rule: only buy if you understand why the business will grow.
Wood rule: seek disruptive, exponential-growth industries.
Penalise missing data — reduce CONFIDENCE by 20 pts per missing metric.
"""
        msg = client.messages.create(
            model      = _HAIKU,
            max_tokens = 200,
            system     = _AGENT_SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": prompt}],
        )
        result = parse_agent_response(msg.content[0].text.strip(), "growth")

        missing = sum(1 for v in [pe, target, rec, industry] if str(v) in ("N/A", "nan", "None", ""))
        result.data_quality = "sparse" if missing >= 3 else ("partial" if missing >= 1 else "complete")
        return result

    except Exception as e:
        logger.warning("growth_agent(%s) failed: %s", ticker, e)
        return AgentResult(
            agent_name   = "growth",
            signal       = "HOLD",
            confidence   = 0,
            reasoning    = f"Growth analysis unavailable: {e}",
            data_quality = "sparse",
        )
