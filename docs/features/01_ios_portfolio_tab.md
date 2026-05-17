# Feature 01 — iOS Portfolio Tab (Robinhood-style)

**Branch:** `feat/01-ios-portfolio-tab`  
**Target:** `main`  
**Scope:** Mobile app only (`mobile/`)

---

## Goal

Add a **Portfolio** tab to the iOS mobile app that feels like Robinhood:

- Big total portfolio value at the top
- Daily P&L (amount + percent), green/red coloured
- Sparkline / line chart of asset value over time (periods: 1D · 1W · 1M · 3M · YTD · 1Y)
- Holdings list below (each row: ticker, shares, market value, P&L %)
- Buying power (cash) row
- If the user is NOT logged in → show a "Connect your broker" card with a login button

The reference design is the Robinhood Investing tab screenshot the PM shared (dark background, large green dollar value, green line chart, time period pills).

---

## What to build

### 1. New tab file: `mobile/app/(tabs)/portfolio.tsx`

This is a new file. The existing tabs are:
- `index.tsx` (訊號 / Signals)
- `oracle.tsx`
- `news.tsx`
- `community.tsx`
- `watchlist.tsx`
- `profile.tsx`

Add Portfolio between watchlist and profile (so tab order becomes: 訊號 · Oracle · News · Community · 自選股 · **Portfolio** · 我的).

### 2. Register the tab: `mobile/app/(tabs)/_layout.tsx`

Add a `<Tabs.Screen>` entry for `portfolio`:
```tsx
<Tabs.Screen
  name="portfolio"
  options={{ title: '持倉', tabBarIcon: ({ color }) => <TabIcon label="💼" color={color} /> }}
/>
```

### 3. Add broker API calls to `mobile/lib/api.ts`

The mobile API file already has a `Broker` namespace. The existing calls use `X-Internal-Secret`. Revise `brokerHeaders` to also attach the JWT so user-credentialed calls work:

```typescript
const INTERNAL_SECRET = process.env.EXPO_PUBLIC_INTERNAL_SECRET ?? '';
const getBrokerHeaders = () => {
  const h: Record<string, string> = {};
  if (INTERNAL_SECRET) h['X-Internal-Secret'] = INTERNAL_SECRET;
  // JWT is attached automatically by the axios interceptor from oracle_auth_token
  return h;
};
```

Add missing types and calls:

```typescript
export interface AccountSnapshot {
  date:           string;   // YYYY-MM-DD
  total_value:    number | null;
  cash:           number | null;
  unrealized_pnl: number | null;
  currency:       string | null;
}

// Add to Broker namespace:
assetHistory: (market = 'TW', days = 90) =>
  api.get<AccountSnapshot[]>(`/api/broker/asset-history?market=${market}&days=${days}`)
     .then(r => r.data),
balance: (market = 'TW') =>
  api.get<BrokerBalance>(`/api/broker/balance?market=${market}`)
     .then(r => r.data),
positions: (market = 'TW') =>
  api.get<BrokerPosition[]>(`/api/broker/positions?market=${market}`)
     .then(r => r.data),
```

(The existing `balance` and `positions` calls have no `market` param — update them to accept `market = 'TW'`.)

---

## Portfolio screen layout

```
┌────────────────────────────────────┐
│  💼 Portfolio                  ⚙️  │   ← header
├────────────────────────────────────┤
│                                    │
│        NT$1,234,567                │   ← total value, large white text
│      ▲ NT$14,940 (+0.04%) Today    │   ← daily P&L, green/red
│                                    │
│  ╭──────────────────────────────╮  │
│  │   [line chart sparkline]     │  │   ← asset history chart
│  ╰──────────────────────────────╯  │
│                                    │
│  [1D] [1W] [1M] [3M] [YTD] [1Y]   │   ← period pills (active = white bg)
│                                    │
├────────────────────────────────────┤
│  Buying Power          NT$45,678   │   ← cash row
├────────────────────────────────────┤
│  Holdings                          │
│  ┌──────────────────────────────┐  │
│  │ 智邦 (2345)                  │  │
│  │ 100 shares · NT$320.5        │  │
│  │                   +NT$4,200  │  │
│  │                     (+1.33%) │  │
│  └──────────────────────────────┘  │
│  (repeat for each holding)         │
└────────────────────────────────────┘
```

