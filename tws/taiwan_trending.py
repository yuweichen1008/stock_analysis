import os
import sys
import pandas as pd
import numpy as np
import glob
import re
from datetime import datetime

# Support both `from tws.taiwan_trending import ...` (package) and
# `python tws/taiwan_trending.py` (direct execution).
try:
    from .utils import (
        fetch_twse_institutional,
        fetch_twse_institutional_range,
        fetch_twse_short_interest,
        fetch_google_news_many,
        get_sentiment_score,
        compute_foreign_metrics,
        get_last_trading_date,
        is_trading_day,
    )
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tws.utils import (
        fetch_twse_institutional,
        fetch_twse_institutional_range,
        fetch_twse_short_interest,
        fetch_google_news_many,
        get_sentiment_score,
        compute_foreign_metrics,
        get_last_trading_date,
        is_trading_day,
    )

# ── 高價潛力股 threshold ──────────────────────────────────────────────────────
HIGH_VALUE_MIN_PRICE = 500   # TWD; stocks ≥ this are candidates for moat analysis


def score_high_value_stock(metrics: dict, roe: float = None) -> tuple[bool, float]:
    """
    Determine whether a stock qualifies as a 高價潛力股 (high-value moat stock)
    and compute its moat score (0–10).

    Criteria (ALL must pass):
      price >= HIGH_VALUE_MIN_PRICE TWD
      price > MA120                 (long-term uptrend)
      RSI   > 45                    (momentum intact, not broken down)
      vol_ratio < 3.0               (not in panic selling)
      f60   > 0                     (net foreign accumulation over 60 days)

    Score breakdown:
      RSI in 50–75 → up to 3 pts   (peak momentum zone)
      f_zscore > 1 → 2 pts          (statistically significant inflow)
      price/MA120 > 1.05 → 2 pts    (comfortably above life-line)
      ROE > 15% → 2 pts             (strong profitability moat)
      price >= 1000 → 1 bonus pt    (true 千元 club)
    """
    price     = metrics.get('price', 0) or 0
    ma120     = metrics.get('MA120', 0) or 0
    rsi       = metrics.get('RSI', 0) or 0
    vol_ratio = metrics.get('vol_ratio') or 0
    f60       = metrics.get('f60') or 0
    f_zscore  = metrics.get('f_zscore') or 0

    # Hard gates
    if price < HIGH_VALUE_MIN_PRICE:
        return False, 0.0
    if ma120 <= 0 or price <= ma120:
        return False, 0.0
    if rsi <= 45:
        return False, 0.0
    if vol_ratio > 3.0:
        return False, 0.0
    if f60 <= 0:
        return False, 0.0

    # Soft score
    score = 0.0
    # RSI 50-75 momentum zone (max 3 pts)
    if 50 <= rsi <= 75:
        score += min(3.0, (rsi - 50) / 25 * 3)
    elif rsi > 75:
        score += 1.0   # overbought — partial credit only
    # Foreign inflow significance (max 2 pts)
    if f_zscore > 1:
        score += 2.0
    elif f_zscore > 0:
        score += 1.0
    # Margin above MA120 (max 2 pts)
    margin = (price - ma120) / ma120 * 100
    if margin > 5.0:
        score += 2.0
    elif margin > 2.0:
        score += 1.0
    # ROE quality moat (max 2 pts)
    if roe is not None:
        try:
            roe_val = float(roe)
            if roe_val > 20:
                score += 2.0
            elif roe_val > 15:
                score += 1.0
        except (ValueError, TypeError):
            pass
    # 千元 club bonus (1 pt)
    if price >= 1000:
        score += 1.0

    return True, round(min(score, 10.0), 2)


