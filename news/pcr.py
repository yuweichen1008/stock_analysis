"""
Fetch put/call ratio (PCR) for US stock tickers via yfinance.

- TW tickers (4-digit numeric) are skipped — returns None immediately.
- Uses nearest-expiry options chain and sums all strikes.
- PCR = total put volume / total call volume.
"""
from __future__ import annotations

import logging

import yfinance as yf

logger = logging.getLogger(__name__)

# PCR thresholds calibrated to CBOE equity PCR historical ranges.
# PCR > 1.0: elevated put buying (fear / hedging).
# PCR < 0.5: low put buying relative to calls (complacency / greed).
_THRESHOLDS = [
    (1.5, "extreme_fear"),
    (1.0, "fear"),
    (0.6, "neutral"),
    (0.4, "greed"),
]


def _pcr_label(pcr: float) -> str:
    for threshold, label in _THRESHOLDS:
        if pcr > threshold:
            return label
    return "extreme_greed"


def fetch_pcr(ticker: str) -> dict | None:
    """
    Return {put_volume, call_volume, pcr, pcr_label} for a US ticker, or None.

    Returns None for TW tickers, tickers with no options, or on any error.
    """
    if not ticker:
        return None
    # Taiwan tickers are 4-digit numbers (e.g. "2330", "2454")
    if ticker.isdigit():
        return None

    try:
        t = yf.Ticker(ticker)
        exps = t.options
        if not exps:
            return None

        chain = t.option_chain(exps[0])  # nearest expiry
        put_vol  = int(chain.puts["volume"].fillna(0).sum())
        call_vol = int(chain.calls["volume"].fillna(0).sum())

        if call_vol == 0:
            return None

        pcr = round(put_vol / call_vol, 3)
        return {
            "put_volume":  put_vol,
            "call_volume": call_vol,
            "pcr":         pcr,
            "pcr_label":   _pcr_label(pcr),
        }
    except Exception as exc:
        logger.debug("fetch_pcr(%s) error: %s", ticker, exc)
        return None
