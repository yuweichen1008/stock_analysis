"""
Tests for options/signals.py — pure classify_signal logic.

No DB, no network, no yfinance — only the scoring / classification functions.
"""
import pytest
from options.signals import (
    classify_signal,
    _rsi_score,
    _pcr_score,
    _iv_score,
    _vol_oi_score,
)


# ── RSI scoring ───────────────────────────────────────────────────────────────

class TestRsiScore:
    def test_buy_rsi_0_gives_max(self):
        assert _rsi_score(0.0, "buy_signal") == pytest.approx(4.0)

    def test_buy_rsi_at_boundary_30_gives_zero(self):
        assert _rsi_score(30.0, "buy_signal") == pytest.approx(0.0)

    def test_buy_rsi_above_30_gives_zero(self):
        assert _rsi_score(35.0, "buy_signal") == 0.0

    def test_buy_rsi_15_gives_2(self):
        # 4 * (1 - 15/30) = 4 * 0.5 = 2.0
        assert _rsi_score(15.0, "buy_signal") == pytest.approx(2.0)

    def test_sell_rsi_100_gives_max(self):
        assert _rsi_score(100.0, "sell_signal") == pytest.approx(4.0)

    def test_sell_rsi_at_boundary_70_gives_zero(self):
        assert _rsi_score(70.0, "sell_signal") == pytest.approx(0.0)

    def test_sell_rsi_below_70_gives_zero(self):
        assert _rsi_score(65.0, "sell_signal") == 0.0

    def test_sell_rsi_85_gives_2(self):
        # 4 * ((85-70)/30) = 4 * 0.5 = 2.0
        assert _rsi_score(85.0, "sell_signal") == pytest.approx(2.0)

    def test_unusual_activity_gives_flat_2(self):
        assert _rsi_score(50.0, "unusual_activity") == 2.0

    def test_none_rsi_returns_default_1(self):
        assert _rsi_score(None, "buy_signal") == 1.0

    def test_buy_score_capped_at_4(self):
        # RSI just below 0 should not exceed 4
        assert _rsi_score(-10.0, "buy_signal") <= 4.0


# ── PCR scoring ───────────────────────────────────────────────────────────────

class TestPcrScore:
    def test_buy_extreme_fear_pcr_above_1_5_gives_3(self):
        assert _pcr_score(1.6, "buy_signal") == 3.0

    def test_buy_fear_pcr_between_1_and_1_5_gives_2(self):
        assert _pcr_score(1.2, "buy_signal") == 2.0

    def test_buy_neutral_pcr_between_0_6_and_1_gives_1(self):
        assert _pcr_score(0.8, "buy_signal") == 1.0

    def test_buy_greed_pcr_below_0_6_gives_0(self):
        assert _pcr_score(0.5, "buy_signal") == 0.0

    def test_sell_extreme_greed_pcr_below_0_4_gives_3(self):
        assert _pcr_score(0.3, "sell_signal") == 3.0

    def test_sell_greed_pcr_between_0_4_and_0_6_gives_2(self):
        assert _pcr_score(0.5, "sell_signal") == 2.0

    def test_sell_neutral_pcr_between_0_6_and_1_gives_1(self):
        assert _pcr_score(0.8, "sell_signal") == 1.0

    def test_sell_fear_pcr_above_1_gives_0(self):
        assert _pcr_score(1.2, "sell_signal") == 0.0

    def test_none_pcr_returns_default_1(self):
        assert _pcr_score(None, "buy_signal") == 1.0

    def test_unusual_pcr_treated_as_buy_side(self):
        # unusual_activity uses buy-side PCR scoring
        assert _pcr_score(1.6, "unusual_activity") == 3.0


# ── IV Rank scoring ───────────────────────────────────────────────────────────

class TestIvScore:
    def test_low_iv_rank_below_25_gives_2(self):
        assert _iv_score(10.0) == 2.0

    def test_mid_iv_rank_25_to_50_gives_1(self):
        assert _iv_score(40.0) == 1.0

    def test_high_iv_rank_above_50_gives_0(self):
        assert _iv_score(60.0) == 0.0

    def test_none_iv_rank_gives_0(self):
        assert _iv_score(None) == 0.0

    def test_boundary_25_gives_1(self):
        assert _iv_score(25.0) == 1.0

    def test_boundary_50_gives_0(self):
        assert _iv_score(50.0) == 0.0


# ── Vol/OI scoring ────────────────────────────────────────────────────────────

class TestVolOiScore:
    def test_above_3_gives_1(self):
        assert _vol_oi_score(3.1) == 1.0

    def test_exactly_3_gives_0(self):
        assert _vol_oi_score(3.0) == 0.0

    def test_below_3_gives_0(self):
        assert _vol_oi_score(2.5) == 0.0

    def test_none_gives_0(self):
        assert _vol_oi_score(None) == 0.0


# ── classify_signal ───────────────────────────────────────────────────────────

