# Feature 03 — Mobile Email + Password Auth

**Branch:** `feat/03-mobile-email-auth`  
**Target:** `main`  
**Scope:** Mobile app only (`mobile/`)

---

## Goal

The backend already has `POST /api/auth/register` and `POST /api/auth/login` (email + bcrypt). The mobile app currently only supports Apple, Google, and device-ID auth. Add email + password login/register to the mobile auth screen so users can create an account without Apple or Google.

---

## Backend context (do not change)

- `POST /api/auth/register` — body: `{ email, password, display_name? }` → `{ access_token, user }`
- `POST /api/auth/login`    — body: `{ email, password }` → `{ access_token, user }`
- Both return `AuthResponse` shape already typed in `mobile/lib/api.ts`
- Rate limited: 10/min per IP

---

## What to build

### 1. Add email auth to `mobile/lib/api.ts`

In the `Auth` namespace, add:

```typescript
login: (email: string, password: string) =>
  api.post<AuthResponse>('/api/auth/login', { email, password }).then(r => r.data),

register: (email: string, password: string, display_name?: string) =>
  api.post<AuthResponse>('/api/auth/register', { email, password, display_name }).then(r => r.data),
```

### 2. Add auth store methods to `mobile/store/auth.ts`

```typescript
loginWithEmail: async (email: string, password: string) => {
  const res = await Auth.login(email, password);
  await _persist(res.access_token, res.user);
  set({ token: res.access_token, user: res.user });
},

registerWithEmail: async (email: string, password: string, displayName?: string) => {
  const res = await Auth.register(email, password, displayName);
  await _persist(res.access_token, res.user);
  set({ token: res.access_token, user: res.user });
},
```

Add these to the `AuthState` interface too.

### 3. Update `mobile/app/auth.tsx`

The current auth screen has Apple Sign In and Google Sign In buttons plus a "continue anonymously" option.

Add a third section: **Email sign in**.

Layout of the new section (add below the OAuth buttons, above "continue anonymously"):

```
──────── or ────────

[Email input field]
[Password input field]

[Sign In]    [Create Account]

```

Two modes: **sign-in** (default) and **register**. Toggle between them with a small link: "Don't have an account? Register" / "Already have one? Sign in".

In register mode, show an optional "Display name" field above email.

**Error handling:** show inline error text in red below the button (e.g. "Invalid email or password", "Email already registered").

**Loading state:** disable all buttons while fetching.

**UX rules:**
- `KeyboardAvoidingView` wrapping the form so keyboard doesn't hide inputs on iOS
- `returnKeyType="next"` on email input, `returnKeyType="go"` on password (triggers submit)
- `autoCapitalize="none"` on email, `secureTextEntry` on password
- `ScrollView` outer container so content doesn't get clipped on small screens

---

## Files to modify

| File | Action |
|------|--------|
| `mobile/lib/api.ts` | Add `Auth.login` and `Auth.register` |
| `mobile/store/auth.ts` | Add `loginWithEmail`, `registerWithEmail` to store and interface |
| `mobile/app/auth.tsx` | Add email/password form section |

---

## Acceptance criteria

1. Auth screen shows email + password inputs below OAuth buttons
2. "Sign In" with correct credentials → navigates to main tabs
3. "Sign In" with wrong password → shows error message inline
4. "Create Account" with duplicate email → shows "Email already registered"
5. Toggling between Sign In / Register shows/hides Display name field
6. Keyboard does not cover inputs
7. `cd mobile && npx tsc --noEmit` → zero errors

---

## Agent prompt (copy-paste to spawn)

> You are implementing Feature 03 of the LokiStock mobile app. Read AGENTS.md first for conventions, then implement exactly what docs/features/03_mobile_email_auth.md specifies.
>
> Work on branch `feat/03-mobile-email-auth`. When done:
> 1. Run `cd mobile && npx tsc --noEmit` — fix any TypeScript errors
> 2. Commit: `feat(mobile): email + password login and register`
> 3. Open a PR to `main` using the template in AGENTS.md
>
> Do not modify any files outside `mobile/`. Do not touch `main`.
