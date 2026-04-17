"""
Value Agent — Benjamin Graham / Warren Buffett perspective.

Evaluates: P/E, ROE, debt-to-equity, margin of safety, dividend yield.
Criteria:
  - P/E < 15   → strong value; 15–25 moderate; > 25 expensive
  - ROE > 15%  → quality moat; < 10% capital destroyer
  - D/E  < 0.5 → conservative; > 2.0 leveraged
  - Margin of safety = (target_price - price) / target_price * 100
  - Dividend yield   → income support bonus
"""

from __future__ import annotations

import logging

from ai.agents.base import (
    AgentResult, _AGENT_SYSTEM_PROMPT, _HAIKU, parse_agent_response
)
from ai.analyst import _get_client

logger = logging.getLogger(__name__)


def run_value_agent(
    ticker:       str,
    market:       str,
    fundamentals: dict,
    metrics:      dict,
) -> AgentResult:
    """
    Score a stock through a value-investor lens (Graham / Buffett criteria).

    Parameters
    ----------
    ticker       : stock symbol
    market       : "TW" or "US"
    fundamentals : dict with pe_ratio, roe, debt_to_equity, target_price,
                   price (or use metrics['price']), dividend_yield, recommendation
    metrics      : dict with price, RSI, score — used if fundamentals lacks price
    """
    try:
        client = _get_client()

        pe      = fundamentals.get("pe_ratio",       "N/A")
        roe     = fundamentals.get("roe",             "N/A")
        de      = fundamentals.get("debt_to_equity",  "N/A")
        target  = fundamentals.get("target_price",    "N/A")
        div     = fundamentals.get("dividend_yield",  "N/A")
        rec     = fundamentals.get("recommendation",  "N/A")
        price   = metrics.get("price") or fundamentals.get("price", "N/A")

        # Compute margin of safety if data is available
        mos_line = "Margin of safety: N/A (target price missing)"
        try:
            t_val = float(str(target).replace(",", ""))
            p_val = float(str(price).replace(",", ""))
            if t_val > 0 and p_val > 0:
                mos = (t_val - p_val) / t_val * 100
                mos_line = f"Margin of safety: {mos:.1f}% (target {t_val:.2f} vs price {p_val:.2f})"
        except (ValueError, TypeError):
            pass

        prompt = f"""\
Stock: {ticker} ({market})

Value Fundamentals:
  P/E ratio:       {pe}   [Graham threshold: < 15 is cheap, 15-25 moderate, > 25 expensive]
  ROE:             {roe}  [Buffett threshold: > 15% = quality moat; < 10% = poor capital allocation]
  Debt/Equity:     {de}   [Graham: < 0.5 conservative; > 2.0 dangerously leveraged]
  Dividend yield:  {div}
  Analyst target:  {target}
  Analyst rec:     {rec}
  Current price:   {price}
  {mos_line}

Evaluate this stock STRICTLY as a value investor (Graham/Buffett school).
Focus on: balance sheet safety, earnings power vs price paid, and margin of safety.
Penalise missing data — reduce CONFIDENCE by 20 pts per missing metric.
"""
        msg = client.messages.create(
            model      = _HAIKU,
            max_tokens = 200,
            system     = _AGENT_SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": prompt}],
        )
        result = parse_agent_response(msg.content[0].text.strip(), "value")

        # Tag data quality
        missing = sum(1 for v in [pe, roe, de, target] if str(v) in ("N/A", "nan", "None", ""))
        result.data_quality = "sparse" if missing >= 3 else ("partial" if missing >= 1 else "complete")
        return result

    except Exception as e:
        logger.warning("value_agent(%s) failed: %s", ticker, e)
        return AgentResult(
            agent_name   = "value",
            signal       = "HOLD",
            confidence   = 0,
            reasoning    = f"Value analysis unavailable: {e}",
            data_quality = "sparse",
        )
