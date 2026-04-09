import os
import io
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go
from tws.models import StockAI
from tws.utils import (TelegramTool, fetch_twse_all_prices,
                        fetch_google_news_many,
                        get_last_trading_date, is_trading_day)
from dotenv import load_dotenv


def generate_candlestick_chart(ticker, df, pred_price=None):
    """
    Generate a 60-day candlestick chart with MA20/MA120 overlays.
    Returns PNG bytes, or None on failure.

    Args:
        ticker: stock ticker string (for chart title)
        df: DataFrame with columns Open/High/Low/Close and a DatetimeIndex
        pred_price: optional Ledoit-Wolf predicted price (draws a dashed line)
    """
    try:
        df = df.copy()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA120'] = df['Close'].rolling(120).mean()

        fig = go.Figure()

        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df['Open'], high=df['High'],
            low=df['Low'], close=df['Close'],
            name=ticker,
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350',
        ))

        fig.add_trace(go.Scatter(
            x=df.index, y=df['MA20'],
            line=dict(color='#ffa726', width=1.2),
            name='MA20',
        ))

        fig.add_trace(go.Scatter(
            x=df.index, y=df['MA120'],
            line=dict(color='#42a5f5', width=1.2),
            name='MA120',
        ))

        if pred_price is not None:
            fig.add_hline(
                y=pred_price,
                line=dict(color='#ab47bc', width=1, dash='dash'),
                annotation_text=f'AI Target {pred_price:.1f}',
                annotation_position='right',
            )

        fig.update_layout(
            title=f'{ticker} — 60-day Chart',
            xaxis_rangeslider_visible=False,
            template='plotly_dark',
            margin=dict(l=40, r=40, t=40, b=30),
            width=800, height=400,
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
        )

        return fig.to_image(format='png')
    except Exception:
        return None

def generate_industry_heatmap(df_trend, mapping_df, universe_df=None):
    """
    Finviz-style treemap of Taiwan stocks grouped by industry.

    When universe_df is supplied (universe_snapshot.csv) the map shows ALL
    historically tracked tickers:
      - Signal stocks  (is_signal=True)  → green gradient by score (0–10)
      - Non-signal stocks                → dark gray

    When universe_df is None (fallback) only today's signal stocks are shown.

    Tile size  = score for signal stocks; 0.4 for non-signal (still visible)
    Tile color = score (-1 sentinel for non-signal → rendered as gray)

    Returns PNG bytes, or None on failure.
    """
    try:
        # ── Choose data source ────────────────────────────────────────────────
        if universe_df is not None and not universe_df.empty:
            source = universe_df.copy()
            source['is_signal'] = source['is_signal'].astype(str).str.lower().isin(['true', '1', 'yes'])
        else:
            source = df_trend.copy()
            source['is_signal'] = True   # df_trend contains only signal rows

        merged = source.merge(
            mapping_df[['ticker', 'name', 'industry']],
            on='ticker', how='left',
        )
        merged['industry'] = merged['industry'].fillna('Other').str.strip()
        merged['name']     = merged['name'].fillna(merged['ticker'])
        merged['score']    = pd.to_numeric(merged.get('score'),  errors='coerce').fillna(0)
        merged['RSI']      = pd.to_numeric(merged.get('RSI'),    errors='coerce')
        merged['bias']     = pd.to_numeric(merged.get('bias'),   errors='coerce')

        if merged.empty:
            return None

        industries = sorted(merged['industry'].unique().tolist())

        # ── Color encoding ────────────────────────────────────────────────────
        # We use -1 as a sentinel for non-signal tiles so the colorscale can map
        # them to gray while keeping 0–10 on the green gradient.
        def tile_color(row):
            return float(row['score']) if row['is_signal'] else -1.0

        def tile_size(row):
            return float(row['score']) if row['is_signal'] else 0.4

        def tile_label(row):
            if row['is_signal']:
                rsi_str  = f" RSI {row['RSI']:.0f}"  if pd.notna(row['RSI'])  else ''
                bias_str = f" Bias {row['bias']:.1f}%" if pd.notna(row['bias']) else ''
                return (
                    f"<b>{row['ticker']}</b><br>{row['name']}<br>"
                    f"▲ {row['score']:.1f}{rsi_str}{bias_str}"
                )
            rsi_str = f" RSI {row['RSI']:.0f}" if pd.notna(row['RSI']) else ''
            return f"<b>{row['ticker']}</b><br>{row['name']}{rsi_str}"

        def hover_label(row):
            status = '✅ Signal' if row['is_signal'] else '⬜ No signal'
            lines  = [
                f"<b>{row['ticker']}  {row['name']}</b>",
                f"Industry: {row['industry']}",
                status,
            ]
            if pd.notna(row['RSI']):  lines.append(f"RSI: {row['RSI']:.1f}")
            if pd.notna(row['bias']): lines.append(f"Bias: {row['bias']:.1f}%")
            if row['is_signal']:      lines.append(f"Score: {row['score']:.1f} / 10")
            return '<br>'.join(lines)

        colors      = [np.nan] + [np.nan] * len(industries) + [tile_color(r) for _, r in merged.iterrows()]
        values      = [0]      + [0]      * len(industries) + [tile_size(r)  for _, r in merged.iterrows()]
        tile_texts  = ['']     + [f'<b>{i}</b>' for i in industries] + [tile_label(r)  for _, r in merged.iterrows()]
        hover_texts = ['']     + industries + [hover_label(r) for _, r in merged.iterrows()]

        # ── Colorscale: gray for -1, green gradient for 0–10 ─────────────────
        # With cmin=-1, cmax=10 the normalized positions are:
        #   value -1 → pos 0.0  (gray)
        #   value  0 → pos 0.09 (very dark green, edge of signal zone)
        #   value 10 → pos 1.0  (bright green)
        colorscale = [
            [0.00, '#3a3a3a'],   # no-signal gray
            [0.07, '#3a3a3a'],   # buffer
            [0.09, '#0d2b0d'],   # score ≈ 0
            [0.30, '#1b5e20'],
            [0.60, '#2e7d32'],
            [0.82, '#43a047'],
            [1.00, '#00e676'],   # score = 10
        ]

        n_signal = int(merged['is_signal'].sum())
        n_total  = len(merged)
        title_text = (
            f'TWS Market Map — {n_signal} signal / {n_total} tracked  '
            f'({pd.Timestamp.now().strftime("%Y-%m-%d")})'
        )

        labels  = ['市場'] + industries + merged['ticker'].tolist()
        parents = ['']    + ['市場'] * len(industries) + merged['industry'].tolist()

        fig = go.Figure(go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            text=tile_texts,
            customdata=hover_texts,
            textinfo='text',
            hovertemplate='%{customdata}<extra></extra>',
            textfont=dict(size=11, color='white', family='monospace'),
            marker=dict(
                colors=colors,
                colorscale=colorscale,
                cmin=-1,
                cmax=10,
                showscale=True,
                colorbar=dict(
                    title=dict(text='Score', font=dict(color='#cccccc', size=11)),
                    thickness=12,
                    tickvals=[-1, 0, 2, 4, 6, 8, 10],
                    ticktext=['N/A', '0', '2', '4', '6', '8', '10'],
                    tickfont=dict(color='#cccccc', size=9),
                    bgcolor='rgba(0,0,0,0)',
                ),
                line=dict(color='#0d1117', width=1.5),
                pad=dict(t=20, l=4, r=4, b=4),
            ),
            root_color='#0d1117',
            pathbar=dict(visible=False),
        ))

        fig.update_layout(
            title=dict(
                text=title_text,
                font=dict(color='#eeeeee', size=14),
                x=0.5, xanchor='center',
            ),
            template='plotly_dark',
            paper_bgcolor='#0d1117',
            plot_bgcolor='#0d1117',
            width=1100,
            height=max(600, 70 * len(industries) + 150),
            margin=dict(l=10, r=10, t=55, b=10),
        )

        return fig.to_image(format='png')
    except Exception:
        return None


