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
                "ticker":            ticker,
                "is_signal":         is_signal,
                "category":          "mean_reversion" if is_signal else "",
                "score":             metrics.get("score", 0),
                "price":             metrics.get("price"),
                "MA120":             metrics.get("MA120"),
                "MA20":              metrics.get("MA20"),
                "RSI":               metrics.get("RSI"),
                "bias":              metrics.get("bias"),
                "vol_ratio":         round(last_vol_ratio, 2) if last_vol_ratio is not None else None,
                # US stocks have no TWSE institutional flow; keep columns for schema parity
                "foreign_net":       None,
                "f5":                None,
                "f20":               None,
                "f60":               None,
                "f_zscore":          None,
                "short_interest":    None,
                "news_sentiment":    round(news_sentiment, 3),
                "last_date":         df.index[-1].strftime("%Y-%m-%d"),
                # Finviz fundamentals — populated below via enrich_signals_with_finviz()
                "fv_pe":             None,
                "fv_eps":            None,
                "fv_sector":         None,
                "fv_target_price":   None,
                "fv_analyst_rating": None,
            }

            if is_signal:
                stats["Signal"] += 1
                results.append(row)

        except Exception as e:
            print(f"   ! Error processing {ticker}: {e}")

    print(f"   Scanned: {stats['Total']} | Signals: {stats['Signal']}")

    if results:
        results_df = pd.DataFrame(results).sort_values("score", ascending=False)
        try:
            from us.finviz_data import enrich_signals_with_finviz
            results_df = enrich_signals_with_finviz(results_df)
        except Exception as e:
            print(f"   [finviz] enrichment skipped: {e}")
        results_df.to_csv(output_file, index=False, encoding="utf-8-sig")
        print(f"[OK] US trending stocks saved to {output_file}")
    else:
        print("[!] No US stocks matching the signal today — fetching Finviz watch-list...")
        watch_rows = _fetch_finviz_watchlist()
        if watch_rows:
            pd.DataFrame(watch_rows).to_csv(output_file, index=False, encoding="utf-8-sig")
            print(f"[OK] US watch-list: {len(watch_rows)} finviz candidates saved to {output_file}")
        else:
            if os.path.exists(output_file):
                os.remove(output_file)
            print("[!] Finviz watch-list also empty — no output file written.")


def _fetch_finviz_watchlist(max_results: int = 10) -> list:
    """
    Fetch near-oversold US stocks from Finviz as a watch-list fallback.
    Tries RSI<30 first; widens to RSI<45 if fewer than 5 results.
    Returns list of row dicts with the standard current_trending.csv schema.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        from us.finviz_data import get_screener_results
    except ImportError:
        return []

    def _to_rows(df: pd.DataFrame) -> list:
        rows = []
        for _, r in df.iterrows():
            try:
                rsi   = float(str(r.get("RSI (14)", "") or "").replace("%", "") or "nan")
                price = float(str(r.get("Price", "") or "").replace(",", "") or "nan")
            except ValueError:
                continue
            if np.isnan(rsi) or np.isnan(price):
                continue
            rows.append({
                "ticker":           str(r.get("Ticker", "")),
                "is_signal":        False,
                "category":         "finviz_watch",
                "score":            0.0,
                "price":            round(price, 2),
                "MA120":            None,
                "MA20":             None,
                "RSI":              round(rsi, 1),
                "bias":             None,
                "vol_ratio":        None,
                "foreign_net":      None,
                "f5":               None,
                "f20":              None,
                "f60":              None,
                "f_zscore":         None,
                "short_interest":   None,
                "news_sentiment":   0.0,
                "last_date":        today,
                "fv_pe":            r.get("P/E"),
                "fv_eps":           r.get("EPS (ttm)"),
                "fv_sector":        r.get("Sector", ""),
                "fv_target_price":  r.get("Target Price"),
                "fv_analyst_rating": r.get("Analyst Recom.", ""),
            })
        return rows

    # Try RSI < 30 (deeply oversold) — "Oversold (30)" is a valid Finviz filter
    try:
        df30 = get_screener_results(
            filters={"Country": "USA", "RSI (14)": "Oversold (30)"},
            order_by="RSI (14)",
        )
        rows = _to_rows(df30)
        if len(rows) >= 5:
            return sorted(rows, key=lambda x: x["RSI"])[:max_results]
    except Exception as e:
        print(f"   [finviz] RSI<30 screen failed: {e}")

    # Widen: fetch without RSI filter, sort ascending, keep RSI < 45 client-side
    # "Oversold (45)" is NOT a valid Finviz filter — we filter the DataFrame instead
    try:
        df_broad = get_screener_results(
            filters={"Country": "USA", "Market Cap.": "Mid+ (over $2bln)"},
            order_by="RSI (14)",
        )
        if not df_broad.empty and "RSI (14)" in df_broad.columns:
            df_broad["RSI (14)"] = pd.to_numeric(df_broad["RSI (14)"], errors="coerce")
            df_broad = df_broad[df_broad["RSI (14)"] < 45].sort_values("RSI (14)")
        rows = _to_rows(df_broad)
        return rows[:max_results]
    except Exception as e:
        print(f"   [finviz] broad RSI screen failed: {e}")

    return []


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run_us_trending(BASE_DIR)
