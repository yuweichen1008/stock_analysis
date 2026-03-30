"""
AI analyst powered by Claude.

Two models are used for cost/quality balance:
  - claude-sonnet-4-6         deep analysis, portfolio insights, cross-market commentary
  - claude-haiku-4-5-20251001 per-stock quick summaries (high volume, low cost)

All public functions return plain strings (Markdown) or generator (stream).
They never raise — errors return a graceful fallback string.
"""

from __future__ import annotations

import logging
import os
from typing import Generator, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_SONNET = "claude-sonnet-4-6"
_HAIKU  = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You are a professional quantitative stock analyst specializing in cross-market \
mean-reversion strategies covering Taiwan (TWSE) and US (S&P 500) equities.

Your analysis style:
- Concise, data-driven, actionable
- Always ground conclusions in the numbers provided
- Flag risks clearly; never oversell a setup
- Use plain Markdown; no excessive emoji
- Respond in English unless the user writes in Chinese
"""


# ─────────────────────────────────────────────────────────────────────────────
# Client singleton
# ─────────────────────────────────────────────────────────────────────────────

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file: ANTHROPIC_API_KEY=sk-ant-..."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def is_configured() -> bool:
    """Return True if the API key is present in the environment."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))


# ─────────────────────────────────────────────────────────────────────────────
# Per-signal quick analysis  (Haiku — cheap, fast)
# ─────────────────────────────────────────────────────────────────────────────