def generate_signal_board(universe_df: pd.DataFrame, mapping_df: pd.DataFrame):
    """
    Horizontal RSI bar chart for all tracked tickers — replaces the sparse treemap.

    Color zones:
      🟢 Signal      (is_signal=True)              → bright green
      🟠 Watch zone  (RSI 35–55, price > MA120)    → orange
      🔴 Below MA120 (life line broken)             → red
      ⬜ Neutral     (RSI ≥ 55)                    → slate gray

    Sorted by RSI ascending so the most oversold tickers appear at the top.
    Each bar is annotated with Bias% and score (for signal stocks).
    Returns PNG bytes or None.
    """
    try:
        df = universe_df.copy()

        # Merge display names
        if not mapping_df.empty and 'ticker' in mapping_df.columns and 'name' in mapping_df.columns:
            df = df.merge(mapping_df[['ticker', 'name']], on='ticker', how='left')
            df['label'] = df['ticker'] + ' ' + df['name'].fillna(df['ticker'])
        else:
            df['label'] = df['ticker']

        df['RSI']       = pd.to_numeric(df.get('RSI'),   errors='coerce')
        df['MA120']     = pd.to_numeric(df.get('MA120'), errors='coerce')
        df['price']     = pd.to_numeric(df.get('price'), errors='coerce')
        df['bias']      = pd.to_numeric(df.get('bias'),  errors='coerce')
        df['score']     = pd.to_numeric(df.get('score', 0), errors='coerce').fillna(0)
        df['is_signal'] = df['is_signal'].astype(str).str.lower().isin(['true', '1', 'yes'])

        df = df.dropna(subset=['RSI']).sort_values('RSI')
        if df.empty:
            return None

        def _color(row):
            if row['is_signal']:
                return '#00e676'   # bright green — active signal
            price = row['price'] if pd.notna(row['price']) else None
            ma120 = row['MA120'] if pd.notna(row['MA120']) else None
            if price is not None and ma120 is not None and price <= ma120:
                return '#ef5350'   # red — below life line
            if row['RSI'] < 50:
                return '#ffa726'   # orange — watch zone
            return '#78909c'       # slate — neutral

        def _annot(row):
            parts = []
            if pd.notna(row['bias']):
                parts.append(f"Bias {row['bias']:.1f}%")
            if row['is_signal']:
                parts.append(f"⭐{row['score']:.1f}")
            return '  '.join(parts)

        colors      = [_color(r) for _, r in df.iterrows()]
        annotations = [_annot(r) for _, r in df.iterrows()]
        n_signal    = int(df['is_signal'].sum())
        n_total     = len(df)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df['RSI'],
            y=df['label'],
            orientation='h',
            marker_color=colors,
            text=annotations,
            textposition='outside',
            textfont=dict(color='#cccccc', size=10),
            hovertemplate='<b>%{y}</b><br>RSI: %{x:.1f}<extra></extra>',
        ))

        fig.add_vline(x=35, line=dict(color='#00e676', width=1.2, dash='dash'),
                      annotation_text='Oversold 35',
                      annotation_font=dict(color='#00e676', size=10),
                      annotation_position='top right')
        fig.add_vline(x=50, line=dict(color='#ffa726', width=1, dash='dot'),
                      annotation_text='Mid 50',
                      annotation_font=dict(color='#ffa726', size=10),
                      annotation_position='top right')

        bar_h      = max(22, min(38, 560 // max(n_total, 1)))
        chart_h    = max(280, n_total * bar_h + 130)
        date_s     = pd.Timestamp.now().strftime('%Y-%m-%d')

        fig.update_layout(
            title=dict(
                text=f'TWS Signal Board — {n_signal} 訊號 / {n_total} 追蹤中  ({date_s})',
                font=dict(color='#eeeeee', size=13),
                x=0.5, xanchor='center',
            ),
            xaxis=dict(
                title='RSI(14)', range=[0, 115],
                gridcolor='#2a2a2a',
                tickfont=dict(color='#aaa'),
                titlefont=dict(color='#aaa'),
            ),
            yaxis=dict(tickfont=dict(color='#cccccc', size=10), automargin=True),
            template='plotly_dark',
            paper_bgcolor='#0d1117',
            plot_bgcolor='#0d1117',
            width=900,
            height=chart_h,
            margin=dict(l=10, r=130, t=55, b=30),
            showlegend=False,
        )

        return fig.to_image(format='png')
    except Exception:
        return None


def clean_display(val, is_pct=False):
    if val is None or str(val) == "N/A" or pd.isna(val): return "N/A"
    try:
        f = float(val)
        if is_pct: f *= 100
        return f"{f:.2f}" + ("%" if is_pct else "")
    except: return "N/A"

def _send_signal_map(base_dir, tool, mapping_df, df_trend):
    """Send signal board (RSI bar chart) for all tracked tickers — called by send_stock_report."""
    try:
        universe_file = os.path.join(base_dir, "data", "company", "universe_snapshot.csv")
        universe_df   = pd.read_csv(universe_file, dtype={'ticker': str}) if os.path.exists(universe_file) else None
        # Use universe snapshot if available; else fall back to today's signals only
        source_df = universe_df if (universe_df is not None and not universe_df.empty) else df_trend
        if source_df is None or source_df.empty:
            return
        board_bytes = generate_signal_board(source_df, mapping_df)
        if board_bytes:
            n_sig   = len(df_trend)
            n_total = len(source_df)
            tool.send_photo(
                board_bytes,
                caption=f'📊 TWS Signal Board — {n_sig} 訊號 / {n_total} 追蹤中',
            )
    except Exception:
        pass


def send_stock_report(base_dir):
    """
    Send the daily TWS signal report to Telegram.

    Format (one message + one image):
      1. Actionable buy list with key metrics per signal stock
      2. Universe signal map heatmap

    No per-stock candlestick charts — subscribers only need what to buy today.
    """
    load_dotenv(os.path.join(base_dir, ".env"))
    mapping_file  = os.path.join(base_dir, "data", "company", "company_mapping.csv")
    trending_file = os.path.join(base_dir, "current_trending.csv")

    if not os.path.exists(mapping_file):
        return

    mapping_df = pd.read_csv(mapping_file, dtype={'ticker': str})
    tool       = TelegramTool(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))
    mapping    = mapping_df.set_index('ticker').to_dict('index')
    date_label = get_last_trading_date().strftime('%Y-%m-%d')

    # ── No signal today ───────────────────────────────────────────────────────
    if not os.path.exists(trending_file):
        tool.send_markdown(
            f"📭 *TWS {date_label} — 今日無訊號*\n\n"
            "市場尚未出現均值回歸條件，建議觀望。\n"
            "_需同時滿足: 價>MA120 + Bias<-2% + RSI<35_"
        )
        _send_signal_map(base_dir, tool, mapping_df, pd.DataFrame())
        return

    df_trend = pd.read_csv(trending_file, dtype={'ticker': str})
    if df_trend.empty:
        return

    # Split by category (handle files without category column gracefully)
    if 'category' not in df_trend.columns:
        df_trend['category'] = 'mean_reversion'
    df_mr  = df_trend[df_trend['category'] == 'mean_reversion']
    df_hv  = df_trend[df_trend['category'] == 'high_value_moat']

    # ── Per-ticker historical win rate lookup ─────────────────────────────────
    _ticker_wr: dict = {}
    try:
        from tws.prediction_tracker import _load_history
        hist = _load_history(base_dir)
        resolved = hist[(hist['status'] == 'resolved') & (hist['market'] == 'TW')]
        if not resolved.empty:
            for tkr, grp in resolved.groupby('ticker'):
                n    = len(grp)
                wins = int(grp['win_open'].sum())
                _ticker_wr[str(tkr)] = (wins, n)
    except Exception:
        pass

    def _wr_tag(ticker: str) -> str:
        """Return a short win-rate badge string, or empty string if no history."""
        if ticker not in _ticker_wr:
            return ''
        wins, n = _ticker_wr[ticker]
        pct = wins / n * 100
        icon = '✅' if pct >= 60 else ('⚠️' if pct >= 40 else '❌')
        return f'  {icon}歷史勝率 {wins}/{n} ({pct:.0f}%)'

    # ── Helper to format a single signal row ─────────────────────────────────
    def _row_line(rank, row, show_moat=False):
        t    = str(row['ticker'])
        info = mapping.get(t, {})
        name = info.get('name', t)
        ind  = info.get('industry', '')

        def _fmt(col, fmt='.1f'):
            v = row.get(col)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return 'N/A'
            try:
                return format(float(v), fmt)
            except (ValueError, TypeError):
                return str(v)

        score = _fmt('score')
        price = _fmt('price', '.1f')
        rsi   = _fmt('RSI',   '.1f')

        sent_raw = row.get('news_sentiment', 0)
        try:
            s = float(sent_raw)
            sent_e = '😊' if s > 0.1 else ('😟' if s < -0.1 else '😐')
        except (ValueError, TypeError):
            sent_e = '😐'

        f60 = row.get('f60')
        try:
            f60v = float(f60)
            f_str = f'外資60日{"買" if f60v > 0 else "賣"}超' if show_moat else ''
        except (ValueError, TypeError):
            f_str = ''

        wr = _wr_tag(t)

        # MA120 slope warning (declining trend = higher risk)
        try:
            slope = float(row.get('ma120_slope', 0) or 0)
            declining = str(row.get('ma120_declining', '')).lower() in ('true', '1')
            slope_warn = f'  ⚠️MA120下滑{slope:+.1f}%' if declining else ''
        except (ValueError, TypeError):
            slope_warn = ''

        if show_moat:
            details = '  '.join(filter(None, [f_str, sent_e]))
            return (
                f"*{rank}\\. {t} {name}* {ind}\n"
                f"   ${price}  RSI {rsi}  ⭐{score}{wr}{slope_warn}\n"
                f"   {details}"
            )
        else:
            bias  = _fmt('bias', '.1f')
            vol   = _fmt('vol_ratio', '.1f')
            fnet  = row.get('foreign_net')
            try:
                fv = float(fnet)
                fnet_str = f'外資{"買" if fv > 0 else "賣"}超{abs(fv)/1000:.0f}K'
            except (ValueError, TypeError):
                fnet_str = ''
            vol_str = f'量比{vol}x' if vol != 'N/A' else ''
            details = '  '.join(filter(None, [vol_str, fnet_str, sent_e]))
            return (
                f"*{rank}\\. {t} {name}* {ind}\n"
                f"   ${price}  RSI {rsi}  Bias {bias}%  ⭐{score}{wr}{slope_warn}\n"
                f"   {details}"
            )

    # ── Build message ─────────────────────────────────────────────────────────
    lines = [
        f"🚀 *TWS 今日訊號* — {date_label}",
        "",
    ]

    # Mean-reversion section
    if not df_mr.empty:
        lines += [
            f"📈 *均值回歸訊號* ({len(df_mr)} 檔)  _今收買入 → 明開賣出_",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        for rank, (_, row) in enumerate(df_mr.iterrows(), start=1):
            lines.append(_row_line(rank, row, show_moat=False))
        lines += [
            "",
            " ├ 買入: 今日收盤前  ├ 賣出: 明日開盤",
            " └ 停損: 跌破 MA120 立即出場",
            "",
        ]

    # High-value moat section
    if not df_hv.empty:
        lines += [
            f"💎 *高價潛力股 — 技術護城河* ({len(df_hv)} 檔)",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        for rank, (_, row) in enumerate(df_hv.iterrows(), start=1):
            lines.append(_row_line(rank, row, show_moat=True))

            # Add data-driven moat summary line (no external API needed)
            try:
                pe    = row.get("pe_ratio")
                roe   = row.get("roe")
                div   = row.get("dividend_yield")
                f60v  = float(row.get("f60") or 0)
                fz    = float(row.get("f_zscore") or 0)
                parts = []
                if roe not in (None, "") and not (isinstance(roe, float) and pd.isna(roe)):
                    parts.append(f"ROE {float(roe):.1f}%")
                if pe not in (None, "") and not (isinstance(pe, float) and pd.isna(pe)):
                    parts.append(f"PE {float(pe):.1f}")
                if div not in (None, "") and not (isinstance(div, float) and pd.isna(div)):
                    parts.append(f"殖利率 {float(div):.2f}%")
                flow_tag = "外資持續買超" if fz > 1 else ("外資淨流入" if f60v > 0 else "")
                if flow_tag:
                    parts.append(flow_tag)
                if parts:
                    lines.append(f"   _{' | '.join(parts)}_")
            except Exception:
                pass

        lines += [
            "",
            "_持股策略: 長線持有，逢回加碼，跌破 MA120 減碼_",
        ]

    if df_mr.empty and df_hv.empty:
        lines.append("今日無訊號。")

    tool.send_markdown('\n'.join(lines))

    # ── Signal map (one image) ────────────────────────────────────────────────
    _send_signal_map(base_dir, tool, mapping_df, df_trend)


# ---------------------------------------------------------------------------
# Full-market heatmap + trending industry report
# ---------------------------------------------------------------------------

def generate_market_heatmap(price_df: pd.DataFrame, company_df: pd.DataFrame):
    """
    Finviz-style full TWSE market heatmap (~1000 stocks).

    Color : daily % change  — red (down) ← gray (flat) → green (up/漲停)
    Size  : log(trading value in NTD)   — bigger tile = more liquidity
    Group : industry from company_df
    """
    try:
        merged = price_df.merge(
            company_df[['ticker', 'name', 'industry']].rename(columns={'name': 'co_name'}),
            on='ticker', how='left',
        )
        merged['industry'] = merged['industry'].fillna('其他').str.strip()
        # prefer the official company name from mapping; fall back to TWSE short name
        merged['display_name'] = merged['co_name'].where(merged['co_name'].notna(), merged['name'])
        merged['change_pct']   = pd.to_numeric(merged['change_pct'], errors='coerce').fillna(0)
        merged['value']        = pd.to_numeric(merged['value'],      errors='coerce').fillna(0)

        if merged.empty:
            return None

        # Tile size: log-scaled trading value so TSMC doesn't swallow everything
        merged['tile_size'] = np.log1p(merged['value'] / 1_000_000).clip(lower=0.3)

        industries = sorted(merged['industry'].unique().tolist())

        labels  = ['大盤'] + industries + merged['ticker'].tolist()
        parents = ['']    + ['大盤'] * len(industries) + merged['industry'].tolist()
        values  = [0]     + [0] * len(industries)     + merged['tile_size'].tolist()
        # Clamp color to [-10, +10] — limit up/down stocks hit exactly ±10
        colors  = (
            [np.nan] + [np.nan] * len(industries)
            + merged['change_pct'].clip(-10, 10).tolist()
        )

        def tile_text(row):
            arrow = '▲' if row['change_pct'] > 0 else ('▼' if row['change_pct'] < 0 else '─')
            limit = ' 🔥' if row['is_limit_up'] else (' 🧊' if row['is_limit_down'] else '')
            return (
                f"<b>{row['ticker']}</b><br>{row['display_name']}<br>"
                f"{arrow}{row['change_pct']:+.1f}%{limit}"
            )

        def hover_text(row):
            return (
                f"<b>{row['ticker']} {row['display_name']}</b><br>"
                f"產業: {row['industry']}<br>"
                f"收盤: {row['close']:.2f}  {row['change_pct']:+.2f}%<br>"
                f"成交值: {row['value']/1e8:.1f} 億"
            )

        tile_texts  = [''] + industries + [tile_text(r)  for _, r in merged.iterrows()]
        hover_texts = [''] + industries + [hover_text(r) for _, r in merged.iterrows()]

        # Diverging red→gray→green colorscale (cmin=-10, cmax=+10)
        colorscale = [
            [0.00, '#b71c1c'],  # -10% 跌停  deep red
            [0.25, '#ef5350'],  # -5%        red
            [0.43, '#ffcdd2'],  # -2%        light red
            [0.50, '#424242'],  # 0%         dark gray
            [0.57, '#c8e6c9'],  # +2%        light green
            [0.75, '#43a047'],  # +5%        green
            [1.00, '#00e676'],  # +10% 漲停  bright green
        ]

        n_up   = int((merged['change_pct'] > 0).sum())
        n_down = int((merged['change_pct'] < 0).sum())
        n_lu   = int(merged['is_limit_up'].sum())
        n_ld   = int(merged['is_limit_down'].sum())
        date_s = get_last_trading_date().strftime('%Y-%m-%d')
        title  = (
            f'TWSE Market Map {date_s} — '
            f'▲{n_up}  ▼{n_down}  🔥漲停{n_lu}  🧊跌停{n_ld}'
        )

        fig = go.Figure(go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            text=tile_texts,
            customdata=hover_texts,
            textinfo='text',
            hovertemplate='%{customdata}<extra></extra>',
            textfont=dict(size=12, color='white', family='sans-serif'),
            marker=dict(
                colors=colors,
                colorscale=colorscale,
                cmin=-10,
                cmax=10,
                showscale=True,
                colorbar=dict(
                    title=dict(text='% Change', font=dict(color='#ccc', size=11)),
                    thickness=12,
                    tickvals=[-10, -5, 0, 5, 10],
                    ticktext=['-10%', '-5%', '0%', '+5%', '+10%'],
                    tickfont=dict(color='#ccc', size=9),
                    bgcolor='rgba(0,0,0,0)',
                ),
                line=dict(color='#111', width=0.8),
                pad=dict(t=18, l=3, r=3, b=3),
            ),
            root_color='#111111',
            pathbar=dict(visible=False),
        ))

        fig.update_layout(
            title=dict(text=title, font=dict(color='#eee', size=16), x=0.5, xanchor='center'),
            template='plotly_dark',
            paper_bgcolor='#111111',
            # Logical size — exported at 2× scale → effective 4000×2400 px
            width=2000,
            height=1200,
            margin=dict(l=8, r=8, t=52, b=8),
        )

        # scale=2 doubles pixel density: logical 2000×1200 → 4000×2400 PNG
        # Users can pinch-zoom on mobile and see every ticker label clearly.
        return fig.to_image(format='png', scale=2)
    except Exception:
        return None


def generate_sector_zoom(price_df: pd.DataFrame, company_df: pd.DataFrame, sector_name: str):
    """
    Single-sector focused treemap at 1000×600 px.

    Same red/green % change color scheme as generate_market_heatmap, but zoomed
    into one industry so individual stock labels are legible without pinch-zooming.
    Returns PNG bytes or None.
    """
    try:
        merged = price_df.merge(
            company_df[['ticker', 'name', 'industry']].rename(columns={'name': 'co_name'}),
            on='ticker', how='left',
        )
        merged['industry'] = merged['industry'].fillna('其他').str.strip()
        sector = merged[merged['industry'] == sector_name].copy()

        if len(sector) < 2:
            return None

        sector['change_pct']   = pd.to_numeric(sector['change_pct'], errors='coerce').fillna(0)
        sector['value']        = pd.to_numeric(sector['value'],      errors='coerce').fillna(0)
        sector['display_name'] = sector['co_name'].where(sector['co_name'].notna(), sector['name'])
        sector['tile_size']    = np.log1p(sector['value'] / 1_000_000).clip(lower=0.3)

        n_up   = int((sector['change_pct'] > 0).sum())
        n_down = int((sector['change_pct'] < 0).sum())
        avg_ch = sector['change_pct'].mean()

        labels  = [sector_name] + sector['ticker'].tolist()
        parents = ['']          + [sector_name] * len(sector)
        values  = [0]           + sector['tile_size'].tolist()
        colors  = [np.nan]      + sector['change_pct'].clip(-10, 10).tolist()

        def _tile_text(row):
            arrow = '▲' if row['change_pct'] > 0 else ('▼' if row['change_pct'] < 0 else '─')
            limit = ' 🔥' if row['is_limit_up'] else (' 🧊' if row['is_limit_down'] else '')
            return (
                f"<b>{row['ticker']}</b><br>{row['display_name']}<br>"
                f"{arrow}{row['change_pct']:+.1f}%{limit}"
            )

        tile_texts = [f'<b>{sector_name}</b>'] + [_tile_text(r) for _, r in sector.iterrows()]

        colorscale = [
            [0.00, '#b71c1c'], [0.25, '#ef5350'], [0.43, '#ffcdd2'],
            [0.50, '#424242'], [0.57, '#c8e6c9'], [0.75, '#43a047'], [1.00, '#00e676'],
        ]

        date_s = get_last_trading_date().strftime('%Y-%m-%d')
        title  = (
            f'{sector_name}  {date_s}  avg {avg_ch:+.2f}%  '
            f'▲{n_up} ▼{n_down}  ({len(sector)} stocks)'
        )

        fig = go.Figure(go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            text=tile_texts,
            textinfo='text',
            textfont=dict(size=13, color='white', family='sans-serif'),
            marker=dict(
                colors=colors,
                colorscale=colorscale,
                cmin=-10, cmax=10,
                showscale=False,
                line=dict(color='#111', width=0.8),
                pad=dict(t=20, l=3, r=3, b=3),
            ),
            root_color='#111111',
            pathbar=dict(visible=False),
        ))

        fig.update_layout(
            title=dict(text=title, font=dict(color='#eee', size=14), x=0.5, xanchor='center'),
            template='plotly_dark',
            paper_bgcolor='#111111',
            width=1000, height=600,
            margin=dict(l=8, r=8, t=50, b=8),
        )

        return fig.to_image(format='png')
    except Exception:
        return None


def send_sector_zooms(price_df: pd.DataFrame, company_df: pd.DataFrame,
                      tool: TelegramTool, top_n: int = 3):
    """
    Pick the top N sectors by total trading value and send a focused heatmap for each.
    Helps users drill into the sectors driving today's market.
    """
    try:
        merged = price_df.merge(company_df[['ticker', 'industry']], on='ticker', how='left')
        merged['industry'] = merged['industry'].fillna('其他').str.strip()
        merged['value']    = pd.to_numeric(merged['value'], errors='coerce').fillna(0)

        top_sectors = (
            merged.groupby('industry')['value']
            .sum()
            .sort_values(ascending=False)
            .head(top_n)
            .index.tolist()
        )

        for sector in top_sectors:
            img = generate_sector_zoom(price_df, company_df, sector)
            if img:
                tool.send_photo(img, caption=f'🔍 {sector} — 產業細部')
    except Exception:
        pass


def build_industry_trend_text(price_df: pd.DataFrame, company_df: pd.DataFrame) -> str:
    """
    Build a Telegram-ready text summary:
    - Overall market breadth
    - Top 5 / Bottom 5 industries by avg % change
    - 漲停板 list (≥ 9.5% change)
    - 跌停板 list (≤ −9.5% change)
    """
    # price_df already has 'name' (TWSE short name); rename company_df's to avoid _x/_y conflict
    merged = price_df.merge(
        company_df[['ticker', 'name', 'industry']].rename(columns={'name': 'co_name'}),
        on='ticker', how='left',
    )
    merged['industry']   = merged['industry'].fillna('其他')
    merged['change_pct'] = pd.to_numeric(merged['change_pct'], errors='coerce').fillna(0)

    total   = len(merged)
    n_up    = int((merged['change_pct'] > 0).sum())
    n_flat  = int((merged['change_pct'] == 0).sum())
    n_down  = int((merged['change_pct'] < 0).sum())
    avg_mkt = merged['change_pct'].mean()

    # Industry averages
    ind = (
        merged.groupby('industry')['change_pct']
        .agg(avg='mean', count='count', up=lambda x: (x > 0).sum())
        .reset_index()
        .sort_values('avg', ascending=False)
    )
    ind['down'] = ind['count'] - ind['up']

    def _ind_line(row):
        arrow = '▲' if row['avg'] > 0 else '▼'
        return f"{arrow} {row['industry']:<10} {row['avg']:+.2f}%  (▲{int(row['up'])} ▼{int(row['down'])})"

    top5    = '\n'.join(_ind_line(r) for _, r in ind.head(5).iterrows())
    bot5    = '\n'.join(_ind_line(r) for _, r in ind.tail(5).iterrows())

    # Limit up / down
    lu_df = merged[merged['is_limit_up']].sort_values('change_pct', ascending=False)
    ld_df = merged[merged['is_limit_down']].sort_values('change_pct')

    def _ticker_list(df, max_n=15):
        if df.empty:
            return '  (無)'
        # 'name' = TWSE short name from price_df (preserved after merge with rename)
        parts = [f"{r['ticker']} {r['name']} {r['change_pct']:+.1f}%" for _, r in df.head(max_n).iterrows()]
        suffix = f'\n  …及其他 {len(df) - max_n} 檔' if len(df) > max_n else ''
        return '  ' + '\n  '.join(parts) + suffix

    date_s = get_last_trading_date().strftime('%Y-%m-%d')

    lines = [
        f"📊 *TWSE 市場總覽 — {date_s}*",
        f"大盤平均漲跌: {avg_mkt:+.2f}%  "
        f"▲{n_up} ─{n_flat} ▼{n_down}  (共{total}檔)",
        "",
        "🔥 *強勢產業 Top 5:*",
        top5,
        "",
        "❄️ *弱勢產業 Bottom 5:*",
        bot5,
        "",
        f"🚀 *漲停板 ({len(lu_df)} 檔):*",
        _ticker_list(lu_df),
    ]
    if not ld_df.empty:
        lines += ["", f"⬇️ *跌停板 ({len(ld_df)} 檔):*", _ticker_list(ld_df)]

    return '\n'.join(lines)


def build_investment_intel(price_df: pd.DataFrame, company_df: pd.DataFrame,
                           universe_df=None) -> str:
    """
    Build an investment intelligence Telegram message with three sections:

    1. 漲停板 stocks with latest news headline (momentum context)
    2. Near-signal watchlist: price > MA120, RSI 35–50, Bias < -1% (not yet triggered)
    3. Strongest sectors for tomorrow + intra-day follow-through idea

    Returns a Telegram markdown string (empty string if nothing notable).
    """
    lines = []
    date_s = get_last_trading_date().strftime('%Y-%m-%d')

    # ── Merge price with company names ────────────────────────────────────────
    merged = price_df.merge(
        company_df[['ticker', 'name', 'industry']].rename(columns={'name': 'co_name'}),
        on='ticker', how='left',
    )
    merged['change_pct'] = pd.to_numeric(merged['change_pct'], errors='coerce').fillna(0)
    merged['value']      = pd.to_numeric(merged['value'],      errors='coerce').fillna(0)
    merged['industry']   = merged['industry'].fillna('其他').str.strip()

    # ── 1. Limit-up stocks with news ─────────────────────────────────────────
    lu_df = merged[merged['is_limit_up']].sort_values('value', ascending=False).head(8)
    if not lu_df.empty:
        lines.append(f'🔥 *漲停板動能 ({date_s})*')
        for _, r in lu_df.iterrows():
            ticker   = str(r['ticker'])
            display  = str(r.get('co_name') or r.get('name', ticker))
            news     = fetch_google_news_many(ticker, display, days=3, max_items=1)
            headline = news[0] if news else '暫無重大新聞'
            lines.append(f"  *{ticker} {display}*  +{r['change_pct']:.1f}%")
            lines.append(f"  📰 {headline}")
        lines.append('')

    # ── 2. Near-signal watchlist (from universe_snapshot) ────────────────────
    if universe_df is not None and not universe_df.empty:
        u = universe_df.copy()
        u['RSI']       = pd.to_numeric(u.get('RSI'),   errors='coerce')
        u['bias']      = pd.to_numeric(u.get('bias'),  errors='coerce')
        u['price']     = pd.to_numeric(u.get('price'), errors='coerce')
        u['MA120']     = pd.to_numeric(u.get('MA120'), errors='coerce')
        u['is_signal'] = u['is_signal'].astype(str).str.lower().isin(['true', '1', 'yes'])

        near = u[
            (~u['is_signal']) &
            (u['price'] > u['MA120']) &
            (u['RSI'] >= 35) & (u['RSI'] < 50) &
            (u['bias'] < -1.0) & (u['bias'] > -12.0)
        ].sort_values('RSI').head(5)

        if not near.empty:
            near = near.merge(company_df[['ticker', 'name']], on='ticker', how='left')
            lines.append('👀 *明日觀察名單 (接近訊號)*')
            lines.append('_條件: 價>MA120  RSI 35-50  Bias<-1%_')
            for _, r in near.iterrows():
                name_val = str(r.get('name', r['ticker']))
                lines.append(
                    f"  *{r['ticker']} {name_val}*  "
                    f"RSI {r['RSI']:.0f}  Bias {r['bias']:.1f}%"
                )
            lines.append('')

    # ── 3. Momentum sectors & intra-day idea ─────────────────────────────────
    ind_stats = (
        merged.groupby('industry')
        .agg(
            avg_ch=('change_pct', 'mean'),
            total_val=('value', 'sum'),
            n_lu=('is_limit_up', 'sum'),
            n_stocks=('ticker', 'count'),
        )
        .sort_values('avg_ch', ascending=False)
    )

    top3 = ind_stats.head(3)
    if not top3.empty:
        lines.append('🚀 *明日強勢產業展望*')
        for ind_name, r in top3.iterrows():
            lu_tag = f'  🔥{int(r["n_lu"])}漲停' if r['n_lu'] > 0 else ''
            lines.append(
                f"  ▲ *{ind_name}*  avg {r['avg_ch']:+.2f}%  "
                f"成交{r['total_val'] / 1e8:.0f}億{lu_tag}"
            )
        lines.append('')

    # Intra-day idea: strongest sector with limit-ups = best momentum follow-through candidate
    hot = ind_stats[ind_stats['n_lu'] > 0].head(1)
    if not hot.empty:
        hot_name = hot.index[0]
        lines.append('💡 *當沖參考*')
        lines.append(
            f'  {hot_name} 今日多檔漲停，明日開盤留意跳空高開後的'
            f'第一根回測支撐 (前收盤±0.5%) 為潛在進場點'
        )
        lines.append('  _風控: 以前日收盤價為停損基準，破則出場_')

    return '\n'.join(lines)


def send_market_overview(base_dir: str):
    """
    Fetch full TWSE market data → send industry trend summary + full heatmap to Telegram.
    Called once per day before the individual signal stock reports.
    """
    load_dotenv(os.path.join(base_dir, '.env'))
    tool = TelegramTool(os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID'))

    mapping_file = os.path.join(base_dir, 'data', 'company', 'company_mapping.csv')
    if not os.path.exists(mapping_file):
        return

    company_df = pd.read_csv(mapping_file, dtype={'ticker': str})
    date_str   = get_last_trading_date().strftime('%Y%m%d')

    if not is_trading_day():
        tool.send_markdown(
            f"📅 今日非交易日，以最近交易日 "
            f"{get_last_trading_date().strftime('%Y-%m-%d')} 數據為準"
        )

    # Fetch full market prices
    price_df = fetch_twse_all_prices(date_str)
    if price_df.empty:
        tool.send_markdown("⚠️ 無法取得今日市場行情，TWSE API 可能尚未更新。")
        return

    # 1. Industry trend text
    try:
        trend_text = build_industry_trend_text(price_df, company_df)
        tool.send_markdown(trend_text)
    except Exception:
        pass

    # 2. Full-market heatmap — sent as document so Telegram keeps full resolution
    #    Users tap the file → pinch-zoom to read any sector clearly
    try:
        heatmap_bytes = generate_market_heatmap(price_df, company_df)
        if heatmap_bytes:
            n_lu  = int(price_df['is_limit_up'].sum())
            n_ld  = int(price_df['is_limit_down'].sum())
            date_s = get_last_trading_date().strftime('%Y-%m-%d')
            tool.send_document(
                heatmap_bytes,
                filename=f'twse_market_map_{date_s}.png',
                caption=(
                    f'📊 TWSE Market Map {date_s}\n'
                    f'{len(price_df)} stocks | 🔥漲停{n_lu} | 🧊跌停{n_ld}\n'
                    '_點擊開啟 → 放大查看各產業細節_'
                ),
            )
    except Exception:
        pass

    # 3. Sector zoom charts — top 3 sectors by trading value, sent as photos
    try:
        send_sector_zooms(price_df, company_df, tool, top_n=3)
    except Exception:
        pass

    # 4. Investment intelligence — limit-up news, near-signal watchlist, intra-day idea
    try:
        universe_file = os.path.join(base_dir, 'data', 'company', 'universe_snapshot.csv')
        universe_df   = (
            pd.read_csv(universe_file, dtype={'ticker': str})
            if os.path.exists(universe_file) else None
        )
        intel_text = build_investment_intel(price_df, company_df, universe_df)
        if intel_text.strip():
            tool.send_markdown(intel_text)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Market Oracle — morning prediction + EOD result messages
# ---------------------------------------------------------------------------

def send_market_prediction(base_dir: str) -> None:
    """
    Send today's TAIEX bull/bear prediction to Telegram.
    Called at ~08:30 TST in run_tws_pipeline Step 0.
    """
    import json as _json
    from datetime import datetime as _dt
    from tws.index_tracker import _load_history, oracle_stats

    load_dotenv(os.path.join(base_dir, ".env"))
    tool     = TelegramTool(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))
    today    = _dt.now().strftime("%Y-%m-%d")
    history  = _load_history(base_dir)

    today_rows = history[history["date"] == today] if not history.empty else pd.DataFrame()
    if today_rows.empty:
        tool.send_markdown(f"🔮 *台股大盤 Oracle — {today}*\n\n_今日預測尚未生成。_")
        return

    row        = today_rows.iloc[-1]
    direction  = row.get("direction", "?")
    conf       = row.get("confidence_pct", 0)
    dir_emoji  = "🟢" if direction == "Bull" else "🔴"
    dir_label  = "多方 (Bull)" if direction == "Bull" else "空方 (Bear)"

    # Factor breakdown
    factor_lines = []
    _factor_labels = {
        "spx_overnight":  "SPX夜盤",
        "taiex_momentum": "台股動能",
        "vix_fear":       "VIX恐慌",
        "signal_count":   "超跌訊號",
        "tw_win_rate":    "近期勝率",
    }
    _factor_units = {
        "spx_overnight": "%", "taiex_momentum": "%",
        "vix_fear": "", "signal_count": "檔", "tw_win_rate": "%",
    }
    try:
        factors = _json.loads(str(row.get("factors_json") or "{}"))
        for fname, finfo in factors.items():
            val      = finfo.get("value")
            is_bull  = finfo.get("bull", False)
            unit     = _factor_units.get(fname, "")
            label    = _factor_labels.get(fname, fname)
            vote     = "✅ (看多)" if is_bull else "❌ (看空)"
            val_str  = f"{val}{unit}" if val is not None else "N/A"
            factor_lines.append(f"  {label}: {val_str} {vote}")
    except Exception:
        pass

    # Oracle stats
    stats = oracle_stats(base_dir)
    stats_line = ""
    if stats["total"] > 0:
        stats_line = (
            f"\n📈 *歷史戰績*  勝率 {stats['win_rate_pct']:.0f}%  "
            f"累計 {stats['cumulative_score']:+,.0f}分  "
            f"({stats['wins']}勝{stats['losses']}負)"
        )

    lines = [
        f"🔮 *台股大盤預測 — {today}*",
        "",
        f"方向: {dir_emoji} *{dir_label}*  信心: {conf:.0f}%",
        "",
        "📊 *因子分析*",
    ] + factor_lines + [stats_line]

    tool.send_markdown("\n".join(lines))


def send_market_result(base_dir: str) -> None:
    """
    Send today's TAIEX Oracle result to Telegram after resolution.
    Called at ~14:05 TST after resolve_today_prediction().
    """
    from datetime import datetime as _dt
    from tws.index_tracker import _load_history, oracle_stats

    load_dotenv(os.path.join(base_dir, ".env"))
    tool     = TelegramTool(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))
    today    = _dt.now().strftime("%Y-%m-%d")
    history  = _load_history(base_dir)

    if history.empty:
        return
    today_rows = history[(history["date"] == today) & (history["status"] == "resolved")]
    if today_rows.empty:
        return

    row        = today_rows.iloc[-1]
    direction  = row.get("direction", "?")
    dir_emoji  = "🟢" if direction == "Bull" else "🔴"
    dir_label  = "多方" if direction == "Bull" else "空方"
    is_correct = str(row.get("is_correct", "")).lower() in ("true", "1")
    outcome    = "✅ 正確" if is_correct else "❌ 錯誤"
    change_pts = float(row.get("taiex_change_pts") or 0)
    score_pts  = float(row.get("score_pts") or 0)

    stats = oracle_stats(base_dir)
    streak_line = f"  連{'勝' if is_correct else '敗'}: {stats['streak']}" if stats["streak"] > 1 else ""

    lines = [
        f"📊 *今日大盤結算 — {today}*",
        "",
        f"預測: {dir_emoji}{dir_label}  實際: {outcome}",
        f"大盤變動: *{change_pts:+.0f}點*  得分: *{score_pts:+.0f}分*",
        "",
        "🏆 *累計戰績*",
        f"  勝率: {stats['win_rate_pct']:.0f}%  ({stats['wins']}勝{stats['losses']}負)",
        f"  累計分數: {stats['cumulative_score']:+,.0f}分",
    ]
    if streak_line:
        lines.append(streak_line)

    tool.send_markdown("\n".join(lines))


