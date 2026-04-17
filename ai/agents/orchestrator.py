"""
Portfolio Manager Orchestrator — Claude Sonnet synthesis.

Takes the 6 specialist agent results and produces a final investment
recommendation by weighing each perspective and resolving disagreements.
"""

from __future__ import annotations

import logging
from typing import List

from ai.agents.base import (
    AgentResult, OrchestratorResult, _SONNET, _AGENT_SYSTEM_PROMPT
)
from ai.analyst import _get_client

logger = logging.getLogger(__name__)

_ORCHESTRATOR_SYSTEM = """\
You are the Portfolio Manager of a quantitative multi-agent hedge fund.
Your job is to synthesize the signals from 6 specialist agents and make
a final, well-reasoned investment decision.

Rules:
- Weigh each agent by their confidence score.
- Identify which agents agree and what their combined reasoning implies.
- Address any significant dissenting agents explicitly.
- FINAL_SIGNAL must be BUY, HOLD, or SELL — no hedging.
- CONVICTION must be an integer 0–100.
- THESIS must be 4–6 sentences covering: (1) why the majority view is right,
  (2) the most important dissenting concern, (3) final decision rationale,
  (4) one-line risk caveat.

Respond ONLY in this exact format:
FINAL_SIGNAL: BUY|HOLD|SELL
CONVICTION: <integer 0-100>
THESIS: <4-6 sentences>
"""


def run_orchestrator(
    ticker:        str,
    market:        str,
    agent_results: List[AgentResult],
) -> OrchestratorResult:
    """
    Synthesize 6 agent results into a final portfolio manager decision.

    Parameters
    ----------
    ticker        : stock symbol
    market        : "TW" or "US"
    agent_results : list of AgentResult from all 6 agents
    """
    # Compute majority signal and weighted confidence even if Claude fails
    buy_count  = sum(1 for a in agent_results if a.signal == "BUY")
    sell_count = sum(1 for a in agent_results if a.signal == "SELL")
    hold_count = sum(1 for a in agent_results if a.signal == "HOLD")
    total      = len(agent_results) or 1

    if buy_count >= sell_count and buy_count >= hold_count:
        majority_signal = "BUY"
        majority_count  = buy_count
    elif sell_count >= hold_count:
        majority_signal = "SELL"
        majority_count  = sell_count
    else:
        majority_signal = "HOLD"
        majority_count  = hold_count

    weighted_conf = (
        sum(a.confidence for a in agent_results) // total
        if agent_results else 0
    )
    consensus_score = majority_count / total

    try:
        client = _get_client()

        # Build the agent summary table
        header = "| Agent       | Signal | Conf | Reasoning |\n|-------------|--------|------|-----------|"
        rows = []
        for a in agent_results:
            short_reason = (a.reasoning[:90] + "…") if len(a.reasoning) > 90 else a.reasoning
            rows.append(f"| {a.agent_name:<11} | {a.signal:<6} | {a.confidence:>3}% | {short_reason} |")
        table = header + "\n" + "\n".join(rows)

        # Vote tally
        vote_summary = (
            f"BUY: {buy_count}/6  HOLD: {hold_count}/6  SELL: {sell_count}/6  "
            f"Weighted avg confidence: {weighted_conf}%"
        )

        prompt = f"""\
Stock: {ticker} ({market})

Agent Analysis Results:
{table}

Vote tally: {vote_summary}
Majority signal: {majority_signal} ({majority_count}/6 agents)
"""
        msg = client.messages.create(
            model      = _SONNET,
            max_tokens = 400,
            system     = _ORCHESTRATOR_SYSTEM,
            messages   = [{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()

        # Parse response
        final_signal = majority_signal  # fallback
        conviction   = weighted_conf
        thesis       = ""

        for line in text.splitlines():
            line = line.strip()
            if line.startswith("FINAL_SIGNAL:"):
                val = line.split(":", 1)[1].strip().upper()
                if val in ("BUY", "HOLD", "SELL"):
                    final_signal = val
            elif line.startswith("CONVICTION:"):
                try:
                    conviction = max(0, min(100, int(line.split(":", 1)[1].strip())))
                except ValueError:
                    pass
            elif line.startswith("THESIS:"):
                thesis = line.split(":", 1)[1].strip()

        # If thesis spans multiple lines (some models do this)
        if not thesis:
            in_thesis = False
            thesis_lines = []
            for line in text.splitlines():
                if line.startswith("THESIS:"):
                    in_thesis = True
                    rest = line.split(":", 1)[1].strip()
                    if rest:
                        thesis_lines.append(rest)
                elif in_thesis:
                    thesis_lines.append(line)
            thesis = " ".join(thesis_lines).strip()

        return OrchestratorResult(
            ticker          = ticker,
            market          = market,
            final_signal    = final_signal,
            conviction      = conviction,
            thesis          = thesis or f"Majority ({majority_count}/6 agents) signals {majority_signal} with {weighted_conf}% avg confidence.",
            consensus_score = consensus_score,
            agent_results   = agent_results,
        )

    except Exception as e:
        logger.warning("orchestrator(%s) failed: %s", ticker, e)
        return OrchestratorResult(
            ticker          = ticker,
            market          = market,
            final_signal    = majority_signal,
            conviction      = weighted_conf,
            thesis          = f"Synthesis unavailable ({e}). Majority: {majority_signal} ({majority_count}/6).",
            consensus_score = consensus_score,
            agent_results   = agent_results,
        )
