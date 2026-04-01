"""
US stock Telegram notification.

Sends a daily US signal report to Telegram after the US pipeline runs.
On zero-signal days, sends the Finviz watch-list so subscribers always
receive an update.

Win rate (based on historical prediction tracking) is included in every
message so subscribers can calibrate how much weight to give signals.
"""

from __future__ import annotations

import glob
import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def send_us_report(base_dir: str) -> None:
    """
    Send daily US stock report to Telegram.

    Loads data_us/current_trending.csv (written by run_us_trending).
    Builds and sends:
      - Historical win-rate header (US market only)
      - Signal list  (if is_signal == True rows exist)
      - Finviz watch-list  (if only category == "finviz_watch" rows exist)
      - Candlestick chart for the top signal ticker (best score)
    """
    from dotenv import load_dotenv
    load_dotenv(os.path.join(base_dir, ".env"))

    from tws.utils import TelegramTool
    from tws.prediction_tracker import prediction_summary

    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("send_us_report: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping")
        return

    tool  = TelegramTool(token, chat_id)
    today = datetime.now().strftime("%Y-%m-%d")

    # ── Load today's data ─────────────────────────────────────────────────────
    trending_file = Path(base_dir) / "data_us" / "current_trending.csv"
    df = pd.DataFrame()
    if trending_file.exists():
        try:
            df = pd.read_csv(trending_file, dtype={"ticker": str})
        except Exception as e:
            logger.warning("send_us_report: could not read trending file: %s", e)

    signals   = df[df["is_signal"].astype(str).str.lower().isin(["true", "1"])] if not df.empty else pd.DataFrame()
    watchlist = df[df["category"] == "finviz_watch"] if not df.empty else pd.DataFrame()

    # ── Win-rate section ──────────────────────────────────────────────────────
    summary = prediction_summary(base_dir, market="US")

    # ── Build message ─────────────────────────────────────────────────────────
    if not signals.empty:
        title = f"🇺🇸 *US Stock Report — {today}*"
    else:
        title = f"🇺🇸 *US Stock Update — {today}*"

    lines = [title, ""]

    # Win rate block
    total = summary.get("total", 0)
    if total > 0:
        wr_open  = summary["win_rate_open"]
        wr_close = summary["win_rate_close"]
        pending  = summary.get("pending", 0)
        avg_ret  = summary.get("avg_open_ret", 0)
        sign     = "+" if avg_ret >= 0 else ""
        lines += [
            "📊 *Historical Win Rate \\(US\\)*",
            f"  Open\\-day: *{wr_open}%*  \\|  Close: {wr_close}%",
            f"  {total} resolved  ·  {pending} pending  ·  Avg {sign}{avg_ret}%",
            "",
        ]
    else:
        lines += ["📊 _No resolved US trades yet — win rate building..._", ""]

    # Signal list
    if not signals.empty:
        lines.append(f"🎯 *Today's Signals \\({len(signals)}\\)*")
        lines.append("")
        for _, r in signals.sort_values("score", ascending=False).head(10).iterrows():
            ticker = str(r["ticker"])
            price  = r.get("price")
            score  = float(r.get("score", 0) or 0)
            rsi    = r.get("RSI")
            bias   = r.get("bias")
            vol    = r.get("vol_ratio")
            fv_pe  = r.get("fv_pe")
            fv_sec = str(r.get("fv_sector") or "")[:20]
            fv_eps = r.get("fv_eps")

            price_str = f"${float(price):.2f}" if price else "N/A"
            score_str = f"⭐{score:.1f}"
            rsi_str   = f"RSI {float(rsi):.1f}" if rsi else ""
            bias_str  = f"Bias {float(bias):+.1f}%" if bias else ""
            vol_str   = f"Vol {float(vol):.1f}×" if vol else ""
            pe_str    = f"PE: {fv_pe}" if fv_pe else ""
            eps_str   = f"EPS: ${fv_eps}" if fv_eps else ""

            lines.append(f"  *{ticker}*  {price_str}  {score_str}")
            detail = "  ".join(filter(None, [rsi_str, bias_str, vol_str]))
            if detail:
                lines.append(f"    {detail}")
            fund = "  ".join(filter(None, [pe_str, eps_str, f"\\[{fv_sec}\\]" if fv_sec else ""]))
            if fund:
                lines.append(f"    {fund}")
            lines.append("")

    elif not watchlist.empty:
        lines += [
            "⚠️ *No signals today*",
            "_Market not oversold enough for mean\\-reversion entries\\._",
            "",
            f"👀 *Finviz Watch\\-List* \\({len(watchlist)} near\\-oversold\\)",
            "",
        ]
        for _, r in watchlist.head(8).iterrows():
            ticker    = str(r["ticker"])
            price     = r.get("price")
            rsi       = r.get("RSI")
            fv_sec    = str(r.get("fv_sector") or "")[:18]
            fv_rating = str(r.get("fv_analyst_rating") or "")

            price_str  = f"${float(price):.2f}" if price else ""
            rsi_str    = f"RSI {float(rsi):.1f}" if rsi else ""
            sec_str    = f"\\[{fv_sec}\\]" if fv_sec else ""
            rating_str = fv_rating if fv_rating else ""

            parts = "  ".join(filter(None, [price_str, rsi_str, sec_str, rating_str]))
            lines.append(f"  `{ticker}`  {parts}")
        lines.append("")
    else:
        lines += [
            "⚠️ *No signals and no watch\\-list data today*",
            "_Re\\-run `master_run.py \\-\\-market US` to refresh\\._",
            "",
        ]

    msg = "\n".join(lines).strip()

    # ── Send text message ─────────────────────────────────────────────────────
    try:
        tool.send_markdown(msg)
    except Exception as e:
        logger.warning("send_us_report: text send failed: %s", e)
        return

    # ── Send candlestick chart for top signal ─────────────────────────────────
    if not signals.empty:
        top = signals.sort_values("score", ascending=False).iloc[0]
        _send_top_signal_chart(base_dir, str(top["ticker"]), tool)


def _send_top_signal_chart(base_dir: str, ticker: str, tool) -> None:
    """Send a candlestick chart for the top US signal ticker."""
    try:
        ohlcv_dir = str(Path(base_dir) / "data_us" / "ohlcv")
        files = glob.glob(os.path.join(ohlcv_dir, f"{ticker}_*.csv"))
        if not files:
            return

        import pandas as pd
        df = pd.read_csv(files[0], index_col=0)
        df.index = pd.to_datetime(df.index, errors="coerce")
        for col in ["Open", "High", "Low", "Close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["Open", "High", "Low", "Close"]).tail(60)

        from tws.telegram_notifier import generate_candlestick_chart
        chart_bytes = generate_candlestick_chart(ticker, df)
        if chart_bytes:
            tool.send_photo(chart_bytes, caption=f"📈 {ticker} — 60-day chart")
    except Exception as e:
        logger.debug("_send_top_signal_chart(%s) failed: %s", ticker, e)
