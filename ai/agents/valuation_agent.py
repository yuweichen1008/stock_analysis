"""
Valuation Agent — Aswath Damodaran perspective.

Evaluates intrinsic value using:
  - Earnings yield (inverse of P/E) — a simple DCF proxy
  - Return on equity as reinvestment quality signal
  - Target price vs current price (analyst intrinsic value proxy)
  - Dividend yield as income floor
  - EV/EBITDA approximation note (limited data available)

Damodaran principle: always ask "what are you paying for?"
Price is what you pay; value is what you get.
"""

from __future__ import annotations

import logging

from ai.agents.base import (
    AgentResult, _AGENT_SYSTEM_PROMPT, _HAIKU, parse_agent_response
)
from ai.analyst import _get_client

logger = logging.getLogger(__name__)


def run_valuation_agent(
    ticker:       str,
    market:       str,
    fundamentals: dict,
    metrics:      dict,
) -> AgentResult:
    """
    Score a stock through a fundamental-valuation lens (Damodaran approach).

    Parameters
    ----------
    ticker       : stock symbol
    market       : "TW" or "US"
    fundamentals : dict with pe_ratio, roe, target_price, dividend_yield
    metrics      : dict with price, score
    """
    try:
        client = _get_client()

        pe      = fundamentals.get("pe_ratio",      metrics.get("fv_pe",    "N/A"))
        roe     = fundamentals.get("roe",            "N/A")
        target  = fundamentals.get("target_price",  "N/A")
        div     = fundamentals.get("dividend_yield", "N/A")
        price   = metrics.get("price", fundamentals.get("price", "N/A"))

        # Earnings yield (1/PE) — Damodaran's simplest value metric
        ey_line = "Earnings yield: N/A"
        try:
            pe_val = float(str(pe).replace(",", ""))
            if pe_val > 0:
                ey = 1 / pe_val * 100
                ey_line = f"Earnings yield: {ey:.1f}% (= 1/PE; > 6% is attractive vs 10yr bond)"
        except (ValueError, TypeError):
            pass

        # Implied required return and intrinsic value narrative
        upside_line = "Intrinsic value vs price: N/A"
        try:
            t_val = float(str(target).replace(",", ""))
            p_val = float(str(price).replace(",", ""))
            if t_val > 0 and p_val > 0:
                upside = (t_val / p_val - 1) * 100
                upside_line = (
                    f"Analyst intrinsic value estimate: {upside:+.1f}% vs current price "
                    f"({t_val:.2f} / {p_val:.2f})"
                )
        except (ValueError, TypeError):
            pass

        # Total yield (earnings yield + dividend yield)
        total_yield_line = "Total yield: N/A"
        try:
            pe_val  = float(str(pe).replace(",", ""))
            div_val = float(str(div).strip("%").replace(",", ""))
            ey      = 1 / pe_val * 100 if pe_val > 0 else 0
            total   = ey + div_val
            total_yield_line = f"Total yield: {total:.1f}% (earnings yield {ey:.1f}% + dividend {div_val:.1f}%)"
        except (ValueError, TypeError):
            pass

        prompt = f"""\
Stock: {ticker} ({market})

Valuation Metrics:
  P/E ratio:         {pe}
  ROE:               {roe}   [Quality of earnings reinvestment]
  Dividend yield:    {div}
  Analyst target:    {target}
  Current price:     {price}
  {ey_line}
  {total_yield_line}
  {upside_line}

  Note: FCF, EV/EBITDA not directly available — estimate directionally from the above.

Evaluate this stock STRICTLY as a valuation analyst (Damodaran school).
Focus on: earnings yield vs cost of capital, ROE quality, total shareholder yield,
and whether the market price implies reasonable assumptions.
Assume 10-year risk-free rate of ~4.5% (US) or ~2% (TW) as discount benchmark.
Penalise missing data — reduce CONFIDENCE by 20 pts per missing metric.
Flag any DCF assumptions that are speculative.
"""
        msg = client.messages.create(
            model      = _HAIKU,
            max_tokens = 220,
            system     = _AGENT_SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": prompt}],
        )
        result = parse_agent_response(msg.content[0].text.strip(), "valuation")

        missing = sum(1 for v in [pe, roe, target, div] if str(v) in ("N/A", "nan", "None", ""))
        result.data_quality = "sparse" if missing >= 3 else ("partial" if missing >= 1 else "complete")
        return result

    except Exception as e:
        logger.warning("valuation_agent(%s) failed: %s", ticker, e)
        return AgentResult(
            agent_name   = "valuation",
            signal       = "HOLD",
            confidence   = 0,
            reasoning    = f"Valuation analysis unavailable: {e}",
            data_quality = "sparse",
        )
