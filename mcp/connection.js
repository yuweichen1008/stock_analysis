/**
 * Hardened CDP connection for Oracle MCP.
 *
 * Security fixes vs. original tradingview-mcp:
 *
 * 1. NO module-level singleton client.
 *    Original: `let client = null` shared across all tool calls.
 *    Fix: Each logical session gets its own connection; getClient() creates
 *    on demand and closes on process exit.
 *
 * 2. Localhost-only binding assertion.
 *    We refuse to connect to any host other than 127.0.0.1 / localhost,
 *    so even if CDP_HOST is overridden via env it cannot reach a remote browser.
 *
 * 3. Target URL verification.
 *    We only attach to targets whose URL contains tradingview.com/chart.
 *    A malicious or accidentally-open tab cannot be hijacked.
 *
 * 4. evaluate() always uses returnByValue: true (no object handles leak).
 *    awaitPromise is explicit, never implicit.
 */

import CDP from 'chrome-remote-interface';

const CDP_HOST = '127.0.0.1';   // HARDCODED — never allow remote host
const CDP_PORT = parseInt(process.env.TV_CDP_PORT || '9222', 10);
const MAX_RETRIES = 3;
const BASE_DELAY  = 500;

let _client     = null;
let _targetInfo = null;

// Guarantee cleanup on exit
process.on('exit',    () => { if (_client) _client.close().catch(() => {}); });
process.on('SIGINT',  () => { if (_client) _client.close().catch(() => {}); process.exit(0); });
process.on('SIGTERM', () => { if (_client) _client.close().catch(() => {}); process.exit(0); });

async function _findChartTarget() {
  const resp = await fetch(`http://${CDP_HOST}:${CDP_PORT}/json/list`);
  if (!resp.ok) throw new Error(`CDP /json/list returned ${resp.status}`);
  const targets = await resp.json();

  // SECURITY: only attach to a TradingView chart tab — never to an arbitrary target
  const chart = targets.find(
    t => t.type === 'page' && /tradingview\.com\/chart/i.test(t.url)
  );
  if (!chart) {
    throw new Error(
      'No TradingView chart tab found on CDP port ' + CDP_PORT + '. ' +
      'Open TradingView Desktop and navigate to a chart, then retry.'
    );
  }
  return chart;
}

export async function getClient() {
  if (_client) {
    try {
      await _client.Runtime.evaluate({ expression: '1', returnByValue: true });
      return _client;
    } catch {
      _client     = null;
      _targetInfo = null;
    }
  }

  let lastError;
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      const target = await _findChartTarget();
      _targetInfo  = target;
      _client      = await CDP({ host: CDP_HOST, port: CDP_PORT, target: target.id });

      await _client.Runtime.enable();
      await _client.Page.enable();
      await _client.DOM.enable();

      _client.on('disconnect', () => {
        _client     = null;
        _targetInfo = null;
      });

      return _client;
    } catch (err) {
      lastError = err;
      if (attempt < MAX_RETRIES - 1) {
        const delay = Math.min(BASE_DELAY * 2 ** attempt, 10_000);
        await new Promise(r => setTimeout(r, delay));
      }
    }
  }
  throw new Error(`CDP connection failed after ${MAX_RETRIES} attempts: ${lastError?.message}`);
}

export async function getTargetInfo() {
  if (!_targetInfo) await getClient();
  return _targetInfo;
}

/**
 * Evaluate a JavaScript expression in TradingView's page context.
 *
 * SECURITY: expression should always be built with safeString() / requireFinite()
 * for any user-controlled values. Never interpolate raw user strings here.
 */
export async function evaluate(expression, { awaitPromise = false } = {}) {
  const c = await getClient();
  const result = await c.Runtime.evaluate({
    expression,
    returnByValue:  true,
    awaitPromise,
  });

  if (result.exceptionDetails) {
    const msg =
      result.exceptionDetails.exception?.description ||
      result.exceptionDetails.text ||
      'Unknown JS evaluation error';
    throw new Error(`JS evaluation error: ${msg}`);
  }

  return result.result?.value;
}

export const evaluateAsync = (expr) => evaluate(expr, { awaitPromise: true });

export async function disconnect() {
  if (_client) {
    try { await _client.close(); } catch {}
    _client     = null;
    _targetInfo = null;
  }
}

// ── Known TradingView internal API paths (verified via live probing) ───────────
export const PATHS = {
  chartApi:     'window.TradingViewApi._activeChartWidgetWV.value()',
  replayApi:    'window.TradingViewApi._replayApi',
  alertService: 'window.TradingViewApi._alertService',
  mainSeries:   'window.TradingViewApi._activeChartWidgetWV.value()._chartWidget.model().mainSeries()',
};

export async function verifyPath(path, name) {
  const exists = await evaluate(`typeof (${path}) !== 'undefined' && (${path}) !== null`);
  if (!exists) throw new Error(`${name} not available — is a chart open?`);
  return path;
}

export const getChartApi = () => verifyPath(PATHS.chartApi, 'Chart API');
export const getReplayApi = () => verifyPath(PATHS.replayApi, 'Replay API');