def get_valid_tickers(tickers_dir):
    """
    載入高成長候選名單，排除 ETF (00開頭) 與標頭
    """
    files = glob.glob(os.path.join(tickers_dir, "top20_*.csv"))
    valid_tickers = set()
    
    for f in files:
        try:
            # 讀取檔案並確保格式為字串
            df = pd.read_csv(f, header=None, dtype=str)
            for val in df[0].tolist():
                val = val.strip()
                # 確保是數字代碼且非 ETF (排除 00 開頭)
                if re.fullmatch(r'\d+', val) and not val.startswith('00'):
                    valid_tickers.add(val)
        except Exception:
            continue
            
    print(f"   - 已載入 {len(valid_tickers)} 檔候選個股 (已排除 ETF)")
    return valid_tickers

def calculate_rsi(df, window=14):
    """
    Wilder's RSI using exponential smoothing (standard definition).

    Simple rolling mean produces different values; this matches TradingView / most
    charting platforms.
    """
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Seed with SMA for the first window, then apply Wilder's EMA (alpha = 1/window)
    alpha = 1.0 / window
    avg_gain = gain.ewm(alpha=alpha, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=window, adjust=False).mean()

    # When avg_loss is 0 (no down days) RSI is 100 by definition; avoid div-by-zero NaN
    rs = avg_gain / avg_loss.where(avg_loss != 0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)
    return rsi


def calculate_volume_ratio(df, window=20):
    """Return last-day volume divided by rolling average volume (vol_ratio).

    A ratio > 1 means above-average volume. On a pullback day, lower volume is
    preferred (sellers drying up); a spike above 2.0 may indicate panic selling.
    """
    avg_vol = df['Volume'].rolling(window=window).mean()
    ratio = df['Volume'] / avg_vol.replace(0, np.nan)
    return ratio


def apply_filters(df):
    """
    Mean-reversion day-trading filter with signal quality scoring.

    Hard gates (ALL must pass for is_signal=True):
      1. Long-term health : price > MA120  (uptrend intact)
      2. Short-term pullback : bias < -2%  (price ≥ 2% below MA20, not just -0.1%)
      3. Oversold          : RSI(14) < 35  (Wilder's method)

    Soft metrics returned regardless (used for scoring & display):
      - volume_ratio : last-day volume vs 20-day avg
      - score        : 0-10 composite quality score

    Returns (is_signal: bool, reasons: list[str], metrics: dict)
      reasons entries use the form  'PASS:<condition>' or 'FAIL:<condition>'
      for transparent diagnostics.
    """
    metrics = {}
    reasons = []

    if len(df) < 120:
        return False, ["FAIL:Insufficient Data (<120 bars)"], metrics

    df = df.copy()
    df['MA120'] = df['Close'].rolling(window=120).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['RSI'] = calculate_rsi(df, window=14)

    has_volume = 'Volume' in df.columns
    if has_volume:
        df['vol_ratio'] = calculate_volume_ratio(df, window=20)

    last = df.iloc[-1]
    price    = float(last['Close'])
    ma120    = float(last['MA120'])
    ma20     = float(last['MA20'])
    rsi      = float(last['RSI'])
    bias     = (price - ma20) / ma20 * 100 if ma20 != 0 else 0.0
    vol_ratio = float(last['vol_ratio']) if has_volume and not np.isnan(last.get('vol_ratio', np.nan)) else None

    metrics.update({
        'price': price,
        'MA120': round(ma120, 2),
        'MA20': round(ma20, 2),
        'RSI': round(rsi, 2),
        'bias': round(bias, 2),
        'vol_ratio': round(vol_ratio, 2) if vol_ratio is not None else None,
    })

    # --- Hard gates ---
    is_healthy   = price > ma120          # long-term uptrend intact
    is_pullback  = bias < -2.0            # meaningful pullback (≥ 2% below MA20)
    is_oversold  = rsi < 35

    reasons.append(f"{'PASS' if is_healthy  else 'FAIL'}:MA120 health (price {'>' if is_healthy else '<='} MA120)")
    reasons.append(f"{'PASS' if is_pullback else 'FAIL'}:Pullback (bias={bias:.1f}%, need <-2%)")
    reasons.append(f"{'PASS' if is_oversold else 'FAIL'}:RSI oversold (RSI={rsi:.1f}, need <35)")

    is_signal = is_healthy and is_pullback and is_oversold

    # --- Signal quality score (0–10) ---
    # Only meaningful when signal fires, but always computed for ranking/display.
    score = 0.0
    if is_signal:
        # RSI depth: 35 → 0 maps to 0 → 4 pts
        score += max(0.0, min(4.0, (35 - rsi) / 35 * 4))
        # Bias depth: -2% → -15% maps to 0 → 3 pts
        score += max(0.0, min(3.0, (abs(bias) - 2) / 13 * 3))
        # Volume: lower vol on pullback is cleaner; penalise panic spikes > 2.5x
        if vol_ratio is not None:
            if vol_ratio <= 1.5:
                score += 2.0   # calm pullback — best
            elif vol_ratio <= 2.5:
                score += 1.0   # elevated but acceptable
            # > 2.5x: no bonus (possible capitulation / distribution)
        # MA120 margin: price comfortably above MA120 (> 5%) earns 1pt
        margin = (price - ma120) / ma120 * 100
        if margin > 5.0:
            score += 1.0

    metrics['score'] = round(score, 2)

    if is_signal:
        reasons.insert(0, f"SIGNAL:Mean Reversion (score={score:.1f})")

    return is_signal, reasons, metrics

