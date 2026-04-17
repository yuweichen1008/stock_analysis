"""
Shared data contracts for the multi-agent investment framework.

AgentResult      — output of each of the 6 specialist agents
OrchestratorResult — final synthesis produced by the Portfolio Manager
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ── Model constants (mirrors ai/analyst.py) ───────────────────────────────────

_SONNET = "claude-sonnet-4-6"
_HAIKU  = "claude-haiku-4-5-20251001"

# ── Shared agent system prompt ────────────────────────────────────────────────

_AGENT_SYSTEM_PROMPT = """\
You are a specialist investment agent in a quantitative multi-agent hedge fund.
Your role is to evaluate a single stock from your designated analytical perspective.

Rules:
- Ground every conclusion in the data provided; do not fabricate numbers.
- If a metric is N/A or missing, explicitly note the data gap and reduce
  your CONFIDENCE by at least 20 points (minimum confidence 0).
- Never raise exceptions — always return the structured output format.
- Respond ONLY in this exact format (no extra text before or after):

SIGNAL: BUY|HOLD|SELL
CONFIDENCE: <integer 0-100>
REASONING: <2-4 concise sentences>
"""


# ── Data contracts ────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    """Output of one specialist agent for one ticker."""
    agent_name:   str                      # value | growth | technical | sentiment | risk | valuation
    signal:       str        = "HOLD"      # BUY | HOLD | SELL
    confidence:   int        = 0           # 0–100
    reasoning:    str        = ""          # 2–4 sentence markdown
    raw_scores:   dict       = field(default_factory=dict)   # optional numeric sub-scores
    data_quality: str        = "complete"  # complete | partial | sparse


@dataclass
class OrchestratorResult:
    """Final synthesis produced by the Portfolio Manager (Sonnet)."""
    ticker:          str
    market:          str
    final_signal:    str                   # BUY | HOLD | SELL
    conviction:      int        = 0        # 0–100 weighted average
    thesis:          str        = ""       # Sonnet synthesis paragraph
    consensus_score: float      = 0.0     # fraction of agents matching final_signal
    agent_results:   List[AgentResult] = field(default_factory=list)


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_agent_response(text: str, agent_name: str) -> AgentResult:
    """
    Parse the structured SIGNAL/CONFIDENCE/REASONING response from a Haiku agent.
    Returns a safe fallback AgentResult if parsing fails.
    """
    result = AgentResult(agent_name=agent_name, data_quality="complete")
    try:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("SIGNAL:"):
                val = line.split(":", 1)[1].strip().upper()
                if val in ("BUY", "HOLD", "SELL"):
                    result.signal = val
            elif line.startswith("CONFIDENCE:"):
                val = line.split(":", 1)[1].strip()
                result.confidence = max(0, min(100, int(val)))
            elif line.startswith("REASONING:"):
                result.reasoning = line.split(":", 1)[1].strip()
    except Exception:
        pass
    return result
