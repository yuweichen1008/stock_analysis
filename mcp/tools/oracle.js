/**
 * Oracle-specific MCP tools — reads from Oracle's own FastAPI backend.
 *
 * These tools do NOT use CDP at all: they call the Oracle API directly,
 * so they work even when TradingView Desktop is not running.
 *
 * Available tools:
 *   oracle_options_screener   — latest RSI + PCR + IV Rank signals
 *   oracle_options_overview   — VIX, market PCR, signal breadth
 *   oracle_weekly_signals     — weekly ±5% contrarian signals
 *   oracle_news_feed          — news + PCR timeline
 *   oracle_signal_search      — search TW/US signals by ticker
 *   oracle_backtest_results   — run options strategy backtest
 */

import { z } from 'zod';
import { requireSymbol, checkRateLimit, audit } from '../security.js';

const API_BASE = process.env.ORACLE_API_BASE || 'http://localhost:8000';

async function apiGet(path) {
  const url = `${API_BASE}${path}`;
  const resp = await fetch(url, { signal: AbortSignal.timeout(10_000) });
  if (!resp.ok) throw new Error(`Oracle API ${path} → HTTP ${resp.status}`);
  return resp.json();
}

function ok(data) {
  return { content: [{ type: 'text', text: JSON.stringify(data, null, 2) }] };
}
function err(msg) {
  return { content: [{ type: 'text', text: JSON.stringify({ success: false, error: msg }) }], isError: true };
}

function wrap(tool, fn) {
  return async (params) => {
    checkRateLimit(tool);
    try {
      const result = await fn(params);
      audit(tool, params, 'ok');
      return ok(result);
    } catch (e) {
      audit(tool, params, `error: ${e.message}`);
      return err(e.message);
    }
  };
}

export function registerOracleTools(server) {

  // ── Options screener ──────────────────────────────────────────────────────
  server.tool('oracle_options_screener',
    'Get latest US options signals — RSI + PCR + IV Rank scored 0-10. ' +
    'Signals: buy_signal (RSI<30 + fear PCR), sell_signal (RSI>70 + greed PCR), unusual_activity (vol/OI>3×).',
    {
      signal_type: z.enum(['buy_signal', 'sell_signal', 'unusual_activity', '']).optional()
                     .default('').describe('Filter by signal type (leave empty for all)'),
      rsi_zone:    z.enum(['oversold', 'overbought', 'neutral', '']).optional()
                     .default('').describe('Filter by RSI zone'),
      limit:       z.number().int().min(1).max(50).default(10).describe('Number of signals to return'),
    },
    wrap('oracle_options_screener', async ({ signal_type, rsi_zone, limit }) => {
      const qs = new URLSearchParams({
        signal_only: 'true',
        limit: String(limit),
        ...(signal_type ? { signal_type } : {}),
        ...(rsi_zone    ? { rsi_zone }    : {}),
      });
      return apiGet(`/api/options/screener?${qs}`);
    })
  );

  // ── Options overview ──────────────────────────────────────────────────────
  server.tool('oracle_options_overview',
    'Get market-wide options overview: VIX, average PCR, buy/sell/unusual signal counts, top 3 signals.',
    {},
    wrap('oracle_options_overview', async () => apiGet('/api/options/overview'))
  );

  // ── Options history for one ticker ────────────────────────────────────────
  server.tool('oracle_options_history',
    'Get 30-day options signal history for one ticker (RSI, PCR, IV Rank over time).',
    { ticker: z.string().describe('US stock ticker, e.g. AAPL') },
    wrap('oracle_options_history', async ({ ticker }) => {
      const safe = requireSymbol(ticker);
      return apiGet(`/api/options/screener/${encodeURIComponent(safe)}/history`);
    })
  );

  // ── Weekly contrarian signals ─────────────────────────────────────────────
  server.tool('oracle_weekly_signals',
    'Get this week\'s US contrarian signals — stocks up ≥5% (SELL) or down ≥5% (BUY) with PCR context.',
    {
      signal_only: z.boolean().default(true).describe('Only return signal tickers'),
      limit:       z.number().int().min(1).max(100).default(20),
    },
    wrap('oracle_weekly_signals', async ({ signal_only, limit }) => {
      return apiGet(`/api/weekly/signals?signal_only=${signal_only}&limit=${limit}`);
    })
  );

  // ── News feed ─────────────────────────────────────────────────────────────
  server.tool('oracle_news_feed',
    'Get latest US/TW news with PCR sentiment and VADER scores.',
    {
      market: z.enum(['all', 'US', 'TW', 'MARKET']).default('US'),
      hours:  z.number().int().min(1).max(24).default(12),
      limit:  z.number().int().min(1).max(50).default(10),
    },
    wrap('oracle_news_feed', async ({ market, hours, limit }) => {
      return apiGet(`/api/news/feed?market=${market}&hours=${hours}&limit=${limit}`);
    })
  );

  // ── Signal search ─────────────────────────────────────────────────────────
  server.tool('oracle_signal_search',
    'Search TW and US signal stocks by ticker or company name.',
    {
      query:  z.string().min(1).max(20).describe('Ticker or company name fragment'),
      market: z.enum(['US', 'TW']).default('US'),
    },
    wrap('oracle_signal_search', async ({ query, market }) => {
      return apiGet(`/api/signals/search?q=${encodeURIComponent(query)}&market=${market}`);
    })
  );

  // ── Backtest results ──────────────────────────────────────────────────────
  server.tool('oracle_backtest_results',
    'Run RSI+PCR strategy backtest against historical WeeklySignal data. ' +
    'Returns win rate, avg return, and Sharpe ratio per signal type.',
    {},
    wrap('oracle_backtest_results', async () => {
      // Spawn the backtester as a subprocess and return its JSON output
      const { execFile } = await import('child_process');
      const { promisify } = await import('util');
      const exec = promisify(execFile);

      const projectRoot = new URL('../../', import.meta.url).pathname;
      const { stdout } = await exec(
        'python3',
        ['options_backtester.py', '--json'],
        { cwd: projectRoot, timeout: 30_000 }
      );
      return JSON.parse(stdout);
    })
  );

  // ── Oracle daily prediction ───────────────────────────────────────────────
  server.tool('oracle_prediction',
    'Get today\'s TAIEX Oracle prediction (Bull/Bear) with confidence, streak, and win rate.',
    {},
    wrap('oracle_prediction', async () => {
      const [today, stats] = await Promise.all([
        apiGet('/api/oracle/today'),
        apiGet('/api/oracle/stats'),
      ]);
      return { today, stats };
    })
  );
}
