# Feature 02 — Web Portfolio — Robinhood-style Redesign

**Branch:** `feat/02-web-portfolio-robinhood`  
**Target:** `main`  
**Scope:** Web app only (`web/`)

---

## Goal

Redesign the top section of the Portfolio page (`web/app/tws/TwsPage.tsx`) so it looks and feels like Robinhood:

- When CTBC is selected: hero section shows **Total Portfolio Value** (large), daily P&L, and an asset history area chart
- Below the hero: existing stock list (keep all existing functionality)
- Clean, uncluttered — replace the current "Account" mini-panel scattered in the right pane with a proper hero header

The existing page already fetches CTBC balance and positions — this feature is purely a UI restructuring of the CTBC tab view.

---

## Current state (do not break)

`web/app/tws/TwsPage.tsx` has:
- Broker toggle strip (CTBC / Moomoo) at the top
- CTBC tab: left list of TW stocks + right detail pane; balance mini-panel inside the right pane
- Moomoo tab: US stock view
- Terminal log at the bottom

**Keep all of this working.** Only restructure the CTBC tab's layout to add the hero section.

---

## What to add

### 1. `web/components/PortfolioHero.tsx` (NEW)

A self-contained hero component that shows the Robinhood-style portfolio summary. It fetches its own data.

Props:
```typescript
interface PortfolioHeroProps {
  market: 'TW' | 'US';
  onLog?: (type: LogType, msg: string) => void;
}
```

Layout:
```
┌──────────────────────────────────────────────────────────────┐
│  Total Portfolio Value                                        │
│  NT$1,234,567                    ← huge, white, bold         │
│  ▲ NT$14,940  (+0.04%)  Today   ← green/red, with arrow     │
│                                                              │
│  [Asset history area chart — Recharts AreaChart]             │
│  [1W] [1M] [3M] [YTD] [1Y]      ← period pills             │
│                                                              │
│  Buying power    NT$45,678       ← cash row                  │
└──────────────────────────────────────────────────────────────┘
```

**Chart:** use Recharts `AreaChart` (already a project dependency):
- `data` = `AccountSnapshot[]` filtered by period
- `XAxis` shows short date label (e.g. "5/12")
- `YAxis` hidden
- `Tooltip` shows date + value
- Area fill: gradient from `#00e676` → transparent (or `#ff5252` → transparent if P&L negative)
- No grid lines

**Period pills:** `['1W', '1M', '3M', 'YTD', '1Y']` — clicking filters the chart data. Active pill has `bg-white text-black`, inactive is `bg-[#2e2e50] text-[#8888aa]`.

**Loading skeleton:** while fetching, show pulsing grey rectangles (Tailwind `animate-pulse bg-[#2e2e50] rounded`):
- Value: `h-10 w-48`
- P&L: `h-5 w-32`
- Chart: `h-32 w-full`

**Auth-aware:** only fetch if `getToken()` returns a truthy value (user is logged in). If not logged in, show a soft placeholder:
```
Total Portfolio Value
—
Login to see your balance
```

**API calls** (use existing functions from `web/lib/api.ts`):
```typescript
import { brokerBalance, brokerAssetHistory } from '@/lib/api';
```

**P&L calculation:**
- "Today" P&L = today's `total_value` minus yesterday's `total_value` from `AccountSnapshot`
- If only one snapshot exists (new user), show `—` for today's P&L

### 2. Integrate into `web/app/tws/TwsPage.tsx`

In the CTBC tab section (`{broker === "CTBC" && ...}`), add `<PortfolioHero market="TW" onLog={addLog} />` at the top, before the existing stock list split view.

The existing `ctbcBalance` state and the balance mini-panel can remain — just add the hero above. The mini-panel inside the right pane becomes redundant for the balance display but keep it for the positions/orders detail.

---

## Files to create / modify

| File | Action |
|------|--------|
| `web/components/PortfolioHero.tsx` | CREATE |
| `web/app/tws/TwsPage.tsx` | MODIFY — import and place `<PortfolioHero>` in CTBC tab |

---

## Acceptance criteria

1. `PortfolioHero` renders at the top of the CTBC tab
2. Shows total value from `/api/broker/balance?market=TW`
3. Shows asset history chart from `/api/broker/asset-history?market=TW`
4. Period pills (1W/1M/3M/YTD/1Y) filter the chart correctly
5. P&L number is green when positive, red when negative
6. Loading skeleton shows while data is fetching
7. When not logged in: placeholder text shown (no fetch attempted)
8. All existing stock list, terminal log, and Moomoo tab functionality unchanged
9. `cd web && npx tsc --noEmit` → zero errors

---

## Agent prompt (copy-paste to spawn)

> You are implementing Feature 02 of the LokiStock web app. Read AGENTS.md first for conventions, then implement exactly what docs/features/02_web_portfolio_robinhood.md specifies.
>
> Work on branch `feat/02-web-portfolio-robinhood`. When done:
> 1. Run `cd web && npx tsc --noEmit` — fix any TypeScript errors
> 2. Commit: `feat(web): Robinhood-style PortfolioHero component with asset history chart`
> 3. Open a PR to `main` using the template in AGENTS.md
>
> Do not modify any files outside `web/`. Do not touch `main`.
