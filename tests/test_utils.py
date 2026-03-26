import pytest
from tws.utils import compute_foreign_metrics, compute_percent_flows


def test_compute_foreign_metrics_basic():
    data = [100, -50, 200, 0, 50]
    res = compute_foreign_metrics(data)
    assert 'f5' in res and res['f5'] == sum(data)
    assert 'zscore' in res


def test_compute_percent_flows_basic():
    f_metrics = {'f5': 300, 'f20': 500, 'f60': 1000}
    vols = [1000] * 30
    res = compute_percent_flows(f_metrics, vols, base_window=20)
    assert pytest.approx(res['f5_pct'], rel=1e-3) == 300 / (1000 * 5)
    assert pytest.approx(res['f20_pct'], rel=1e-3) == 500 / (1000 * 20)