**Not logged in / no credentials:**
```
┌────────────────────────────────────┐
│  💼 Portfolio                      │
├────────────────────────────────────┤
│                                    │
│     🔒                             │
│  Connect your broker               │
│  Login and add CTBC or Moomoo      │
│  credentials to see your           │
│  portfolio here.                   │
│                                    │
│  [  Sign In  ]                     │
│                                    │
└────────────────────────────────────┘
```

---

## Implementation notes

### Chart
Use `react-native-svg` + a simple `Polyline`/`Path` — Recharts is web-only. If `react-native-svg` is not in `mobile/package.json`, install it: `cd mobile && npm install react-native-svg`. Draw the line chart manually using SVG:

```tsx
import Svg, { Polyline, Line } from 'react-native-svg';

// Map AccountSnapshot[] → SVG points string
const toPoints = (data: AccountSnapshot[], w: number, h: number) => {
  const values = data.map(d => d.total_value ?? 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return data.map((d, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - (((d.total_value ?? 0) - min) / range) * h;
    return `${x},${y}`;
  }).join(' ');
};
```

Color the line `#00e676` (bull green) if current value ≥ first value, else `#ff5252`.

### Period filtering
`AccountSnapshot` rows have `date: string` (YYYY-MM-DD). Filter client-side:

```typescript
const cutoff = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().split('T')[0];
};
const PERIODS = { '1D': 1, '1W': 7, '1M': 30, '3M': 90, 'YTD': ytdDays(), '1Y': 365 };
```

### Auth check
```typescript
const { token, user } = useAuthStore();
const isLoggedIn = !!token;
```
If `!isLoggedIn`, render the "Connect your broker" card and a button that navigates to `/auth`.

### Loading states
Show a skeleton / placeholder while fetching:
- Total value: grey rectangle `w-40 h-8 rounded bg-[#2e2e50]`
- Chart: grey rectangle full width h-32
- Each holding: grey row

### Error handling
CTBC calls fail silently if the broker isn't running. Show a subtle banner:
```
⚠️ CTBC unavailable — showing last known data
```

### Navigation to auth
```typescript
import { router } from 'expo-router';
router.push('/auth');
```

---

## Files to create / modify

| File | Action |
|------|--------|
| `mobile/app/(tabs)/portfolio.tsx` | CREATE |
| `mobile/app/(tabs)/_layout.tsx` | MODIFY — add portfolio tab |
| `mobile/lib/api.ts` | MODIFY — add AccountSnapshot type, assetHistory call, market param on balance/positions |

---

## Acceptance criteria

1. New "持倉" tab appears in the tab bar between 自選股 and 我的
2. When not logged in: lock icon + "Sign In" button visible, tapping navigates to auth screen
3. When logged in but no CTBC creds saved (`user.has_ctbc === false`): show "Connect CTBC" card
4. When logged in + CTBC configured: balance, positions, and asset history load
5. Period pills filter the chart (1W shows last 7 days of snapshots)
6. P&L is red when negative, green when positive
7. Holding rows show ticker, shares, value, P&L
8. TypeScript compiles: `cd mobile && npx tsc --noEmit`

---

## Agent prompt (copy-paste to spawn)

> You are implementing Feature 01 of the LokiStock app. Read AGENTS.md first for code conventions, then implement exactly what docs/features/01_ios_portfolio_tab.md specifies.
>
> Work on branch `feat/01-ios-portfolio-tab`. When done:
> 1. Run `cd mobile && npx tsc --noEmit` — fix any TypeScript errors
> 2. Commit with message `feat(mobile): Robinhood-style Portfolio tab with asset history chart`
> 3. Open a PR to `main` using the PR template in AGENTS.md
>
> Do not modify any files outside `mobile/`. Do not touch `main`.