# ---------------------------------------------------------------------------
# Individual subscriber DMs (Telegram subscribers, not the channel)
# ---------------------------------------------------------------------------

def send_to_chat(chat_id: str, text: str) -> bool:
    """
    Send a Markdown message to a single Telegram chat ID.
    Used for individual subscriber DMs (morning prediction + result).
    Returns True on success.
    """
    import requests as _req
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_id:
        return False
    try:
        r = _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=8,
        )
        return r.ok
    except Exception:
        return False


def broadcast_to_subscribers(base_dir: str, msg_type: str) -> int:
    """
    Broadcast Oracle messages to all active Telegram subscribers.
    msg_type: "morning" | "result"
    Returns count of DMs sent.
    """
    import sys as _sys
    from pathlib import Path as _Path
    _root = str(_Path(base_dir))
    if _root not in _sys.path:
        _sys.path.insert(0, _root)

    from api.db import Subscriber, SessionLocal
    from tws.index_tracker import _load_history, oracle_stats

    from datetime import datetime as _dt
    import json as _json

    today   = _dt.now().strftime("%Y-%m-%d")
    history = _load_history(base_dir)
    stats   = oracle_stats(base_dir)

    if history.empty:
        return 0

    if msg_type == "morning":
        rows = history[history["date"] == today]
        if rows.empty:
            return 0
        row       = rows.iloc[-1]
        direction = row.get("direction", "?")
        conf      = float(row.get("confidence_pct") or 0)
        dir_emoji = "🟢" if direction == "Bull" else "🔴"
        dir_label = "多方 Bull" if direction == "Bull" else "空方 Bear"
        text = (
            f"🔮 *Oracle 今日預測 — {today}*\n\n"
            f"{dir_emoji} *{dir_label}*  信心 {conf:.0f}%\n\n"
            f"下注截止 09:00 TST\n"
            f"累計勝率 {stats.get('win_rate_pct', 0):.0f}%  積分 {stats.get('cumulative_score', 0):+,.0f}"
        )

    elif msg_type == "result":
        rows = history[(history["date"] == today) & (history["status"] == "resolved")]
        if rows.empty:
            return 0
        row        = rows.iloc[-1]
        direction  = row.get("direction", "?")
        is_correct = str(row.get("is_correct", "")).lower() in ("true", "1")
        change_pts = float(row.get("taiex_change_pts") or 0)
        score_pts  = float(row.get("score_pts") or 0)
        outcome    = "✅ 命中" if is_correct else "❌ 未命中"
        streak     = stats.get("streak", 0)
        streak_txt = f"  🔥 {streak}連勝" if is_correct and streak >= 2 else ""
        text = (
            f"📊 *Oracle 結算 — {today}*\n\n"
            f"{outcome}\n"
            f"大盤 {change_pts:+.0f}pts  積分 {score_pts:+.0f}{streak_txt}\n\n"
            f"累計勝率 {stats.get('win_rate_pct', 0):.0f}%  "
            f"積分 {stats.get('cumulative_score', 0):+,.0f}"
        )
    else:
        return 0

    db   = SessionLocal()
    sent = 0
    try:
        subs = db.query(Subscriber).filter(Subscriber.active == True).all()
        for sub in subs:
            if send_to_chat(sub.telegram_id, text):
                sent += 1
    finally:
        db.close()

    return sent