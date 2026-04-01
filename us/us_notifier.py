"""
US stock Telegram notification.

Sends a daily US market update to Telegram after the US pipeline runs.
The message always contains:
  1. Index performance  (S&P 500, NASDAQ, DOW, VIX) — via yfinance
  2. Sector heat        (Finviz large-cap sector avg change) — best-effort
  3. Win-rate header    (historical US signal performance)
  4. Signal list        (if mean-reversion signals fired today)
     OR Finviz watch-list (near-oversold candidates when no full signals)
  5. Candlestick chart  (top-scoring signal ticker, if any)
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
    """Send daily US market + signal report to Telegram."""
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

    # ── Load today's signal data ──────────────────────────────────────────────
    trending_file = Path(base_dir) / "data_us" / "current_trending.csv"
    df = pd.DataFrame()
    if trending_file.exists():
        try:
            df = pd.read_csv(trending_file, dtype={"ticker": str})
        except Exception as e:
            logger.warning("send_us_report: could not read trending file: %s", e)

    signals   = df[df["is_signal"].astype(str).str.lower().isin(["true", "1"])] \
                if not df.empty else pd.DataFrame()
    watchlist = df[df.get("category", pd.Series([""] * len(df))) == "finviz_watch"] \
                if not df.empty else pd.DataFrame()

    # ── Market summary (indices + sectors) ────────────────────────────────────
    mkt = {}
    try:
        from us.finviz_data import get_market_summary
        mkt = get_market_summary()
    except Exception as e:
        logger.debug("send_us_report: market summary failed: %s", e)

    # ── Win-rate section ──────────────────────────────────────────────────────
    summary = prediction_summary(base_dir, market="US")

    # ── Build message ─────────────────────────────────────────────────────────
    title = (f"🇺🇸 *US Stock Report — {today}*"
             if not signals.empty else
             f"🇺🇸 *US Market Update — {today}*")
    lines = [title, ""]

    # 1. Index performance
    indices = mkt.get("indices", [])
    if indices:
        lines.append("📈 *Market Indices*")
        for idx in indices:
            chg  = idx["change_pct"]
            sign = "+" if chg >= 0 else ""
            icon = "🟢" if chg >= 0 else "🔴"
            lines.append(f"  {icon} {idx['name']:8s}  {sign}{chg:.2f}%"
                         f"  ({idx['price']:,.0f})")
        lines.append("")

    # 2. Sector heat (top 3 + bottom 3)
    sectors = mkt.get("sectors", [])
    if sectors:
        lines.append("🏭 *Sector Performance*")
        top3  = sectors[:3]
        bot3  = sectors[-3:]
        shown = {s["Sector"] for s in top3 + bot3}
        for s in top3:
            chg  = s.get("avg_change_pct", 0)
            sign = "+" if chg >= 0 else ""
            lines.append(f"  🟢 {s['Sector'][:20]:20s}  {sign}{chg:.2f}%")
        for s in reversed(bot3):
            if s["Sector"] not in {t["Sector"] for t in top3}:
                chg  = s.get("avg_change_pct", 0)
                sign = "+" if chg >= 0 else ""
                lines.append(f"  🔴 {s['Sector'][:20]:20s}  {sign}{chg:.2f}%")
        lines.append("")

    # 3. Win-rate
    total = summary.get("total", 0)
    if total > 0:
        wr_open  = summary["win_rate_open"]
        wr_close = summary["win_rate_close"]
        pending  = summary.get("pending", 0)
        avg_ret  = summary.get("avg_open_ret", 0)
        sign     = "+" if avg_ret >= 0 else ""
        lines += [
            "📊 *Signal Win Rate (US)*",
            f"  Open-day: *{wr_open}%*  |  Close: {wr_close}%",
            f"  {total} resolved  ·  {pending} pending  ·  Avg {sign}{avg_ret}%",
            "",
        ]
    else:
        lines += ["📊 _Win rate: building history (no resolved trades yet)_", ""]

    # 4a. Signals
    if not signals.empty:
        lines.append(f"🎯 *Today's Signals ({len(signals)})*")
        lines.append("")
        for _, r in signals.sort_values("score", ascending=False).head(10).iterrows():
            ticker    = str(r["ticker"])
            price     = r.get("price")
            score     = float(r.get("score", 0) or 0)
            rsi       = r.get("RSI")
            bias      = r.get("bias")
            vol       = r.get("vol_ratio")
            fv_pe     = r.get("fv_pe")
            fv_sec    = str(r.get("fv_sector") or "")[:22]
            fv_eps    = r.get("fv_eps")

            price_str = f"${float(price):.2f}" if pd.notna(price) and price else "N/A"
            rsi_str   = f"RSI {float(rsi):.1f}"   if pd.notna(rsi)   and rsi   else ""
            bias_str  = f"Bias {float(bias):+.1f}%" if pd.notna(bias) and bias else ""
            vol_str   = f"Vol {float(vol):.1f}x"   if pd.notna(vol)   and vol   else ""
            pe_str    = f"PE {fv_pe}"               if fv_pe else ""
            eps_str   = f"EPS ${fv_eps}"            if fv_eps else ""
            sec_str   = f"[{fv_sec}]"               if fv_sec else ""

            lines.append(f"  *{ticker}*  {price_str}  ⭐{score:.1f}")
            detail = "  ".join(filter(None, [rsi_str, bias_str, vol_str]))
            if detail:
                lines.append(f"    {detail}")
            fund = "  ".join(filter(None, [pe_str, eps_str, sec_str]))
            if fund:
                lines.append(f"    {fund}")
            lines.append("")

    # 4b. Watch-list (no signals day)
    elif not watchlist.empty:
        lines += [
            "⚠️ *No signals today* — market not deeply oversold",
            "",
            f"👀 *Finviz Watch-List* ({len(watchlist)} near-oversold candidates)",
            "",
        ]
        for _, r in watchlist.sort_values("RSI").head(8).iterrows():
            ticker    = str(r["ticker"])
            price     = r.get("price")
            rsi       = r.get("RSI")
            fv_sec    = str(r.get("fv_sector") or "")[:18]
            fv_rating = str(r.get("fv_analyst_rating") or "")

            price_str  = f"${float(price):.2f}" if pd.notna(price) and price else ""
            rsi_str    = f"RSI {float(rsi):.1f}" if pd.notna(rsi) and rsi else ""
            sec_str    = f"[{fv_sec}]"            if fv_sec else ""
            parts = "  ".join(filter(None, [price_str, rsi_str, sec_str, fv_rating]))
            lines.append(f"  `{ticker}`  {parts}")
        lines.append("")

    # 4c. Truly empty
    else:
        lines += [
            "⚠️ *No signals or watch-list data today*",
            "_Finviz may be rate-limiting — indices above still fresh._",
            "",
        ]

    # Top movers (always shown when available)
    movers = mkt.get("top_movers", [])
    if movers:
        gainers = [m for m in movers if m["change_pct"] >= 0][:3]
        losers  = [m for m in movers if m["change_pct"] < 0][:3]
        if gainers or losers:
            lines.append("🏆 *Top Movers (Large Cap)*")
            for m in gainers:
                lines.append(f"  🟢 *{m['ticker']}*  {m['change_pct']:+.2f}%  {m['sector'][:16]}")
            for m in losers:
                lines.append(f"  🔴 *{m['ticker']}*  {m['change_pct']:+.2f}%  {m['sector'][:16]}")
            lines.append("")

    msg = "\n".join(lines).strip()

    # Telegram Markdown has a 4096-char limit — truncate gracefully
    if len(msg) > 4000:
        msg = msg[:3970] + "\n\n_...message truncated_"

    try:
        tool.send_markdown(msg)
        logger.info("send_us_report: US report sent (%d chars)", len(msg))
    except Exception as e:
        logger.warning("send_us_report: text send failed: %s", e)
        return

    # ── Chart for top signal ──────────────────────────────────────────────────
    if not signals.empty:
        top = signals.sort_values("score", ascending=False).iloc[0]
        _send_top_signal_chart(base_dir, str(top["ticker"]), tool)


def _send_top_signal_chart(base_dir: str, ticker: str, tool) -> None:
    """Send a 60-day candlestick chart for the top US signal ticker."""
    try:
        ohlcv_dir = str(Path(base_dir) / "data_us" / "ohlcv")
        files = glob.glob(os.path.join(ohlcv_dir, f"{ticker}_*.csv"))
        if not files:
            return
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
