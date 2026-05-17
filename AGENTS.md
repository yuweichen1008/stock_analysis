# LokiStock — Agent-Driven Development Workflow

This document is the operating manual for shipping features via isolated Claude agents, one pull request at a time.

---

## Philosophy

Each feature is developed in its own git branch by a Claude agent that has full context from this file plus the feature brief in `docs/features/`. The human PM reviews the diff and merges. No feature touches `main` until it is reviewed and approved.

```
main ──────────────────────────────────────────── (production-ready)
        │              │              │
   feat/01         feat/02       feat/03
   (agent A)       (agent B)     (agent C)
        │              │              │
      PR #1          PR #2         PR #3
```

---

## Branch Naming Convention

```
feat/<NN>-<slug>          e.g.  feat/01-ios-portfolio-tab
fix/<slug>                e.g.  fix/ctbc-session-expiry
chore/<slug>              e.g.  chore/bump-deps
```

Always branch from `main`. PRs target `main`.

---

## How to Launch a Feature Agent

### Option A — From Claude Code (recommended)

In Claude Code, use the Agent tool with `isolation: "worktree"`:

```
@claude spawn a worktree agent from docs/features/01_ios_portfolio_tab.md and open a PR when done
```

The agent works in an isolated git worktree on its own branch. When it finishes it opens a PR via `gh pr create`. You review the diff at the GitHub PR URL.

### Option B — Manual branch + Claude session

```bash
git checkout -b feat/01-ios-portfolio-tab
# Open Claude Code in this repo
# Paste: "Work on docs/features/01_ios_portfolio_tab.md — implement and open a PR"
```

### Reviewing a PR

In any Claude Code session:
```
/ultrareview <PR-number>
```
This runs a multi-agent review covering correctness, security, test coverage, and design consistency.

---

## PR Template

Every agent must use this PR body structure:

```markdown
## What this PR does
<1-3 bullet points>

## Files changed
<list key files>

## How to test
<step-by-step manual test or automated test command>

## Screenshots / before-after
<if UI change>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## Feature Backlog (ordered by priority)

| # | Branch | Brief | Status |
|---|--------|-------|--------|
| 01 | `feat/01-ios-portfolio-tab` | [iOS Portfolio Tab](docs/features/01_ios_portfolio_tab.md) | **Ready to build** |
| 02 | `feat/02-web-portfolio-robinhood` | [Web Portfolio — Robinhood UI](docs/features/02_web_portfolio_robinhood.md) | Ready to build |
| 03 | `feat/03-mobile-email-auth` | [Mobile Email Auth](docs/features/03_mobile_email_auth.md) | Ready to build |
| 04 | `feat/04-options-insight-widget` | [Options Insight Widget](docs/features/04_options_insight_widget.md) | Ready to build |
| 05 | `feat/05-ctbc-asset-history` | [CTBC Asset History Chart](docs/features/05_ctbc_asset_history.md) | Depends on 02 |

---

## Common Agent Rules

Every agent must follow these rules exactly — they apply to all features:

### Code style
- Dark theme: `bg-[#0d0d14]` surface, `#1a1a2e` card, `#2e2e50` border, `#7c5cfc` accent purple, `#00e676` bull green, `#ff5252` bear red
- Mobile: use React Native / Expo conventions — no web APIs, no `window`, no `document`
- Web: Next.js 14, `"use client"` for interactive components, Tailwind CSS
- No comments explaining what the code does — only add comments for non-obvious WHY
- No console.log in production code

### Auth pattern
- **Mobile**: `useAuthStore` from `mobile/store/auth.ts` — `token` is the JWT; axios interceptor attaches it automatically
- **Web**: `useAuth()` from `web/lib/auth.ts` — `getToken()` returns the JWT from localStorage
- **Backend broker endpoints**: pass `Authorization: Bearer <jwt>` header — the revised `/api/broker/balance`, `/positions`, `/orders` now accept JWT as an alternative to X-Internal-Secret

### API base URLs
- **Mobile**: `API_BASE` from `mobile/lib/api.ts` — always use the `api` axios instance, never `fetch`
- **Web**: use functions from `web/lib/api.ts` and `web/lib/auth.ts`

### Testing
- Backend: `python3 -m pytest tests/ -q` — all 86 non-API tests must pass
- Web TypeScript: `cd web && npx tsc --noEmit` — zero errors
- Mobile: no test runner configured; do a manual walk-through in the brief

### Commit message format
```
feat(<scope>): <short description>

<optional body>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

## Security rules (non-negotiable)

- Never commit `.env`, `.env.local`, or any file containing secrets
- `GET /api/users/broker-creds/{broker}` must NEVER return decrypted values
- Broker credentials are Fernet-encrypted at rest — never log or display plaintext creds
- All broker calls from the frontend must use the JWT from auth store, not hardcoded secrets
- `CTBC_DRY_RUN=true` is the default — never change this in code (only in .env)

---

## Key file map (agents read this to navigate quickly)

### Backend
| File | Purpose |
|------|---------|
| `api/main.py` | Router registration |
| `api/auth.py` | JWT helpers, `get_current_user`, `get_optional_user`, `encrypt_cred`, `decrypt_cred` |
| `api/db.py` | All SQLAlchemy models (14 tables) |
| `api/config.py` | All env vars via `settings` |
| `api/routers/auth.py` | `/api/auth/login`, `/register`, `/me` |
| `api/routers/users.py` | `/api/users/broker-creds` CRUD |
| `api/routers/broker.py` | `/api/broker/balance`, `/positions`, `/orders`, `/trades`, `/asset-history` |
| `api/services/broker_service.py` | `get_ctbc()`, `make_ctbc_for_user(user)`, `ctbc_call()` |
| `brokers/ctbc.py` | Playwright CTBC browser automation |

### Web (Next.js 14)
| File | Purpose |
|------|---------|
| `web/lib/auth.ts` | `useAuth()` hook, `getToken()`, `setSession()` |
| `web/lib/api.ts` | All API call functions |
| `web/lib/types.ts` | TypeScript interfaces |
| `web/components/NavBar.tsx` | Auth-aware nav (Login/user chip) |
| `web/components/TerminalLog.tsx` | Debug log strip at bottom of Portfolio page |
| `web/app/tws/TwsPage.tsx` | Portfolio page (CTBC + Moomoo tabs) |
| `web/app/trading/TradingPage.tsx` | Trading dashboard |
| `web/app/profile/page.tsx` | User profile + broker credential forms |

### Mobile (Expo / React Native)
| File | Purpose |
|------|---------|
| `mobile/lib/api.ts` | All API types and call functions |
| `mobile/store/auth.ts` | Zustand auth store — `useAuthStore()` |
| `mobile/store/watchlist.ts` | Zustand watchlist store |
| `mobile/app/(tabs)/_layout.tsx` | Tab bar config |
| `mobile/app/(tabs)/profile.tsx` | Profile tab |
| `mobile/app/auth.tsx` | Login / OAuth screen |
| `mobile/constants/colors.ts` | Design tokens |

---

## Design tokens (always use these)

```typescript
// Colors
bg:       '#0d0d14'   // page background
surface:  '#1a1a2e'   // card / tab bar
elevated: '#252540'   // elevated card
border:   '#2e2e50'   // dividers
accent:   '#7c5cfc'   // primary purple
bull:     '#00e676'   // green / positive
bear:     '#ff5252'   // red / negative
gold:     '#ffa726'   // coins / gold
blue:     '#448aff'   // info / fetch

textPrimary:   '#ffffff'
textSecondary: '#8888aa'
textMuted:     '#555570'
```

### Number formatting (Taiwan stocks)
```typescript
// TWD amounts
const NT = (n: number) => `NT$${n.toLocaleString('zh-TW', { maximumFractionDigits: 0 })}`;
// P&L with sign
const pnl = (n: number) => (n >= 0 ? '+' : '') + NT(n);
// Percentage
const pct = (n: number) => (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
```