class TestClassifySignal:
    def _buy(self, rsi=25.0, pcr=1.2, iv_rank=20.0, vol_oi=1.0):
        return {"rsi_14": rsi, "pcr": pcr, "iv_rank": iv_rank, "volume_oi_ratio": vol_oi}

    def _sell(self, rsi=75.0, pcr=0.4, iv_rank=20.0, vol_oi=1.0):
        return {"rsi_14": rsi, "pcr": pcr, "iv_rank": iv_rank, "volume_oi_ratio": vol_oi}

    def _unusual(self, rsi=50.0, pcr=0.8, iv_rank=60.0, vol_oi=4.0):
        return {"rsi_14": rsi, "pcr": pcr, "iv_rank": iv_rank, "volume_oi_ratio": vol_oi}

    # classification
    def test_buy_signal_fires(self):
        sig, _, _ = classify_signal(self._buy())
        assert sig == "buy_signal"

    def test_sell_signal_fires(self):
        sig, _, _ = classify_signal(self._sell())
        assert sig == "sell_signal"

    def test_unusual_activity_fires(self):
        sig, _, _ = classify_signal(self._unusual())
        assert sig == "unusual_activity"

    def test_no_signal_when_neutral(self):
        metrics = {"rsi_14": 50.0, "pcr": 0.8, "iv_rank": 30.0, "volume_oi_ratio": 1.0}
        sig, score, _ = classify_signal(metrics)
        assert sig is None

    # priority: unusual beats buy
    def test_unusual_beats_buy_signal(self):
        m = self._buy(rsi=20.0, pcr=1.5, iv_rank=10.0, vol_oi=5.0)
        sig, _, _ = classify_signal(m)
        assert sig == "unusual_activity"

    # unusual beats sell
    def test_unusual_beats_sell_signal(self):
        m = self._sell(rsi=80.0, pcr=0.3, iv_rank=10.0, vol_oi=5.0)
        sig, _, _ = classify_signal(m)
        assert sig == "unusual_activity"

    # IV Rank gate
    def test_high_iv_rank_blocks_buy(self):
        sig, _, _ = classify_signal(self._buy(iv_rank=60.0))
        assert sig is None

    def test_high_iv_rank_blocks_sell(self):
        sig, _, _ = classify_signal(self._sell(iv_rank=60.0))
        assert sig is None

    def test_null_iv_rank_allows_buy(self):
        """Cold-start: null IV rank treated as 'cheap' — signal should still fire."""
        m = {**self._buy(), "iv_rank": None}
        sig, _, _ = classify_signal(m)
        assert sig == "buy_signal"

    def test_null_iv_rank_allows_sell(self):
        m = {**self._sell(), "iv_rank": None}
        sig, _, _ = classify_signal(m)
        assert sig == "sell_signal"

    # PCR gate
    def test_low_pcr_blocks_buy(self):
        sig, _, _ = classify_signal(self._buy(pcr=0.5))
        assert sig is None

    def test_high_pcr_blocks_sell(self):
        sig, _, _ = classify_signal(self._sell(pcr=1.2))
        assert sig is None

    # score range
    def test_score_is_between_0_and_10(self):
        for m in [self._buy(), self._sell(), self._unusual()]:
            _, score, _ = classify_signal(m)
            assert 0.0 <= score <= 10.0, f"score {score} out of range"

    def test_no_signal_score_is_zero(self):
        metrics = {"rsi_14": 50.0, "pcr": 0.8, "iv_rank": 30.0, "volume_oi_ratio": 1.0}
        _, score, _ = classify_signal(metrics)
        assert score == 0.0

    def test_score_increases_with_deeper_rsi(self):
        m_shallow = self._buy(rsi=29.0)
        m_deep    = self._buy(rsi=10.0)
        _, s1, _ = classify_signal(m_shallow)
        _, s2, _ = classify_signal(m_deep)
        assert s2 > s1

    def test_score_increases_with_more_extreme_pcr_buy(self):
        m_mild    = self._buy(pcr=1.1)
        m_extreme = self._buy(pcr=1.6)
        _, s1, _ = classify_signal(m_mild)
        _, s2, _ = classify_signal(m_extreme)
        assert s2 >= s1

    def test_score_increases_with_lower_iv_rank(self):
        m_high_iv = self._buy(iv_rank=40.0)
        m_low_iv  = self._buy(iv_rank=10.0)
        _, s1, _ = classify_signal(m_high_iv)
        _, s2, _ = classify_signal(m_low_iv)
        assert s2 >= s1

    # reason string
    def test_reason_contains_rsi(self):
        _, _, reason = classify_signal(self._buy(rsi=25.0))
        assert "RSI=25.0" in reason

    def test_reason_contains_pcr(self):
        _, _, reason = classify_signal(self._buy(pcr=1.2))
        assert "PCR=1.20" in reason

    def test_reason_contains_iv_rank(self):
        _, _, reason = classify_signal(self._buy(iv_rank=30.0))
        assert "IV_rank=30" in reason

    def test_reason_null_iv_says_accumulating(self):
        m = {**self._buy(), "iv_rank": None}
        _, _, reason = classify_signal(m)
        assert "accumulating" in reason.lower()

    # edge: missing keys handled gracefully
    def test_empty_metrics_returns_no_signal(self):
        sig, score, reason = classify_signal({})
        assert sig is None
        assert reason  # non-empty string
