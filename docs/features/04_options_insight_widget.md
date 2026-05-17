# Feature 04 — Options Insight Widget

**Branch:** `feat/04-options-insight-widget`  
**Target:** `main`  
**Scope:** Web app (`web/`) and Mobile app (`mobile/`)

---

## Goal

Surface the top 3 options screener signals as a small "insight" widget that appears:
1. On the web Portfolio page (below the PortfolioHero, above the stock list) — visible to ALL users, no login required
2. On the mobile Portfolio tab — at the bottom of the holdings list as a "Market Insights" section

This is a read-only, public feature. The options screener already runs twice daily and stores results in the `options_signals` table. The endpoint `GET /api/options/overview` returns the top signals.

---

## Web widget: `web/components/OptionsInsightWidget.tsx` (NEW)

### Layout

```
┌─────────────────────────────────────────────────────┐
│  Options Insights                    [View all →]   │
├──────────────┬──────────────┬───────────────────────┤
│  AAPL        │  TSLA        │  NVDA                 │
│  📈 Buy      │  📉 Sell     │  ⚡ Unusual            │
│  Score 8.2   │  Score 7.1   │  Score 9.0            │
│  RSI 28.4    │  RSI 72.1    │  PCR 0.41             │
│  IV Rank 65  │  IV Rank 78  │  IV Rank 91           │
└──────────────┴──────────────┴───────────────────────┘
```

Three cards in a horizontal row. Each card:
- Ticker name (large)
- Signal badge: `📈 Buy Signal` (green), `📉 Sell Signal` (red), `⚡ Unusual Activity` (yellow)
- Score: `Score 8.2 / 10`
- RSI: `RSI 28.4`
- IV Rank (if available): `IVR 65`

"View all →" links to `/options`.

**Data source:** `GET /api/options/overview` → `OptionsOverview.top_signals` (array of `OptionsSignalItem`)

**No auth required** — call it unconditionally.

**Auto-refresh:** refetch every 5 minutes using `setInterval` inside `useEffect`.

**Loading:** three grey skeleton cards.

**Empty state:** if `top_signals.length === 0`, show "No signals today — check back after market hours."

### Signal badge colours

```typescript
const SIGNAL_STYLE = {
  buy_signal:         { label: 'Buy Signal',        emoji: '📈', color: '#00e676', bg: '#00e67620' },
  sell_signal:        { label: 'Sell Signal',        emoji: '📉', color: '#ff5252', bg: '#ff525220' },
  unusual_activity:   { label: 'Unusual Activity',   emoji: '⚡', color: '#ffd700', bg: '#ffd70020' },
};
```

### Integration into `web/app/tws/TwsPage.tsx`

Add `<OptionsInsightWidget />` inside the CTBC tab section, below the PortfolioHero (or below the broker toggle if Feature 02 is not yet merged — it must work standalone):

```tsx
{broker === "CTBC" && (
  <>
    <OptionsInsightWidget />   {/* ← add this */}
    {/* existing stock list ... */}
  </>
)}
```

---

## Mobile widget: add to `mobile/app/(tabs)/portfolio.tsx`

At the bottom of the Portfolio screen (after the holdings list), add a **Market Insights** section:

```
─────────────── Market Insights ───────────────

 📈 Buy Signal          AAPL    Score 8.2
 📉 Sell Signal         TSLA    Score 7.1
 ⚡ Unusual Activity    NVDA    Score 9.0

             [View Options Screener →]
```

Each row is a `TouchableOpacity` that does nothing (future: navigate to options detail). "View Options Screener →" does nothing for now (options screener is web-only).

**Data source:** add `Options.overview()` call in `mobile/lib/api.ts` (it already exists). Use `top_signals` from the response.

This section is visible to ALL users regardless of login status.

---

## Files to create / modify

| File | Action |
|------|--------|
| `web/components/OptionsInsightWidget.tsx` | CREATE |
| `web/app/tws/TwsPage.tsx` | MODIFY — add widget in CTBC tab |
| `mobile/app/(tabs)/portfolio.tsx` | MODIFY — add Market Insights section (Feature 01 must exist) |

**Note:** Feature 01 (iOS Portfolio tab) must be merged first for the mobile portion. If not merged, implement only the web widget and note this in the PR.

---

## Acceptance criteria

### Web
1. Widget renders below broker toggle (or below PortfolioHero if Feature 02 merged)
2. Shows up to 3 signal cards with correct colours and signal type
3. "View all →" links to `/options`
4. Refreshes every 5 minutes
5. Skeleton shown while loading, "No signals" message when empty
6. `cd web && npx tsc --noEmit` → zero errors

### Mobile
1. "Market Insights" section at bottom of Portfolio tab
2. Shows up to 3 signal rows
3. `cd mobile && npx tsc --noEmit` → zero errors

---

## Agent prompt (copy-paste to spawn)

> You are implementing Feature 04 of the LokiStock app. Read AGENTS.md first for conventions, then implement exactly what docs/features/04_options_insight_widget.md specifies.
>
> Work on branch `feat/04-options-insight-widget`. When done:
> 1. `cd web && npx tsc --noEmit` — fix web TypeScript errors
> 2. `cd mobile && npx tsc --noEmit` — fix mobile TypeScript errors
> 3. Commit: `feat: options insight widget on web Portfolio and mobile`
> 4. Open a PR to `main` using the template in AGENTS.md
>
> Do not touch `main`. If Feature 01 is not yet merged, skip the mobile portion and note it in the PR.
