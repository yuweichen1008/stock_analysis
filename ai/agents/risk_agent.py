"""
Risk Agent — Nassim Taleb / fat-tail risk perspective.

Evaluates:
  - Volatility proxy: vol_ratio (volume surge = price instability)
  - Drawdown proxy: |bias%| (deep deviation = fat-tail risk)
  - Debt risk: debt_to_equity (leverage amplifies downside)
  - Trend fragility: MA120 proximity (close to support = risk of breakdown)
  - Position sizing recommendation: 1–5% of portfolio

Taleb principles applied:
  - Avoid "picking up pennies in front of a steamroller"
  - Size positions inversely proportional to volatility
  - Asymmetric payoff: loss must be capped, upside open
"""

from __future__ import annotations

import logging

from ai.agents.base import (
    AgentResult, _AGENT_SYSTEM_PROMPT, _HAIKU, parse_agent_response
)
from ai.analyst import _get_client

logger = logging.getLogger(__name__)


def run_risk_agent(
    ticker:       str,
    market:       str,
    metrics:      dict,
    fundamentals: dict,
) -> AgentResult:
    """
    Score a stock through a risk-management lens (Taleb-inspired).

    Parameters
    ----------
    ticker       : stock symbol
    market       : "TW" or "US"
    metrics      : dict with RSI, bias, vol_ratio, MA120, price, score
    fundamentals : dict with debt_to_equity
    """
    try:
        client = _get_client()

        rsi    = metrics.get("RSI",      "N/A")
        bias   = metrics.get("bias",     "N/A")
        vol_r  = metrics.get("vol_ratio","N/A")
        ma120  = metrics.get("MA120",    "N/A")
        price  = metrics.get("price",    "N/A")
        de     = fundamentals.get("debt_to_equity", "N/A")

        # Volatility assessment
        vol_label = "N/A"
        try:
            v = float(str(vol_r))
            if v < 1.5:
                vol_label = f"Low ({v:.1f}x — clean pullback)"
            elif v < 3.0:
                vol_label = f"Moderate ({v:.1f}x — some volatility)"
            else:
                vol_label = f"High ({v:.1f}x — elevated risk, reduce position size)"
        except (ValueError, TypeError):
            pass

        # MA120 buffer
        ma_buffer_line = "MA120 buffer: N/A"
        try:
            p    = float(str(price).replace(",", ""))
            m120 = float(str(ma120).replace(",", ""))
            if p > 0 and m120 > 0:
                buf = (p - m120) / m120 * 100
                ma_buffer_line = f"MA120 buffer: {buf:+.1f}% (price vs long-term trend line)"
        except (ValueError, TypeError):
            pass

        # Suggested position size (rough Taleb sizing)
        pos_size = 2.0  # default 2%
        pos_label = "Suggested position size: 2% of portfolio (default)"
        try:
            v = float(str(vol_r))
            b = abs(float(str(bias)))
            if v > 3.0 or b > 10:
                pos_size  = 1.0
                pos_label = "Suggested position size: 1% (high volatility — reduce exposure)"
            elif v < 1.5 and b < 5:
                pos_size  = 3.0
                pos_label = "Suggested position size: 3% (low volatility — normal sizing)"
        except (ValueError, TypeError):
            pass

        prompt = f"""\
Stock: {ticker} ({market})

Risk Metrics:
  RSI(14):        {rsi}   [< 30 = panic selloff territory (opportunity but fragile)]
  Bias vs MA20:   {bias}%  [|bias| > 10% = fat-tail risk of continued decline]
  Volume ratio:   {vol_label}
  Debt/Equity:    {de}    [> 2.0 = leveraged balance sheet (amplifies downside)]
  {ma_buffer_line}
  {pos_label}

Evaluate this stock STRICTLY as a risk manager (Taleb school).
Focus on: downside protection, position sizing, tail risk, and whether
the risk/reward asymmetry is acceptable.
Signal BUY only if downside is clearly capped and payoff is asymmetric.
Signal SELL if leverage, volatility, or momentum create an open-ended loss scenario.
Penalise missing data — reduce CONFIDENCE by 20 pts per missing metric.
"""
        msg = client.messages.create(
            model      = _HAIKU,
            max_tokens = 220,
            system     = _AGENT_SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": prompt}],
        )
        result = parse_agent_response(msg.content[0].text.strip(), "risk")

        missing = sum(1 for v in [rsi, bias, vol_r, de] if str(v) in ("N/A", "nan", "None", ""))
        result.data_quality = "sparse" if missing >= 3 else ("partial" if missing >= 1 else "complete")
        result.raw_scores   = {"position_size_pct": pos_size, "vol_ratio": vol_r}
        return result

    except Exception as e:
        logger.warning("risk_agent(%s) failed: %s", ticker, e)
        return AgentResult(
            agent_name   = "risk",
            signal       = "HOLD",
            confidence   = 0,
            reasoning    = f"Risk analysis unavailable: {e}",
            data_quality = "sparse",
        )
