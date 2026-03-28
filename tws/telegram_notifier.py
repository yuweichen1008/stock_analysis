import os
import io
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go
from tws.models import StockAI
from tws.utils import TelegramTool, fetch_twse_all_prices, get_last_trading_date, is_trading_day
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


def clean_display(val, is_pct=False):
    if val is None or str(val) == "N/A" or pd.isna(val): return "N/A"
    try:
        f = float(val)
        if is_pct: f *= 100
        return f"{f:.2f}" + ("%" if is_pct else "")
    except: return "N/A"

def send_stock_report(base_dir):
    load_dotenv(os.path.join(base_dir, ".env"))
    mapping_file = os.path.join(base_dir, "data", "company", "company_mapping.csv")
    trending_file = os.path.join(base_dir, "current_trending.csv")
    
    mapping_df = pd.read_csv(mapping_file, dtype={'ticker': str})
    
    # 優先顯示今日熱門，若無則顯示 ROE 最強的前 5 檔
    if os.path.exists(trending_file):
        tickers = pd.read_csv(trending_file, dtype={'ticker': str})['ticker'].head(10).tolist()
    else:
        tickers = mapping_df[mapping_df['roe'] != 'N/A'].sort_values('roe', ascending=False)['ticker'].head(5).tolist()

    mapping = mapping_df.set_index('ticker').to_dict('index')
    tool = TelegramTool(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))
    report = f"🚀 **台股 AI 深度分析報告**\n"
    report += "--------------------------------\n"

    # Send the header first, then one block per stock
    tool.send_markdown(report)

    for t in tickers:
        info = mapping.get(t, {})

        # Fetch OHLCV (need full bar data for candlestick + AI model)
        ohlcv = None
        curr_p, pred_p = "N/A", "N/A"
        try:
            ohlcv = yf.download(f"{t}.TW", period="60d", progress=False)
            hist = ohlcv[['Close']]
            curr_p, pred_p = StockAI.predict_target(hist)
        except Exception:
            pass

        # Signal colour
        if curr_p != "N/A" and pred_p != "N/A":
            color = "🔴 (上漲預期)" if pred_p > curr_p else "🟢 (下跌預期)"
            price_line = f"${curr_p:.2f} | 🔮 目標: ${pred_p:.2f}"
        else:
            color = "⚪ (數據更新中)"
            price_line = "N/A"

        stock_report = (
            f"🏢 **{info.get('name', '未知')}** ({t})\n"
            f"📂 產業: {info.get('industry', '未知')}\n"
            f"📊 **財務體質**\n"
            f" ├ ROE: {clean_display(info.get('roe'), True)} | 負債比: {clean_display(info.get('debt_to_equity'))}\n"
            f" └ 殖利率: {clean_display(info.get('dividend_yield'), True)} | PE: {clean_display(info.get('pe_ratio'))}\n"
            f"💡 **市場評價**\n"
            f" ├ 建議: {str(info.get('recommendation', 'N/A')).upper()}\n"
            f" └ 分析師目標價: ${clean_display(info.get('target_price'))}\n"
            f"🔮 **AI 預測 (Ledoit-Wolf)** {color}\n"
            f" └ 目前現價: {price_line}\n"
        )
        tool.send_markdown(stock_report)

        # Candlestick chart
        if ohlcv is not None and not ohlcv.empty:
            # For MA120 overlay we need a longer window — extend to 6 months if available
            try:
                ohlcv_long = yf.download(f"{t}.TW", period="6mo", progress=False)
            except Exception:
                ohlcv_long = ohlcv
            target_p = pred_p if pred_p != "N/A" else None
            chart_bytes = generate_candlestick_chart(t, ohlcv_long, pred_price=target_p)
            if chart_bytes:
                tool.send_photo(chart_bytes, caption=f"{t} — {info.get('name', '')} | Bias & AI target")

    # Finviz-style industry treemap — uses full universe snapshot when available
    try:
        universe_file = os.path.join(base_dir, "data", "company", "universe_snapshot.csv")
        df_trend_map  = pd.read_csv(trending_file, dtype={'ticker': str}) if os.path.exists(trending_file) else pd.DataFrame()
        universe_df   = pd.read_csv(universe_file, dtype={'ticker': str}) if os.path.exists(universe_file) else None

        if not df_trend_map.empty or (universe_df is not None and not universe_df.empty):
            heatmap_bytes = generate_industry_heatmap(df_trend_map, mapping_df, universe_df=universe_df)
            if heatmap_bytes:
                n_signal = len(df_trend_map)
                n_total  = len(universe_df) if universe_df is not None else n_signal
                tool.send_photo(
                    heatmap_bytes,
                    caption=f'📊 TWS Signal Map — {n_signal} signal / {n_total} tracked',
                )
    except Exception:
        pass


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
            textfont=dict(size=10, color='white', family='sans-serif'),
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
            title=dict(text=title, font=dict(color='#eee', size=13), x=0.5, xanchor='center'),
            template='plotly_dark',
            paper_bgcolor='#111111',
            width=1400,
            height=900,
            margin=dict(l=8, r=8, t=48, b=8),
        )

        return fig.to_image(format='png')
    except Exception:
        return None


def build_industry_trend_text(price_df: pd.DataFrame, company_df: pd.DataFrame) -> str:
    """
    Build a Telegram-ready text summary:
    - Overall market breadth
    - Top 5 / Bottom 5 industries by avg % change
    - 漲停板 list (≥ 9.5% change)
    - 跌停板 list (≤ −9.5% change)
    """
    merged = price_df.merge(
        company_df[['ticker', 'name', 'industry']],
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
        parts = [f"{r['ticker']} {r['name']} {r['change_pct']:+.1f}%" for _, r in df.head(max_n).iterrows()]
        suffix = f'\n  …及其他 {len(df)-max_n} 檔' if len(df) > max_n else ''
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

    # 2. Full-market heatmap
    try:
        heatmap_bytes = generate_market_heatmap(price_df, company_df)
        if heatmap_bytes:
            n_lu = int(price_df['is_limit_up'].sum())
            tool.send_photo(
                heatmap_bytes,
                caption=f'📊 TWSE Market Map — {len(price_df)} stocks, 🔥{n_lu} 漲停',
            )
    except Exception:
        pass