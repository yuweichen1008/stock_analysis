/**
 * Chart reading and control tools.
 * Security: all user inputs go through security.js validators before CDP evaluation.
 */

import { z } from 'zod';
import { evaluate, evaluateAsync, getChartApi } from '../connection.js';
import { safeString, requireFinite, requireSymbol, requireTimeframe, requireChartType, checkRateLimit, audit } from '../security.js';

function wrap(tool, fn) {
  return async (params) => {
    checkRateLimit(tool);
    try {
      const result = await fn(params);
      audit(tool, params, 'ok');
      return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
    } catch (err) {
      audit(tool, params, `error: ${err.message}`);
      return { content: [{ type: 'text', text: JSON.stringify({ success: false, error: err.message }) }], isError: true };
    }
  };
}

export function registerChartTools(server) {
  // ── Get current chart state ───────────────────────────────────────────────
  server.tool('chart_get_state',
    'Get current chart state (symbol, timeframe, chart type, all indicators)',
    {},
    wrap('chart_get_state', async () => {
      const chart = await getChartApi();
      const state = await evaluateAsync(`
        (async () => {
          const chart = ${chart};
          const symbol    = chart.symbol();
          const timeframe = chart.resolution();
          const studies   = chart.getAllStudies().map(s => ({
            id: s.id, name: s.name, entityId: s.entityId
          }));
          return { symbol, timeframe, studies };
        })()
      `);
      return state;
    })
  );

  // ── Set symbol ────────────────────────────────────────────────────────────
  server.tool('chart_set_symbol',
    'Change the chart symbol/ticker',
    { symbol: z.string().describe('Ticker symbol (e.g. AAPL, BTCUSD, NASDAQ:TSLA)') },
    wrap('chart_set_symbol', async ({ symbol }) => {
      const safe = requireSymbol(symbol);  // allowlist validation
      const chart = await getChartApi();
      await evaluateAsync(`${chart}.setSymbol(${safeString(safe)}, {})`);
      return { success: true, symbol: safe };
    })
  );

  // ── Set timeframe ─────────────────────────────────────────────────────────
  server.tool('chart_set_timeframe',
    'Change the chart timeframe/resolution',
    { timeframe: z.string().describe('Timeframe: 1 5 15 30 60 240 D W M') },
    wrap('chart_set_timeframe', async ({ timeframe }) => {
      const safe = requireTimeframe(timeframe);  // allowlist validation
      const chart = await getChartApi();
      await evaluateAsync(`${chart}.setResolution(${safeString(safe)}, {})`);
      return { success: true, timeframe: safe };
    })
  );

  // ── Set chart type ────────────────────────────────────────────────────────
  server.tool('chart_set_type',
    'Change chart type (Candles, Line, Area, HeikinAshi, etc.)',
    { chart_type: z.string().describe('Type name or number 0-9') },
    wrap('chart_set_type', async ({ chart_type }) => {
      const typeNum = requireChartType(chart_type);  // validated numeric
      const chart = await getChartApi();
      await evaluate(`${chart}.setChartType(${typeNum})`);
      return { success: true, chart_type: typeNum };
    })
  );

  // ── Manage indicator ──────────────────────────────────────────────────────
  server.tool('chart_manage_indicator',
    'Add or remove a technical indicator on the chart',
    {
      action:    z.enum(['add', 'remove']).describe('add or remove'),
      indicator: z.string().max(100).describe('Full indicator name, e.g. "Relative Strength Index"'),
      entity_id: z.string().optional().describe('Entity ID for remove (from chart_get_state)'),
      inputs:    z.record(z.union([z.number(), z.string(), z.boolean()])).optional()
                   .describe('Input overrides as an object, e.g. {"length": 14}'),
    },
    wrap('chart_manage_indicator', async ({ action, indicator, entity_id, inputs }) => {
      const chart = await getChartApi();

      if (action === 'remove') {
        if (!entity_id) throw new Error('entity_id required for remove');
        // entity_id goes through safeString — never raw interpolation
        await evaluate(`${chart}.removeEntity(${safeString(entity_id)})`);
        return { success: true, action: 'remove', entity_id };
      }

      // validate inputs object: all values must be finite numbers, strings, or booleans
      const safeInputs = {};
      for (const [k, v] of Object.entries(inputs || {})) {
        if (typeof v === 'number' && !Number.isFinite(v)) {
          throw new Error(`Input "${k}" is not a finite number`);
        }
        safeInputs[k] = v;
      }

      const inputsJson = JSON.stringify(safeInputs);
      await evaluateAsync(
        `${chart}.createStudy(${safeString(indicator)}, false, false, ${inputsJson})`
      );
      return { success: true, action: 'add', indicator };
    })
  );

  // ── Get visible range ─────────────────────────────────────────────────────
  server.tool('chart_get_visible_range',
    'Get the visible date range (unix timestamps)',
    {},
    wrap('chart_get_visible_range', async () => {
      const chart = await getChartApi();
      return await evaluate(`
        (() => {
          const r = ${chart}.getVisibleRange();
          return { from: r.from, to: r.to };
        })()
      `);
    })
  );

  // ── Scroll to date ────────────────────────────────────────────────────────
  server.tool('chart_scroll_to_date',
    'Jump the chart to a specific date',
    { date: z.string().describe('ISO date string (2024-01-15) or unix timestamp') },
    wrap('chart_scroll_to_date', async ({ date }) => {
      // Convert to number — never interpolate the raw string
      const ts = requireFinite(
        isNaN(Number(date)) ? Math.floor(new Date(date).getTime() / 1000) : Number(date),
        'date timestamp'
      );
      const chart = await getChartApi();
      await evaluate(`${chart}.setVisibleRange({ from: ${ts - 86400 * 30}, to: ${ts} })`);
      return { success: true, timestamp: ts };
    })
  );
}