def run_taiwan_trending(base_dir):
    """
    主執行函式：由根目錄的 master_run.py 呼叫並傳入根目錄路徑
    """
    # 統一路徑設定
    tickers_dir = os.path.join(base_dir, "data", "tickers")
    ohlcv_dir = os.path.join(base_dir, "data", "ohlcv")
    output_file = os.path.join(base_dir, "current_trending.csv")

    valid_tickers = get_valid_tickers(tickers_dir)
    results = []          # signal stocks only → current_trending.csv
    universe_rows = []    # ALL scanned tickers   → universe_snapshot.csv
    stats = {"Total": 0, "Signal": 0, "High-Value": 0, "Below MA120": 0, "Not Oversold": 0}

    # Load ROE from company mapping (needed for high-value moat scoring)
    mapping_file = os.path.join(base_dir, "data", "company", "company_mapping.csv")
    roe_map: dict = {}
    if os.path.exists(mapping_file):
        try:
            _cm = pd.read_csv(mapping_file, dtype={'ticker': str})
            if 'roe' in _cm.columns:
                roe_map = dict(zip(_cm['ticker'], _cm['roe']))
        except Exception:
            pass

    # Resolve the trading date to use for TWSE API calls.
    # On weekends/holidays the exchange is closed: roll back to the last trading day
    # so institutional flow and short interest data are always fetched for a valid date.
    now        = datetime.now()
    trading_dt = get_last_trading_date(now)
    today_str  = trading_dt.strftime('%Y%m%d')

    if not is_trading_day(now):
        lag_days = (now.date() - trading_dt.date()).days
        print(f"--- 今日非交易日 ({now.strftime('%Y-%m-%d %A')}) ---")
        print(f"    使用最近交易日資料: {trading_dt.strftime('%Y-%m-%d')} (前 {lag_days} 天)")
    print(f"--- 執行台股短線分析: {trading_dt.date()} ---")

    inst_range  = fetch_twse_institutional_range(today_str, days=60)
    inst_latest = {d['symbol']: d for d in fetch_twse_institutional(today_str)}
    short_map   = fetch_twse_short_interest(today_str)

    for ticker in valid_tickers:
        pattern = os.path.join(ohlcv_dir, f"{ticker}_*.csv")
        existing_files = glob.glob(pattern)

        if not existing_files:
            continue

        f = existing_files[0]
        try:
            df = pd.read_csv(f, index_col=0)
            df.index = pd.to_datetime(df.index, format='mixed', errors='coerce')

            cols_to_fix = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in cols_to_fix:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            df = df.dropna(subset=cols_to_fix)

            if len(df) < 120:
                continue

            stats["Total"] += 1
            is_signal, reasons, metrics = apply_filters(df)

            foreign_net = None
            f_metrics = {'f5': None, 'f20': None, 'f60': None, 'zscore': None}
            if ticker in inst_latest:
                foreign_net = inst_latest[ticker]['foreign_net']
            if ticker in inst_range:
                f_metrics = compute_foreign_metrics(inst_range[ticker])

            short_interest = short_map.get(ticker)

            headlines = fetch_google_news_many(ticker, "", days=7, max_items=5)
            sentiment  = get_sentiment_score(headlines)

            # ── 高價潛力股 moat check ─────────────────────────────────────────
            hv_metrics = {**metrics, 'f60': f_metrics.get('f60'), 'f_zscore': f_metrics.get('zscore')}
            is_high_value, hv_score = score_high_value_stock(hv_metrics, roe=roe_map.get(ticker))

            # category: mean_reversion takes precedence when both fire
            if is_signal:
                category = "mean_reversion"
                final_score = metrics.get('score', 0)
            elif is_high_value:
                category = "high_value_moat"
                final_score = hv_score
            else:
                category = ""
                final_score = metrics.get('score', 0)

            row = {
                'ticker':         ticker,
                'is_signal':      is_signal or is_high_value,
                'category':       category,
                'score':          final_score,
                'price':          metrics.get('price'),
                'MA120':          metrics.get('MA120'),
                'MA20':           metrics.get('MA20'),
                'RSI':            metrics.get('RSI'),
                'bias':           metrics.get('bias'),
                'vol_ratio':      metrics.get('vol_ratio'),
                'foreign_net':    foreign_net,
                'f5':             f_metrics.get('f5'),
                'f20':            f_metrics.get('f20'),
                'f60':            f_metrics.get('f60'),
                'f_zscore':       f_metrics.get('zscore'),
                'short_interest': short_interest,
                'news_sentiment': round(sentiment, 3),
                'last_date':      df.index[-1].strftime('%Y-%m-%d'),
            }
            universe_rows.append(row)

            if is_signal:
                stats["Signal"] += 1
                results.append(row)
            elif is_high_value:
                stats["High-Value"] += 1
                results.append(row)
            else:
                for r in reasons:
                    if r in stats:
                        stats[r] += 1

        except Exception as e:
            print(f"   ! 處理 {ticker} 時出錯: {e}")

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"   掃描: {stats['Total']} | 🚀 均值回歸: {stats['Signal']} | 💎 高價潛力: {stats['High-Value']} | 📉 生命線下: {stats['Below MA120']}")

    # ── Write signal file ───────────────────────────────────────────────────
    if results:
        pd.DataFrame(results).sort_values('score', ascending=False).to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"[OK] 短線訊號股名單已存至 {output_file}")
    else:
        if os.path.exists(output_file):
            os.remove(output_file)
        print("[!] 今日無符合短線訊號之個股。")

    # ── Write universe snapshot (used by heatmap) ────────────────────────────
    # Merge with previous snapshot so tickers from older top-20 lists are
    # preserved even when they drop off the current top-20.
    universe_file = os.path.join(base_dir, "data", "company", "universe_snapshot.csv")
    if universe_rows:
        df_new = pd.DataFrame(universe_rows)
        if os.path.exists(universe_file):
            df_old = pd.read_csv(universe_file, dtype={'ticker': str})
            # Keep old rows for tickers not scanned today, replace those that were
            df_old = df_old[~df_old['ticker'].isin(df_new['ticker'])]
            df_universe = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_universe = df_new
        df_universe.to_csv(universe_file, index=False, encoding='utf-8-sig')
        print(f"[OK] 全域快照已更新: {len(df_universe)} 檔 → {universe_file}")

if __name__ == "__main__":
    # 支援獨立執行測試
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run_taiwan_trending(ROOT)