# Feature 05 — CTBC Asset History Dedicated Page

**Branch:** `feat/05-ctbc-asset-history`  
**Target:** `main`  
**Depends on:** Feature 02 merged (PortfolioHero component exists)  
**Scope:** Web app only (`web/`)

---

## Goal

Build a dedicated `/portfolio/history` page that shows the full CTBC asset history: a large area chart of total portfolio value over time, with the ability to drill into individual time periods. This is the "account value over time" feature that CTBC 亮點 doesn't have.

---

## What to build

### New page: `web/app/portfolio/history/page.tsx`

This page is auth-gated: redirect to `/login?next=/portfolio/history` if no JWT.

**Layout:**

```
┌──────────────────────────────────────────────────┐
│  ← Back to Portfolio      Asset History          │
├──────────────────────────────────────────────────┤
│                                                  │
│  Total Value Today                               │
│  NT$1,234,567                                    │
│  ▲ NT$45,678 since first snapshot (+3.84%)       │
│                                                  │
│  [1W] [1M] [3M] [6M] [1Y] [All]                 │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │                                            │  │
│  │   [Full-height AreaChart — Recharts]       │  │
│  │                                            │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  Snapshot history                                │
│  ┌────────────────────────────────────────────┐  │
│  │  Date        Value         P&L vs prev     │  │
│  │  2025-05-17  NT$1,234,567  ▲ +NT$3,210    │  │
│  │  2025-05-16  NT$1,231,357  ▼ -NT$8,900    │  │
│  │  ...                                       │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### Chart details

- Recharts `AreaChart` + `Area` + `XAxis` (show month/day) + `Tooltip`
- Fill gradient: green → transparent when trending up, red → transparent when trending down (compare first to last value in current period)
- Height: 280px
- Reference line at current value
- `CartesianGrid` with subtle `#2e2e50` stroke

### Snapshot table

Columns: Date | Total Value | Cash | Unrealized P&L | Daily Change
- Daily Change = this row's `total_value` minus previous row's `total_value`
- Color daily change green/red
- Newest first

### Period selector

Periods: `1W` (7d), `1M` (30d), `3M` (90d), `6M` (180d), `1Y` (365d), `All` (all snapshots).

Fetch all data once with `days=365` and filter client-side for shorter periods. For "All", use `days=730`.

### API

```typescript
import { brokerAssetHistory } from '@/lib/api';
// Already exists: brokerAssetHistory(market = 'TW', days = 90)
```

Call with `days=730` to get full history, filter client-side by period.

### Navigation

- Add a "History →" link inside `PortfolioHero` (Feature 02) next to the period pills if it exists.
- Also link from the Trading page's "Asset History" section.

---

## Files to create / modify

| File | Action |
|------|--------|
| `web/app/portfolio/history/page.tsx` | CREATE |
| `web/components/PortfolioHero.tsx` | MODIFY — add "Full History →" link (if Feature 02 merged) |

---

## Acceptance criteria

1. `/portfolio/history` redirects to `/login` if not authenticated
2. When authenticated: full area chart renders with AccountSnapshot data
3. Period pills filter the chart correctly
4. Snapshot table shows all snapshots newest-first with daily P&L column
5. "All" period shows everything available
6. "← Back to Portfolio" link works
7. `cd web && npx tsc --noEmit` → zero errors

---

## Agent prompt (copy-paste to spawn)

> You are implementing Feature 05 of the LokiStock web app. Read AGENTS.md first for conventions, then implement exactly what docs/features/05_ctbc_asset_history.md specifies.
>
> Work on branch `feat/05-ctbc-asset-history`. When done:
> 1. `cd web && npx tsc --noEmit` — fix TypeScript errors
> 2. Commit: `feat(web): dedicated CTBC asset history page with full period chart`
> 3. Open a PR to `main` using the template in AGENTS.md
>
> Check if PortfolioHero exists (Feature 02). If it does, add the "Full History →" link. If not, skip that part and note it in the PR. Do not touch `main`.
