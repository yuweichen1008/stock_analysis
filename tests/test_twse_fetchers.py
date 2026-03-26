import pytest
from types import SimpleNamespace

from tws import utils


class DummyResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_fetch_twse_institutional_parsing(monkeypatch):
    sample = {
        'data': [
            ['2330', 'TSMC', '1,000', '500', '500'],
            ['3105', 'SomeCo', '200', '300', '(100)'],
        ]
    }

    def fake_get(url, timeout=1):
        return DummyResponse(sample)

    monkeypatch.setattr(utils, 'requests', SimpleNamespace(get=fake_get))
    res = utils.fetch_twse_institutional('20260326')
    assert isinstance(res, list)
    assert any(r['symbol'] == '2330' and r['foreign_net'] == 500 for r in res)
    assert any(r['symbol'] == '3105' and r['foreign_net'] == -100 for r in res)


def test_fetch_twse_short_interest_parsing(monkeypatch):
    sample = {
        'fields': ['證券代號', '證券名稱', '借券賣出'],
        'data': [
            ['2330', 'TSMC', '1,234'],
            ['2002', 'Uniq', '5,000'],
        ]
    }

    def fake_get(url, timeout=1):
        return DummyResponse(sample)

    monkeypatch.setattr(utils, 'requests', SimpleNamespace(get=fake_get))
    res = utils.fetch_twse_short_interest('20260326')
    assert isinstance(res, dict)
    assert res.get('2330') == 1234
    assert res.get('2002') == 5000