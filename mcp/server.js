#!/usr/bin/env node
/**
 * Oracle MCP Server
 *
 * A hardened TradingView MCP bridge + Oracle signal tools for Claude Code.
 *
 * Security improvements over tradesdontlie/tradingview-mcp:
 *   - All user inputs validated via allowlist (symbol, timeframe, chart type)
 *   - safeString() applied consistently to every CDP interpolation
 *   - No module-level singleton connection (race-condition fix)
 *   - CDP hardcoded to 127.0.0.1 only — cannot be redirected to remote host
 *   - CDP target URL verified against tradingview.com/chart pattern
 *   - pine_check disabled by default (prevents source exfiltration to TV servers)
 *   - Pine Script scanned for outbound request.* calls before injection
 *   - Screenshot output isolated to ~/oracle-mcp-screenshots/
 *   - Per-tool rate limiting (30 calls/min general; 5/min screenshots; 10/min pine)
 *   - Append-only audit log at ~/.oracle-mcp-audit.log
 *
 * Tools exposed:
 *   TV chart tools:  chart_get_state, chart_set_symbol, chart_set_timeframe,
 *                    chart_set_type, chart_manage_indicator, chart_get_visible_range,
 *                    chart_scroll_to_date
 *   Pine Script:     pine_get_source, pine_set_source, pine_compile, pine_get_errors,
 *                    pine_check (disabled by default — set ORACLE_MCP_PINE_CHECK=1)
 *   Screenshots:     capture_screenshot
 *   Oracle signals:  oracle_options_screener, oracle_options_overview,
 *                    oracle_options_history, oracle_weekly_signals, oracle_news_feed,
 *                    oracle_signal_search, oracle_backtest_results, oracle_prediction
 *
 * Usage (in .claude/settings.json mcpServers):
 *   {
 *     "oracle": {
 *       "command": "node",
 *       "args": ["/path/to/stock_analysis/mcp/server.js"],
 *       "env": {
 *         "ORACLE_API_BASE": "http://localhost:8000",
 *         "TV_CDP_PORT": "9222"
 *       }
 *     }
 *   }
 *
 * TradingView Desktop must be launched with:
 *   --remote-debugging-port=9222 --remote-allow-origins=http://localhost:9222
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';

import { registerChartTools  } from './tools/chart.js';
import { registerPineTools   } from './tools/pine.js';
import { registerCaptureTools} from './tools/capture.js';
import { registerOracleTools } from './tools/oracle.js';

process.stderr.write(
  '⚠  Oracle MCP Server\n' +
  '   Unofficial tool — not affiliated with TradingView Inc. or Anthropic.\n' +
  '   TradingView tools require Desktop app with --remote-debugging-port=9222.\n' +
  '   Oracle tools require Oracle API running at ' + (process.env.ORACLE_API_BASE || 'http://localhost:8000') + '\n' +
  '   Audit log: ~/.oracle-mcp-audit.log\n\n'
);

const server = new McpServer(
  {
    name:        'oracle-mcp',
    version:     '1.0.0',
    description: 'Oracle signal tools + hardened TradingView chart bridge for Claude Code',
  },
  {
    instructions: `Oracle MCP — two classes of tools:

ORACLE TOOLS (no TradingView needed — reads Oracle API directly):
- oracle_options_screener   → latest RSI+PCR+IV Rank options signals (scored 0-10)
- oracle_options_overview   → VIX, market PCR, signal counts
- oracle_options_history    → 30-day signal history for one ticker
- oracle_weekly_signals     → ±5% contrarian signals with PCR
- oracle_news_feed          → news + PCR sentiment feed
- oracle_signal_search      → search TW/US signal stocks
- oracle_backtest_results   → RSI+PCR win rate backtest
- oracle_prediction         → today's TAIEX Oracle prediction + stats

TRADINGVIEW TOOLS (requires TV Desktop with CDP on port 9222):
- chart_get_state           → symbol, timeframe, all indicator entity IDs (call first)
- chart_set_symbol          → change ticker (validated allowlist)
- chart_set_timeframe       → change resolution (validated allowlist)
- chart_set_type            → change chart type
- chart_manage_indicator    → add/remove study
- chart_get_visible_range   → current visible date range
- chart_scroll_to_date      → jump to date
- pine_get_source           → get current Pine Script
- pine_set_source           → inject Pine Script (warns on request.* network calls)
- pine_compile              → compile and add to chart
- pine_get_errors           → compilation errors
- pine_check                → DISABLED by default (sends code to TV servers)
- capture_screenshot        → screenshot (rate-limited 5/min, saved to ~/oracle-mcp-screenshots/)

WORKFLOW:
1. For signal analysis: call oracle_options_screener first, then optionally open
   a high-score ticker in TradingView and use chart_get_state to verify.
2. For Pine development: use pine_set_source → pine_compile → pine_get_errors loop.
3. NEVER use pine_check unless you accept that TradingView logs your source code.`,
  }
);

registerOracleTools(server);   // Oracle API tools (always available)
registerChartTools(server);    // TradingView CDP chart control
registerPineTools(server);     // Pine Script editing
registerCaptureTools(server);  // Screenshots

const transport = new StdioServerTransport();
await server.connect(transport);
