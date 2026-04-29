"""
Tests for options/fetcher.py — pure computation helpers.

No DB session, no yfinance network calls.
Only _compute_rsi (pure pandas/numpy) is tested here because
fetch_options_metrics() requires live yfinance data.
"""
import pandas as pd
import numpy as np
import pytest

from options.fetcher import _compute_rsi


# ── helpers ───────────────────────────────────────────────────────────────────

def _series(values):
    return pd.Series(values, dtype=float)


# ── _compute_rsi ──────────────────────────────────────────────────────────────

class TestComputeRsi:

    def test_returns_none_when_fewer_than_period_plus_1_rows(self):
        closes = _series([100.0] * 14)  # need >= 15 for period=14
        assert _compute_rsi(closes, period=14) is None

    def test_returns_none_for_period_5_with_only_5_rows(self):
        assert _compute_rsi(_series([1, 2, 3, 4, 5]), period=5) is None

    def test_all_gains_returns_100(self):
        closes = _series(range(1, 31))  # strictly increasing
        result = _compute_rsi(closes)
        assert result == 100.0

    def test_all_losses_returns_near_zero(self):
        closes = _series(range(30, 0, -1))  # strictly decreasing
        result = _compute_rsi(closes)
        assert result is not None
        assert result < 5.0

    def test_result_in_0_to_100(self):
        np.random.seed(7)
        prices = np.cumprod(1 + np.random.uniform(-0.03, 0.03, 30)) * 100
        result = _compute_rsi(_series(prices))
        assert result is not None
        assert 0.0 <= result <= 100.0

    def test_custom_period_respected(self):
        # 10 strictly increasing → RSI(5)=100
        closes = _series(range(1, 11))
        assert _compute_rsi(closes, period=5) == 100.0

    def test_result_is_float_not_none(self):
        closes = _series([100 + ((-1) ** i) * i * 0.5 for i in range(30)])
        result = _compute_rsi(closes)
        assert isinstance(result, float)

    def test_oversold_returns_low_value(self):
        # Build a series that ends with a sharp drop to make RSI low
        prices = [100.0] * 15 + [95, 90, 85, 80, 75, 70, 65, 60, 55, 50]
        result = _compute_rsi(_series(prices))
        assert result is not None
        assert result < 30.0, f"Expected RSI < 30, got {result}"

    def test_overbought_returns_high_value(self):
        # Build a series that ends with a sharp rise
        prices = [100.0] * 15 + [105, 110, 115, 120, 125, 130, 135, 140, 145, 150]
        result = _compute_rsi(_series(prices))
        assert result is not None
        assert result > 70.0, f"Expected RSI > 70, got {result}"

    def test_returns_rounded_to_2dp(self):
        closes = _series([100 + np.sin(i / 3) * 5 for i in range(30)])
        result = _compute_rsi(closes)
        if result is not None:
            assert round(result, 2) == result
