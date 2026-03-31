import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime

from tws.taiwan_trending import apply_filters, calculate_volume_ratio


def get_valid_tickers(ohlcv_dir: str):
    """Return list of tickers from downloaded OHLCV files."""
    files = glob.glob(os.path.join(ohlcv_dir, "*.csv"))
    return [os.path.basename(f).split("_")[0] for f in files]


def run_us_trending(base_dir: str):
    """
    Run mean-reversion signal filter on all downloaded US OHLCV files.

    Output: data_us/current_trending.csv
    Columns mirror taiwan_trending output so the unified AI platform
    and dashboard can handle both markets identically.
    """
    us_data_dir = os.path.join(base_dir, "data_us")
    ohlcv_dir   = os.path.join(us_data_dir, "ohlcv")
    output_file = os.path.join(us_data_dir, "current_trending.csv")

    valid_tickers = get_valid_tickers(ohlcv_dir)
    results = []
    stats   = {"Total": 0, "Signal": 0}

    print(f"--- Running US stock analysis: {datetime.now().date()} ---")

    for ticker in valid_tickers:
        pattern        = os.path.join(ohlcv_dir, f"{ticker}_*.csv")
        existing_files = glob.glob(pattern)
        if not existing_files:
            continue

        f = existing_files[0]
        try:
            df = pd.read_csv(f, index_col=0)
            df.index = pd.to_datetime(df.index, format="mixed", errors="coerce")

            for col in ["Open", "High", "Low", "Close", "Volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

            if len(df) < 120:
                continue

            stats["Total"] += 1
            is_signal, reasons, metrics = apply_filters(df.copy())

            # Volume ratio (same calculation as TW)
            vol_ratio_series = calculate_volume_ratio(df, window=20)
            last_vol_ratio   = float(vol_ratio_series.iloc[-1]) if not vol_ratio_series.empty else None
            if last_vol_ratio is not None and np.isnan(last_vol_ratio):
                last_vol_ratio = None

            # News sentiment for US stocks (English query)
            news_sentiment = 0.0
            try:
                from tws.utils import fetch_google_news_many, get_sentiment_score
                headlines     = fetch_google_news_many(ticker, "", days=7, max_items=5)
                news_sentiment = get_sentiment_score(headlines)
            except Exception:
                pass

            row = {
                "ticker":         ticker,
                "is_signal":      is_signal,
                "category":       "mean_reversion" if is_signal else "",
                "score":          metrics.get("score", 0),
                "price":          metrics.get("price"),
                "MA120":          metrics.get("MA120"),
                "MA20":           metrics.get("MA20"),
                "RSI":            metrics.get("RSI"),
                "bias":           metrics.get("bias"),
                "vol_ratio":      round(last_vol_ratio, 2) if last_vol_ratio is not None else None,
                # US stocks have no TWSE institutional flow; keep columns for schema parity
                "foreign_net":    None,
                "f5":             None,
                "f20":            None,
                "f60":            None,
                "f_zscore":       None,
                "short_interest": None,
                "news_sentiment": round(news_sentiment, 3),
                "last_date":      df.index[-1].strftime("%Y-%m-%d"),
            }

            if is_signal:
                stats["Signal"] += 1
                results.append(row)

        except Exception as e:
            print(f"   ! Error processing {ticker}: {e}")

    print(f"   Scanned: {stats['Total']} | Signals: {stats['Signal']}")

    if results:
        pd.DataFrame(results).sort_values("score", ascending=False).to_csv(
            output_file, index=False, encoding="utf-8-sig"
        )
        print(f"[OK] US trending stocks saved to {output_file}")
    else:
        if os.path.exists(output_file):
            os.remove(output_file)
        print("[!] No US stocks matching the signal today.")


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run_us_trending(BASE_DIR)
