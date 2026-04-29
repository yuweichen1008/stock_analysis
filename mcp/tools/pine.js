/**
 * Pine Script tools — hardened vs. original.
 *
 * Security changes:
 * 1. pine_check is DISABLED by default (it sends your code to pine-facade.tradingview.com,
 *    logging your IP and algorithm). Set ORACLE_MCP_PINE_CHECK=1 to enable.
 * 2. pine_set_source scans for outbound request.* calls and warns before injecting.
 * 3. Source size is capped at 100 KB to prevent memory issues.
 */

import { z } from 'zod';
import { evaluate, evaluateAsync } from '../connection.js';
import { safeString, scanPineSource, checkRateLimit, audit } from '../security.js';

const PINE_CHECK_ENABLED = process.env.ORACLE_MCP_PINE_CHECK === '1';
const MAX_SOURCE_BYTES = 100_000;

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

export function registerPineTools(server) {
  // ── Get source ────────────────────────────────────────────────────────────
  server.tool('pine_get_source',
    'Get current Pine Script source code from the editor',
    {},
    wrap('pine_get_source', async () => {
      const src = await evaluate(
        `(typeof monaco !== 'undefined' ? monaco.editor.getModels()[0]?.getValue() : null)`
      );
      return { source: src || null };
    })
  );

  // ── Set source (inject Pine Script) ──────────────────────────────────────
  server.tool('pine_set_source',
    'Inject Pine Script source code into the TradingView editor',
    { source: z.string().max(MAX_SOURCE_BYTES).describe('Pine Script v5 source code') },
    wrap('pine_set_source', async ({ source }) => {
      // SECURITY: scan for outbound network calls — warn but don't block
      const warnings = scanPineSource(source);

      await evaluateAsync(`
        (async () => {
          const model = monaco.editor.getModels()[0];
          if (!model) throw new Error('Pine editor not found — open a Pine Script tab first');
          model.setValue(${safeString(source)});
        })()
      `);

      return {
        success: true,
        chars: source.length,
        security_warnings: warnings.length > 0 ? warnings : undefined,
      };
    })
  );

  // ── Compile ───────────────────────────────────────────────────────────────
  server.tool('pine_compile',
    'Compile the current Pine Script and add it to the chart',
    {},
    wrap('pine_compile', async () => {
      const result = await evaluateAsync(`
        (async () => {
          const btn = document.querySelector('[data-name="add-script-to-chart"]');
          if (!btn) throw new Error('Compile button not found — is a Pine Script editor open?');
          btn.click();
          await new Promise(r => setTimeout(r, 1500));
          return { success: true };
        })()
      `);
      return result;
    })
  );

  // ── Get errors ────────────────────────────────────────────────────────────
  server.tool('pine_get_errors',
    'Get compilation errors from the Pine Script editor',
    {},
    wrap('pine_get_errors', async () => {
      const errors = await evaluate(
        `(typeof monaco !== 'undefined'
          ? monaco.editor.getModelMarkers({}).map(m => ({
              line: m.startLineNumber,
              col:  m.startColumn,
              msg:  m.message,
              severity: m.severity,
            }))
          : [])`
      );
      return { errors: errors || [] };
    })
  );

  // ── pine_check — DISABLED by default ─────────────────────────────────────
  if (PINE_CHECK_ENABLED) {
    server.tool('pine_check',
      '⚠ Validates Pine Script via TradingView servers (sends source code externally). ' +
      'Enable with ORACLE_MCP_PINE_CHECK=1.',
      { source: z.string().max(MAX_SOURCE_BYTES).describe('Pine Script source') },
      wrap('pine_check', async ({ source }) => {
        const warnings = scanPineSource(source);
        const resp = await fetch('https://pine-facade.tradingview.com/pine-facade/compile', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ source }),
        });
        const data = await resp.json();
        return { ...data, security_warnings: warnings };
      })
    );
  } else {
    server.tool('pine_check',
      'Disabled — would send source code to TradingView servers. Set ORACLE_MCP_PINE_CHECK=1 to enable.',
      { source: z.string().describe('Pine Script source') },
      async () => ({
        content: [{
          type: 'text',
          text: JSON.stringify({
            success: false,
            error:   'pine_check is disabled to protect your Pine Script from being sent to TradingView servers. ' +
                     'Set env var ORACLE_MCP_PINE_CHECK=1 to enable it explicitly.',
          }),
        }],
        isError: true,
      })
    );
  }
}
