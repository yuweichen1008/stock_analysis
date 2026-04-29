# Oracle MCP Setup

## Install dependencies

```bash
cd mcp
npm install
```

## Oracle tools (no TradingView needed)

Start the Oracle API first:

```bash
docker compose up          # or: uvicorn api.main:app --reload --port 8000
```

The Oracle MCP tools (`oracle_options_screener`, `oracle_weekly_signals`, etc.)
call your local Oracle API and work without TradingView.

## TradingView tools (optional)

Launch **TradingView Desktop** with the debug port enabled. The `--remote-allow-origins`
flag is required — it restricts CDP access to requests from localhost only.

**macOS:**
```bash
open -a "TradingView" --args --remote-debugging-port=9222 \
  --remote-allow-origins=http://localhost:9222
```

**Windows (PowerShell):**
```powershell
& "${env:LOCALAPPDATA}\Programs\TradingView\TradingView.exe" `
  --remote-debugging-port=9222 `
  --remote-allow-origins=http://localhost:9222
```

> **Why `--remote-allow-origins`?**
> Without it, any browser tab on your machine can connect to port 9222 and execute
> arbitrary JavaScript in your TradingView session. This flag restricts CDP to
> connections that explicitly claim to originate from localhost.

Navigate to a chart in TradingView before using chart tools.

## Claude Code configuration

The `.claude/mcp.json` file in this repo configures Claude Code to use Oracle MCP
automatically when you open this project. No manual setup needed.

Verify it's loaded:
```
/mcp
```
You should see `oracle` listed with status `connected`.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ORACLE_API_BASE` | `http://localhost:8000` | Oracle FastAPI URL |
| `TV_CDP_PORT` | `9222` | Chrome DevTools Protocol port |
| `ORACLE_MCP_PINE_CHECK` | (unset) | Set to `1` to enable `pine_check` (sends code to TradingView servers) |

## Security notes

| Concern | Mitigation in this version |
|---------|---------------------------|
| CDP unauthenticated port | Use `--remote-allow-origins=http://localhost:9222` when launching TV |
| Arbitrary host in CDP | `CDP_HOST` hardcoded to `127.0.0.1` — cannot be overridden |
| Code injection via symbol/timeframe | Allowlist regex + set validation before any `evaluate()` call |
| Pine Script exfiltration | `pine_check` disabled by default; re-enable with explicit env var |
| Pine outbound requests | `pine_set_source` scans for `request.*` patterns and warns |
| Screenshot leaks | Rate-limited 5/min; saved only to `~/oracle-mcp-screenshots/` |
| No audit trail | Every tool call logged to `~/.oracle-mcp-audit.log` |
| Concurrent connection races | No singleton — connection created fresh, cleaned up on exit |

## Audit log

All tool calls are logged to `~/.oracle-mcp-audit.log`:

```jsonl
{"ts":"2026-04-28T10:23:41Z","tool":"oracle_options_screener","params":{"limit":10},"outcome":"ok"}
{"ts":"2026-04-28T10:23:55Z","tool":"chart_set_symbol","params":{"symbol":"AAPL"},"outcome":"ok"}
```

Pine Script source is truncated to `[Pine Script N chars]` in the log.