def analyze_signal(
    ticker:       str,
    market:       str,
    metrics:      dict,
    headlines:    Optional[List[str]] = None,
    fundamentals: Optional[dict]      = None,
) -> str:
    """
    Generate a 3–5 sentence trade thesis for a single signal stock.

    Parameters
    ----------
    ticker      : stock symbol
    market      : "TW" or "US"
    metrics     : dict with keys price, RSI, bias, MA120, MA20, score, vol_ratio
    headlines   : recent news headlines (list of strings)
    fundamentals: dict with pe_ratio, roe, target_price, dividend_yield, industry
    """
    try:
        client = _get_client()

        mkt_label = "Taiwan TWSE" if market == "TW" else "US S&P 500"
        news_block = (
            "\n".join(f"- {h}" for h in (headlines or [])[:5])
            or "No recent headlines available."
        )

        fund_lines = []
        if fundamentals:
            for k, v in fundamentals.items():
                if str(v) not in ("N/A", "nan", "None", ""):
                    fund_lines.append(f"  {k}: {v}")
        fund_block = "\n".join(fund_lines) or "  Not available."

        prompt = f"""\
Stock: **{ticker}** ({mkt_label})

Technical metrics:
  Price:      {metrics.get('price', 'N/A')}
  RSI(14):    {metrics.get('RSI', 'N/A')}
  Bias vs MA20: {metrics.get('bias', 'N/A')}%
  MA120:      {metrics.get('MA120', 'N/A')}
  Score:      {metrics.get('score', 'N/A')} / 10
  Vol ratio:  {metrics.get('vol_ratio', 'N/A')}x

Fundamentals:
{fund_block}

Recent news:
{news_block}

Write a concise 3–5 sentence mean-reversion trade thesis covering:
1. Why this setup is valid (the technicals)
2. Key risk to the trade
3. One-line verdict (Strong / Moderate / Weak setup)
"""
        msg = client.messages.create(
            model      = _HAIKU,
            max_tokens = 300,
            system     = _SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.warning("analyze_signal(%s) failed: %s", ticker, e)
        return f"_AI analysis unavailable: {e}_"


# ─────────────────────────────────────────────────────────────────────────────
# Bulk signal analysis  (Haiku — batch, returns per-ticker dict)
# ─────────────────────────────────────────────────────────────────────────────

def bulk_analyze_signals(signals_df: pd.DataFrame, max_tickers: int = 10) -> dict:
    """
    Analyze up to `max_tickers` signal stocks in a single Claude call.
    Returns dict {ticker: analysis_text}.

    Cheaper and faster than calling analyze_signal() per ticker.
    """
    if signals_df.empty:
        return {}
    try:
        client  = _get_client()
        top_df  = signals_df.head(max_tickers)

        rows = []
        for _, r in top_df.iterrows():
            rows.append(
                f"- {r['ticker']} ({r.get('market','?')})  "
                f"RSI={r.get('RSI','?')}  Bias={r.get('bias','?')}%  "
                f"Score={r.get('score','?')}  Price={r.get('price','?')}"
            )
        stock_list = "\n".join(rows)

        prompt = f"""\
The following stocks have fired a mean-reversion buy signal today \
(price > MA120, RSI < 35, Bias < -2%):

{stock_list}

For each ticker, write ONE sentence: the strongest reason to trade it \
and the main risk. Format as:
TICKER: [one sentence]
"""
        msg = client.messages.create(
            model      = _HAIKU,
            max_tokens = 600,
            system     = _SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()

        # Parse "TICKER: text" lines into a dict
        result = {}
        for line in text.splitlines():
            if ":" in line:
                parts = line.split(":", 1)
                t = parts[0].strip().upper()
                result[t] = parts[1].strip()
        return result
    except Exception as e:
        logger.warning("bulk_analyze_signals failed: %s", e)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Cross-market comparison  (Sonnet — deeper reasoning)
# ─────────────────────────────────────────────────────────────────────────────

def compare_markets(tw_df: pd.DataFrame, us_df: pd.DataFrame) -> str:
    """
    Generate a cross-market opportunity summary comparing TW vs US signals.
    Returns a Markdown string.
    """
    try:
        client = _get_client()

        def _summarise(df: pd.DataFrame, label: str) -> str:
            if df.empty:
                return f"{label}: No signals today."
            avg_rsi   = df["RSI"].mean()   if "RSI"   in df else "N/A"
            avg_bias  = df["bias"].mean()  if "bias"  in df else "N/A"
            avg_score = df["score"].mean() if "score" in df else "N/A"
            top = df.sort_values("score", ascending=False).head(3)
            tickers = ", ".join(top["ticker"].tolist())
            return (
                f"{label}: {len(df)} signal(s)  |  "
                f"avg RSI {avg_rsi:.1f}  Bias {avg_bias:.1f}%  Score {avg_score:.1f}\n"
                f"Top picks: {tickers}"
            )

        tw_summary = _summarise(tw_df, "Taiwan (TWSE)")
        us_summary = _summarise(us_df, "US (S&P 500)")

        prompt = f"""\
Today's mean-reversion signals across two markets:

{tw_summary}
{us_summary}

Provide a 4–6 sentence cross-market commentary covering:
1. Which market offers stronger setups today and why
2. Any notable sector or macro context worth flagging
3. Capital allocation suggestion (e.g. favour TW / US / split)
Keep it concise and actionable.
"""
        msg = client.messages.create(
            model      = _SONNET,
            max_tokens = 400,
            system     = _SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.warning("compare_markets failed: %s", e)
        return f"_Cross-market analysis unavailable: {e}_"


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio insights  (Sonnet)
# ─────────────────────────────────────────────────────────────────────────────

def portfolio_insights(positions_df: pd.DataFrame, balances: list) -> str:
    """
    AI commentary on the current portfolio composition and risk.
    Returns a Markdown string.
    """
    try:
        client = _get_client()

        if positions_df.empty:
            pos_block = "No open positions."
        else:
            top_pos = positions_df.sort_values("mkt_value", ascending=False).head(10)
            lines = []
            for _, r in top_pos.iterrows():
                lines.append(
                    f"  {r.get('broker','?')} | {r['ticker']}  "
                    f"qty={r.get('qty','?')}  val={r.get('mkt_value','?'):.0f}  "
                    f"pnl={r.get('pnl','?'):+.0f}"
                )
            pos_block = "\n".join(lines)

        bal_lines = [
            f"  {b['broker']}: total={b.get('total_value',0):,.0f}  "
            f"cash={b.get('cash',0):,.0f}  upnl={b.get('unrealized_pnl',0):+,.0f}"
            for b in (balances or [])
        ]
        bal_block = "\n".join(bal_lines) or "No balance data."

        prompt = f"""\
Current portfolio snapshot across all connected brokers:

Balances:
{bal_block}

Top positions:
{pos_block}

Provide a 4–6 sentence portfolio review covering:
1. Concentration risk (any single position or sector too large?)
2. Cash level vs invested — is there dry powder for new signals?
3. Overall P&L health
4. One actionable suggestion (rebalance / add / reduce)
"""
        msg = client.messages.create(
            model      = _SONNET,
            max_tokens = 400,
            system     = _SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.warning("portfolio_insights failed: %s", e)
        return f"_Portfolio analysis unavailable: {e}_"


# ─────────────────────────────────────────────────────────────────────────────
# Streaming chat  (Sonnet)
# ─────────────────────────────────────────────────────────────────────────────

def chat_stream(
    messages:      List[dict],
    context:       str = "",
) -> Generator[str, None, None]:
    """
    Streaming Q&A about stocks, signals, or portfolio.

    Parameters
    ----------
    messages : list of {"role": "user"|"assistant", "content": str}
    context  : optional context string injected before the conversation
               (e.g. today's signal summary, positions snapshot)

    Yields text chunks as they arrive from the API.
    """
    try:
        client = _get_client()

        system = _SYSTEM_PROMPT
        if context:
            system += f"\n\nContext for this conversation:\n{context}"

        with client.messages.stream(
            model      = _SONNET,
            max_tokens = 1024,
            system     = system,
            messages   = messages,
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        logger.warning("chat_stream failed: %s", e)
        yield f"\n\n_Error: {e}_"


def chat(messages: List[dict], context: str = "") -> str:
    """Non-streaming version of chat_stream. Returns full response string."""
    return "".join(chat_stream(messages, context))
