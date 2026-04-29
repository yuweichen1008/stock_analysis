"""
API-level tests for /api/options/* endpoints.

Uses FastAPI TestClient with an in-memory SQLite DB injected via
dependency_overrides — no live PostgreSQL required.

Single module-scoped `client` fixture: tests that need data seed and
clean up within the test body so competing dependency overrides never
clobber each other.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# StaticPool: every Session() call reuses the same underlying connection,
# so tables created by create_all() are visible to all sessions.
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="module")
def client():
    from api.db import Base, get_db
    from api.main import app
    from api.routers import options as opt_mod

    Base.metadata.create_all(bind=_engine)

    def _get_test_db():
        db = _Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_test_db

    def _clear_caches():
        opt_mod._cache_screener.update({"data": None, "ts": 0.0, "key": None})
        opt_mod._cache_overview.update({"data": None, "ts": 0.0})

    _clear_caches()

    with TestClient(app) as c:
        c._clear_caches = _clear_caches  # expose for tests that need to reset
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture(autouse=True)
def _clean_db_and_cache(client):
    """Before each test: truncate options tables and clear API caches."""
    from api.db import OptionsIvSnapshot, OptionsSignal

    db = _Session()
    db.query(OptionsSignal).delete()
    db.query(OptionsIvSnapshot).delete()
    db.commit()
    db.close()
    client._clear_caches()
    yield


def _seed_one_signal():
    """Insert a known buy_signal row. Returns snapshot datetime."""
    from api.db import OptionsIvSnapshot, OptionsSignal

    snap = datetime(2026, 4, 28, 14, 45, tzinfo=timezone.utc).replace(tzinfo=None)
    db = _Session()
    db.add(OptionsSignal(
        ticker="AAPL",
        snapshot_at=snap,
        rsi_14=25.0,
        pcr=1.2,
        pcr_label="fear",
        signal_type="buy_signal",
        signal_score=7.5,
        signal_reason="RSI=25.0 PCR=1.20(fear)",
        executed=False,
    ))
    db.add(OptionsIvSnapshot(ticker="AAPL", snapshot_at=snap, avg_iv=0.28))
    db.commit()
    db.close()
    return snap


# ── /api/options/db-status ────────────────────────────────────────────────────

class TestDbStatus:
    def test_empty_returns_200(self, client):
        assert client.get("/api/options/db-status").status_code == 200

    def test_empty_seeded_false(self, client):
        assert client.get("/api/options/db-status").json()["seeded"] is False

    def test_empty_counts_zero(self, client):
        data = client.get("/api/options/db-status").json()
        assert data["options_signals"] == 0
        assert data["iv_snapshots"] == 0

    def test_empty_latest_snapshot_none(self, client):
        assert client.get("/api/options/db-status").json()["latest_snapshot"] is None

    def test_response_has_required_keys(self, client):
        data = client.get("/api/options/db-status").json()
        for key in ("options_signals", "iv_snapshots", "latest_snapshot", "seeded"):
            assert key in data

    def test_seeded_returns_true(self, client):
        _seed_one_signal()
        data = client.get("/api/options/db-status").json()
        assert data["seeded"] is True
        assert data["options_signals"] >= 1

    def test_seeded_has_latest_snapshot(self, client):
        _seed_one_signal()
        assert client.get("/api/options/db-status").json()["latest_snapshot"] is not None


# ── /api/options/screener ─────────────────────────────────────────────────────

class TestOptionsScreener:
    def test_empty_returns_200(self, client):
        assert client.get("/api/options/screener").status_code == 200

    def test_empty_count_is_zero(self, client):
        assert client.get("/api/options/screener").json()["count"] == 0

    def test_empty_signals_is_list(self, client):
        assert isinstance(client.get("/api/options/screener").json()["signals"], list)

    def test_response_shape(self, client):
        data = client.get("/api/options/screener").json()
        for key in ("snapshot_at", "count", "signals"):
            assert key in data

    def test_seeded_returns_signal(self, client):
        _seed_one_signal()
        data = client.get("/api/options/screener").json()
        assert data["count"] >= 1
        s = data["signals"][0]
        assert s["ticker"] == "AAPL"
        assert s["signal_type"] == "buy_signal"

    def test_signal_type_filter_miss(self, client):
        _seed_one_signal()
        data = client.get("/api/options/screener?signal_type=sell_signal").json()
        assert data["count"] == 0

    def test_limit_param(self, client):
        _seed_one_signal()
        assert len(client.get("/api/options/screener?limit=1").json()["signals"]) <= 1

    def test_signal_item_fields(self, client):
        _seed_one_signal()
        data = client.get("/api/options/screener").json()
        if data["count"] > 0:
            s = data["signals"][0]
            for field in ("id", "ticker", "signal_type", "signal_score", "rsi_14", "pcr"):
                assert field in s


# ── /api/options/screener/{ticker}/history ────────────────────────────────────

class TestOptionsHistory:
    def test_unknown_ticker_empty(self, client):
        data = client.get("/api/options/screener/ZZZZ/history").json()
        assert data["ticker"] == "ZZZZ"
        assert data["history"] == []

    def test_known_ticker_returns_history(self, client):
        _seed_one_signal()
        data = client.get("/api/options/screener/AAPL/history").json()
        assert data["ticker"] == "AAPL"
        assert len(data["history"]) >= 1

    def test_ticker_uppercase(self, client):
        _seed_one_signal()
        assert client.get("/api/options/screener/aapl/history").json()["ticker"] == "AAPL"


# ── /api/options/overview ─────────────────────────────────────────────────────

class TestOptionsOverview:
    def _get_with_mock_vix(self, client, vix_val=None):
        import pandas as pd
        if vix_val is None:
            mock_hist = MagicMock()
            mock_hist.empty = True
        else:
            mock_hist = pd.DataFrame({"Close": [vix_val]})
        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = mock_hist
            return client.get("/api/options/overview").json()

    def test_returns_200(self, client):
        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = MagicMock(empty=True)
            assert client.get("/api/options/overview").status_code == 200

    def test_response_has_required_keys(self, client):
        data = self._get_with_mock_vix(client)
        for key in ("vix", "market_pcr", "buy_count", "sell_count", "unusual_count",
                    "top_signals", "snapshot_at"):
            assert key in data

    def test_empty_db_zero_counts(self, client):
        data = self._get_with_mock_vix(client)
        assert data["buy_count"] == 0
        assert data["sell_count"] == 0
        assert data["unusual_count"] == 0

    def test_vix_injected_when_mocked(self, client):
        data = self._get_with_mock_vix(client, vix_val=18.5)
        assert data["vix"] == pytest.approx(18.5, abs=0.1)

    def test_seeded_buy_count(self, client):
        _seed_one_signal()
        data = self._get_with_mock_vix(client)
        assert data["buy_count"] >= 1
