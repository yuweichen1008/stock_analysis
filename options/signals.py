"""
Signal classification and scoring for options screener.

classify_signal(metrics) -> (signal_type, score, reason)

Signal types (priority order):
  unusual_activity  — vol/OI ratio > 3.0 (informed flow regardless of RSI)
  buy_signal        — RSI < 30, PCR > 1.0, IV rank cheap/unknown (fear + oversold)
  sell_signal       — RSI > 70, PCR < 0.6, IV rank cheap/unknown (greed + overbought)
  None              — no signal

Score 0-10:
  RSI component    0-4 pts
  PCR component    0-3 pts
  IV Rank          0-2 pts
  Vol/OI activity  0-1 pt
"""
from __future__ import annotations

import math


def _rsi_score(rsi: float | None, signal_type: str | None) -> float:
    if rsi is None:
        return 1.0
    if signal_type == "buy_signal":
        return min(4.0, 4.0 * (1.0 - rsi / 30.0)) if rsi < 30 else 0.0
    if signal_type == "sell_signal":
        return min(4.0, 4.0 * ((rsi - 70.0) / 30.0)) if rsi > 70 else 0.0
    return 2.0  # unusual_activity: neutral RSI contribution


def _pcr_score(pcr: float | None, signal_type: str | None) -> float:
    if pcr is None:
        return 1.0
    if signal_type in ("buy_signal", "unusual_activity"):
        if pcr > 1.5:
            return 3.0
        if pcr > 1.0:
            return 2.0
        if pcr > 0.6:
            return 1.0
        return 0.0
    if signal_type == "sell_signal":
        if pcr < 0.4:
            return 3.0
        if pcr < 0.6:
            return 2.0
        if pcr < 1.0:
            return 1.0
        return 0.0
    return 1.0


def _iv_score(iv_rank: float | None) -> float:
    if iv_rank is None:
        return 0.0
    if iv_rank < 25:
        return 2.0
    if iv_rank < 50:
        return 1.0
    return 0.0


def _vol_oi_score(ratio: float | None) -> float:
    return 1.0 if ratio is not None and ratio > 3.0 else 0.0


def classify_signal(metrics: dict) -> tuple[str | None, float, str]:
    """
    Returns (signal_type, score 0-10, human-readable reason string).
    """
    rsi          = metrics.get("rsi_14")
    pcr          = metrics.get("pcr")
    iv_rank      = metrics.get("iv_rank")
    vol_oi       = metrics.get("volume_oi_ratio")
    avg_iv       = metrics.get("avg_iv")
    pcr_label    = metrics.get("pcr_label", "")

    # ── Classify ──────────────────────────────────────────────────────────────
    iv_ok = iv_rank is None or iv_rank < 50  # null → assume cheap (cold-start)

    if vol_oi is not None and vol_oi > 3.0:
        signal_type = "unusual_activity"
    elif rsi is not None and rsi < 30 and pcr is not None and pcr > 1.0 and iv_ok:
        signal_type = "buy_signal"
    elif rsi is not None and rsi > 70 and pcr is not None and pcr < 0.6 and iv_ok:
        signal_type = "sell_signal"
    else:
        signal_type = None

    # ── Score ─────────────────────────────────────────────────────────────────
    score = round(
        _rsi_score(rsi, signal_type)
        + _pcr_score(pcr, signal_type)
        + _iv_score(iv_rank)
        + _vol_oi_score(vol_oi),
        2,
    )

    # ── Reason ────────────────────────────────────────────────────────────────
    parts = []
    parts.append(f"RSI={rsi:.1f}" if rsi is not None else "RSI=n/a")
    parts.append(f"PCR={pcr:.2f}({pcr_label})" if pcr is not None else "PCR=n/a")
    if iv_rank is not None:
        parts.append(f"IV_rank={iv_rank:.0f}")
    else:
        parts.append("IV_rank=null(accumulating)")
    if avg_iv is not None:
        parts.append(f"IV={avg_iv*100:.1f}%")
    if vol_oi is not None:
        parts.append(f"vol/OI={vol_oi:.1f}x")
    reason = "  ".join(parts)

    return signal_type, score, reason
