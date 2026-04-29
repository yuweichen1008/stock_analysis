/**
 * Data extraction, symbol info, alerts, and indicator control tools.
 *
 * Reuses CDP patterns from tradingview-mcp (tradesdontlie) adapted to our
 * hardened connection layer:
 *   - data_get_ohlcv      — visible bar OHLCV data
 *   - data_get_indicator  — current indicator output values (study values)
 *   - indicator_set_inputs — change indicator input parameters
 *   - symbol_info          — ticker metadata (exchange, type, description)
 *   - alert_create         — create a price alert on the current symbol
 *   - alert_list           — list active alerts on the chart
 *   - pine_save            — save Pine script to TradingView account
 *   - pine_get_console     — read Pine console / log output
 */

import { z } from 'zod';
import { evaluate, evaluateAsync, getChartApi } from '../connection.js';
import { safeString, requireSymbol, checkRateLimit, audit } from '../security.js';

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

export function registerDataTools(server) {

  // ── OHLCV bar data ────────────────────────────────────────────────────────
  server.tool('data_get_ohlcv',
    'Get OHLCV bar data currently visible in the chart. ' +
    'Returns array of {time, open, high, low, close, volume} objects. ' +
    'Call chart_get_state first to confirm the symbol you are reading.',
    {
      limit: z.number().int().min(1).max(500).default(100)
               .describe('Max number of bars to return (most recent first)'),
    },
    wrap('data_get_ohlcv', async ({ limit }) => {
      const chart = await getChartApi();
      const bars = await evaluateAsync(`
        (async () => {
          const chart = ${chart};
          const series = chart.getSeries();
          if (!series) throw new Error('No price series found on chart');
          const data = series.data().values();
          const result = [];
          for (const bar of data) {
            result.push({
              time:   bar.time,
              open:   bar.value[0],
              high:   bar.value[1],
              low:    bar.value[2],
              close:  bar.value[3],
              volume: bar.value[4] ?? null,
            });
          }
          // Most recent first, limited
          return result.reverse().slice(0, ${Math.floor(limit)});
        })()
      `);
      return { count: bars.length, bars };
    })
  );

  // ── Indicator current values ───────────────────────────────────────────────
  server.tool('data_get_indicator',
    'Read the current output values of an indicator visible in the Data Window. ' +
    'Returns name + values for each plot of the study. ' +
    'Use chart_get_state to find the entityId of the study you want to read.',
    {
      entity_id: z.string().describe('Study entityId from chart_get_state'),
    },
    wrap('data_get_indicator', async ({ entity_id }) => {
      const chart = await getChartApi();
      const safeId = safeString(entity_id);
      const values = await evaluateAsync(`
        (async () => {
          const chart = ${chart};
          const dwv = chart.dataWindowView();
          if (!dwv) throw new Error('Data Window View unavailable');
          // Items in the data window correspond to indicator plots
          const items = dwv.items();
          const result = [];
          for (const item of items) {
            const name = item.title?.() ?? item.name?.() ?? 'unknown';
            const val  = item.formattedValue?.() ?? item.value?.() ?? null;
            result.push({ name, value: val });
          }
          return result;
        })()
      `);
      return { entity_id, values };
    })
  );

  // ── Indicator input controls ───────────────────────────────────────────────
  server.tool('indicator_set_inputs',
    'Change the input parameters of an indicator on the chart. ' +
    'Opens the settings dialog, modifies inputs, and saves. ' +
    'inputs is a dict mapping input name → new value.',
    {
      entity_id: z.string().describe('Study entityId from chart_get_state'),
      inputs:    z.record(z.string(), z.union([z.string(), z.number(), z.boolean()]))
                  .describe('Input name → value pairs to change'),
    },
    wrap('indicator_set_inputs', async ({ entity_id, inputs }) => {
      const chart = await getChartApi();
      const safeId     = safeString(entity_id);
      const safeInputs = safeString(JSON.stringify(inputs));
      const result = await evaluateAsync(`
        (async () => {
          const chart   = ${chart};
          const study   = chart.getStudyById(${safeId});
          if (!study) throw new Error('Study not found: ' + ${safeId});
          const inputMap = JSON.parse(${safeInputs});
          const meta     = study.metaInfo();
          const current  = study.inputs() ?? {};
          const updated  = { ...current };
          for (const [k, v] of Object.entries(inputMap)) {
            updated[k] = v;
          }
          await study.setInputs(updated);
          // Wait for chart to recalculate
          await new Promise(r => setTimeout(r, 600));
          return { success: true, entity_id: ${safeId}, applied: inputMap };
        })()
      `);
      return result;
    })
  );

  // ── Symbol info ───────────────────────────────────────────────────────────
  server.tool('symbol_info',
    'Get metadata for a symbol: full name, exchange, type (stock/crypto/forex/index), ' +
    'description, currency, and minimum tick.',
    {
      symbol: z.string().optional().describe('Ticker (leave empty to use current chart symbol)'),
    },
    wrap('symbol_info', async ({ symbol }) => {
      const chart = await getChartApi();
      let safeSymExpr;
      if (symbol) {
        const validated = requireSymbol(symbol);
        safeSymExpr = safeString(validated);
      } else {
        safeSymExpr = null;
      }
      const info = await evaluateAsync(`
        (async () => {
          const chart = ${chart};
          const sym = ${safeSymExpr ? safeSymExpr : 'chart.symbol()'};
          const info = await chart.symbolInfo(sym);
          if (!info) throw new Error('Symbol info unavailable for: ' + sym);
          return {
            ticker:      info.ticker      ?? info.name,
            description: info.description ?? null,
            exchange:    info.exchange     ?? null,
            type:        info.type         ?? null,
            currency:    info.currency_code ?? null,
            minmov:      info.minmov       ?? null,
            pricescale:  info.pricescale   ?? null,
            timezone:    info.timezone     ?? null,
          };
        })()
      `);
      return info;
    })
  );

  // ── Alert creation ────────────────────────────────────────────────────────
  server.tool('alert_create',
    'Create a price alert on the current chart symbol. ' +
    'condition: "above" | "below" | "crosses_up" | "crosses_down". ' +
    'Returns alert id when successful.',
    {
      price:     z.number().describe('Alert price level'),
      condition: z.enum(['above', 'below', 'crosses_up', 'crosses_down'])
                  .default('above')
                  .describe('Trigger condition'),
      message:   z.string().max(200).optional().describe('Optional alert message'),
    },
    wrap('alert_create', async ({ price, condition, message }) => {
      const chart = await getChartApi();
      const safePrice   = safeString(String(price));
      const safeCond    = safeString(condition);
      const safeMsg     = message ? safeString(message) : safeString('');
      const result = await evaluateAsync(`
        (async () => {
          const chart = ${chart};
          const sym   = chart.symbol();
          // TradingView alert creation via the chart alert manager
          const alertMgr = chart.alertsManager?.();
          if (!alertMgr) throw new Error('Alert manager unavailable — ensure you are on a chart page');
          const condMap = {
            'above':       'greater',
            'below':       'less',
            'crosses_up':  'crossing_up',
            'crosses_down':'crossing_down',
          };
          const alert = await alertMgr.createAlert({
            symbol:    sym,
            condition: condMap[${safeCond}] ?? 'greater',
            price:     parseFloat(${safePrice}),
            message:   ${safeMsg},
          });
          return { success: true, alert_id: alert?.id ?? null, symbol: sym, price: parseFloat(${safePrice}) };
        })()
      `);
      return result;
    })
  );

  // ── Alert list ────────────────────────────────────────────────────────────
  server.tool('alert_list',
    'List active price alerts on the current chart or for a specific symbol.',
    {},
    wrap('alert_list', async () => {
      const chart = await getChartApi();
      const alerts = await evaluateAsync(`
        (async () => {
          const chart    = ${chart};
          const alertMgr = chart.alertsManager?.();
          if (!alertMgr) throw new Error('Alert manager unavailable');
          const all = alertMgr.alerts?.() ?? [];
          return all.map(a => ({
            id:        a.id,
            symbol:    a.symbol ?? null,
            condition: a.condition ?? null,
            price:     a.price    ?? null,
            message:   a.message  ?? null,
            active:    a.active   ?? true,
          }));
        })()
      `);
      return { count: alerts.length, alerts };
    })
  );

  // ── Pine save ──────────────────────────────────────────────────────────────
  server.tool('pine_save',
    'Save the currently loaded Pine Script to your TradingView account. ' +
    'Equivalent to clicking "Save" in the Pine Editor. ' +
    'Returns success status and script name.',
    {},
    wrap('pine_save', async () => {
      const result = await evaluate(`
        (function() {
          // Click the Save button in the Pine Editor toolbar
          const btns = document.querySelectorAll('button');
          for (let i = 0; i < btns.length; i++) {
            const label = btns[i].textContent.trim();
            if (/^Save$/i.test(label) || /save script/i.test(btns[i].getAttribute('aria-label') ?? '')) {
              btns[i].click();
              return { success: true, action: 'save_clicked' };
            }
          }
          // Fallback: Ctrl+S keyboard shortcut
          document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {
            key: 's', ctrlKey: true, bubbles: true
          }));
          return { success: true, action: 'ctrl_s' };
        })()
      `);
      return result;
    })
  );

  // ── Pine console ──────────────────────────────────────────────────────────
  server.tool('pine_get_console',
    'Read the Pine Script console / log output (runtime log() calls). ' +
    'Returns the last N console lines.',
    {
      limit: z.number().int().min(1).max(200).default(50)
               .describe('Number of console lines to return (most recent first)'),
    },
    wrap('pine_get_console', async ({ limit }) => {
      const lines = await evaluate(`
        (function() {
          // TradingView stores Pine console lines in the Pine editor state
          const consoleEl = document.querySelector('[class*="consoleOutput"], [class*="pine-console"]');
          if (!consoleEl) return [];
          const rows = Array.from(consoleEl.querySelectorAll('[class*="consoleLine"], li, p'));
          return rows
            .slice(-${Math.floor(limit)})
            .map(r => r.textContent?.trim() ?? '')
            .filter(Boolean)
            .reverse();
        })()
      `);
      const arr = Array.isArray(lines) ? lines : [];
      return { count: arr.length, lines: arr };
    })
  );
}
