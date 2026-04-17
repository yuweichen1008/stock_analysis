"""
Technical Agent — price action, momentum, and volume analysis.

Evaluates:
  - MA crossover state: price vs MA20 vs MA120 (trend structure)
  - RSI extremes: < 35 oversold (buy candidate), > 70 overbought (risk)
  - Bias%: deviation from MA20 (mean-reversion depth)
  - Volume confirmation: vol_ratio quality (< 1.5 on pullback = clean setup)
  - Score: existing signal scoring (0–10)
"""

from __future__ import annotations

import logging

from ai.agents.base import (
    AgentResult, _AGENT_SYSTEM_PROMPT, _HAIKU, parse_agent_response
)
from ai.analyst import _get_client

logger = logging.getLogger(__name__)


def run_technical_agent(
    ticker:  str,
    market:  str,
    metrics: dict,
) -> AgentResult:
    """
    Score a stock through a technical-analysis lens.

    Parameters
    ----------
    ticker  : stock symbol
    market  : "TW" or "US"
    metrics : dict with price, RSI, bias, MA20, MA120, vol_ratio, score,
              is_signal (optional), ma120_declining (optional)
    """
    try:
        client = _get_client()

        price   = metrics.get("price",    "N/A")
        rsi     = metrics.get("RSI",      "N/A")
        bias    = metrics.get("bias",     "N/A")
        ma20    = metrics.get("MA20",     "N/A")
        ma120   = metrics.get("MA120",    "N/A")
        vol_r   = metrics.get("vol_ratio","N/A")
        score   = metrics.get("score",    "N/A")

        # Derive MA structure label
        ma_state = "N/A"
        try:
            p  = float(str(price).replace(",", ""))
            m20  = float(str(ma20).replace(",", ""))
            m120 = float(str(ma120).replace(",", ""))
            if p > m20 > m120:
                ma_state = "Bullish (price > MA20 > MA120)"
            elif p < m20 < m120:
                ma_state = "Bearish (price < MA20 < MA120)"
            elif m120 < p < m20:
                ma_state = "Pullback in uptrend (MA120 < price < MA20)"
            elif p < m20 and p > m120:
                ma_state = "Pullback to MA120 support"
            else:
                ma_state = "Mixed / consolidation"
        except (ValueError, TypeError):
            pass

        # RSI label
        rsi_label = ""
        try:
            r = float(str(rsi))
            if r < 30:
                rsi_label = "Extremely oversold (< 30)"
            elif r < 35:
                rsi_label = "Oversold (30–35)"
            elif r > 70:
                rsi_label = "Overbought (> 70)"
            elif r > 60:
                rsi_label = "Elevated (60–70)"
            else:
                rsi_label = "Neutral (35–60)"
        except (ValueError, TypeError):
            pass

        prompt = f"""\
Stock: {ticker} ({market})

Technical Indicators:
  Price:          {price}
  RSI(14):        {rsi}  → {rsi_label}
  Bias vs MA20:   {bias}%  [< −2% = meaningful pullback; < −5% = deep pullback]
  MA20:           {ma20}
  MA120:          {ma120}
  MA Structure:   {ma_state}
  Volume ratio:   {vol_r}x  [< 1.5 on pullback = low-volatility accumulation]
  Signal score:   {score} / 10

Evaluate this stock STRICTLY as a technical analyst.
Focus on: trend structure (MA alignment), momentum (RSI), pullback depth (Bias),
and volume quality (vol_ratio).
A clean mean-reversion BUY setup has: uptrend intact (price > MA120),
RSI < 35, Bias < −2%, and vol_ratio < 1.5.
Penalise missing data — reduce CONFIDENCE by 20 pts per missing metric.
"""
        msg = client.messages.create(
            model      = _HAIKU,
            max_tokens = 200,
            system     = _AGENT_SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": prompt}],
        )
        result = parse_agent_response(msg.content[0].text.strip(), "technical")

        missing = sum(1 for v in [rsi, bias, ma20, ma120] if str(v) in ("N/A", "nan", "None", ""))
        result.data_quality = "sparse" if missing >= 3 else ("partial" if missing >= 1 else "complete")
        result.raw_scores   = {"rsi": rsi, "bias": bias, "vol_ratio": vol_r, "score": score}
        return result

    except Exception as e:
        logger.warning("technical_agent(%s) failed: %s", ticker, e)
        return AgentResult(
            agent_name   = "technical",
            signal       = "HOLD",
            confidence   = 0,
            reasoning    = f"Technical analysis unavailable: {e}",
            data_quality = "sparse",
        )
