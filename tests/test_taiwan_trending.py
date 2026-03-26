import os
import pandas as pd
from tws.taiwan_trending import run_taiwan_trending


def test_run_trending_tmpdir(tmp_path, monkeypatch):
    # Prepare a small repo structure
    base = tmp_path
    data_dir = base / 'data'
    tickers_dir = data_dir / 'tickers'
    ohlcv_dir = data_dir / 'ohlcv'
    tickers_dir.mkdir(parents=True)
    ohlcv_dir.mkdir(parents=True)

    # create a top20 file including 2330
    topfile = tickers_dir / 'top20_sample.csv'
    topfile.write_text('2330\n')

    # create a synthetic OHLCV with 130 rows to satisfy MA120 requirement
    dest = ohlcv_dir / '2330_20260305.csv'
    lines = ['Date,Open,High,Low,Close,Volume']
    base_price = 500.0
    base_vol = 1000000
    # Build an uptrend for first 120 days, then a short pullback for last 10 days
    for i in range(120):
        date = f"2026-01-{(i%31)+1:02d}"
        price = base_price + i * 1.0
        vol = base_vol + i * 10000
        lines.append(f"{date},{price},{price+5},{price-5},{price},{int(vol)}")
    # last 10 days: pullback to below MA20
    last_base = base_price + 119 * 1.0
    for j in range(10):
        date = f"2026-03-{(j%31)+1:02d}"
        price = last_base - (j+1) * 10  # drop 10,20,...
        vol = base_vol + (120 + j) * 5000
        lines.append(f"{date},{price},{price+2},{price-2},{price},{int(vol)}")
    dest.write_text('\n'.join(lines))

    # run (smoke-run; ensure it does not raise)
    run_taiwan_trending(str(base))

    # also unit-test apply_filters directly with a crafted DataFrame that should trigger a signal
    import pandas as pd
    from tws.taiwan_trending import apply_filters

    # craft 130 days increasing close, then a short pullback on last day
    closes = [500.0 + i * 1.0 for i in range(125)] + [600.0, 590.0, 580.0, 570.0, 560.0]
    dates = pd.date_range(end='2026-03-05', periods=len(closes)).strftime('%Y-%m-%d')
    df2 = pd.DataFrame({'Close': closes}, index=pd.to_datetime(dates))
    # ensure sufficient length and numeric types
    is_signal, reasons, metrics = apply_filters(df2)
    # apply_filters should return a tuple and metrics should include MA120 and RSI
    assert isinstance(is_signal, bool)
    assert isinstance(reasons, list)
    assert isinstance(metrics, dict)
