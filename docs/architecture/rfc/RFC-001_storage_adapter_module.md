# RFC-001: Storage Adapter Module for Session Persistence

## Status
Proposed

## Date
2026-03-29

## Authors
Engineering

## Related
- PRD-006: Test Helper Storage Parity
- ADR-013: Mobile Session Persistence & Rematch Redirect Forwarding
- ADR-014: Test Helper Storage Parity — Phase 2

---

## 1. Problem

Session storage configuration is duplicated across two files in `frontend-mobile`:

```
frontend-mobile/src/App.tsx:22-37          loadSession / saveSession / clearSession
frontend-mobile/src/test/App.routing.test.tsx:26-32   setSession / clearSession (test helpers)
```

Both express the same contract — "store this JSON blob under `ww_session` in `localStorage`" — independently. When `ADR-013` changed the storage backend from `sessionStorage` to `localStorage`, only `App.tsx` was updated. The test helpers silently drifted, all four routing tests failed, and the bug was caught only by running the test suite manually.

This RFC proposes a `sessionStore.ts` module that becomes the single authoritative definition of that contract.

---

## 2. Proposed Solution

### 2.1 New Module: `frontend-mobile/src/lib/sessionStore.ts`

```typescript
import type { Session } from '../types/game'

export const SESSION_KEY = 'ww_session'
const store = localStorage  // single line to change if backend changes

export function loadSession(): Session | null {
  const raw = store.getItem(SESSION_KEY)
  return raw ? (JSON.parse(raw) as Session) : null
}

export function saveSession(s: Session): void {
  store.setItem(SESSION_KEY, JSON.stringify(s))
}

export function clearSession(): void {
  store.removeItem(SESSION_KEY)
}
```

**Key design choices:**

- `const store = localStorage` — the storage backend is a single reassignable line, not scattered across three functions. A future backend change is a one-character edit in one file.
- Named exports — consumers import specific functions; no default export to prevent `import store from '...'` naming conflicts.
- `SESSION_KEY` is exported — test helpers that need to assert against raw storage (`localStorage.getItem(SESSION_KEY)`) import the constant rather than repeating the string literal.
- No dependency on React or Vite internals — the module is a plain TypeScript file, importable in any test environment without mocking.

### 2.2 Updated `App.tsx`

Remove the inline implementations at lines 22–37 and replace with imports:

```typescript
// Before (inline in App.tsx)
const SESSION_KEY = 'ww_session'
function loadSession(): Session | null { ... }
function saveSession(s: Session) { ... }
function clearSession() { ... }

// After
import { loadSession, saveSession, clearSession } from './lib/sessionStore'
```

No other changes to `App.tsx`. All three functions are currently used at lines 52, 67, 74, and 150 — those call sites are unchanged.

### 2.3 Updated `App.routing.test.tsx`

Remove the local helper functions and the `'ww_session'` string literal. Replace with imports from the production module:

```typescript
// Before (duplicated in test file)
const SESSION = { game_id: 'g1', player_id: 'p1', session_token: 'tok' }
function setSession() {
  localStorage.setItem('ww_session', JSON.stringify(SESSION))
}
function clearSession() {
  localStorage.clear()
}

// After
import { saveSession, clearSession, SESSION_KEY } from '../lib/sessionStore'
const SESSION = { game_id: 'g1', player_id: 'p1', session_token: 'tok' }
// setSession() is replaced inline by saveSession(SESSION)
// clearSession() delegates to the same function the app uses
```

Tests call `saveSession(SESSION)` directly. Because jsdom provides a real in-memory `localStorage`, no mocking of `sessionStore.ts` is required.

---

## 3. No Change to Server Contract

This refactor is entirely client-side. The WebSocket payloads, REST endpoints, and `Session` type structure are unchanged:

```
Client (App.tsx)          WebSocket / REST           Server
  loadSession()    ──────  session_token in URL  ──→  validate token
  saveSession()    ←─────  { type: "sync", ... }      issue token
  clearSession()   ──────  POST /rejoin 401      ──→  reject expired
```

The `Session` interface (`game_id`, `player_id`, `session_token`) is not modified.

---

## 4. Secondary Scope: `frontend-display` Host Secret

`frontend-display/src/App.tsx:33-52` has the same structural pattern for `ww_host_{gameId}`:

```typescript
localStorage.getItem(`ww_host_${gId}`)      // line 33
localStorage.setItem(`ww_host_${newGameId}`, newHostSecret)  // line 52, 171
```

This is not tested by a helper file today, so there is no active drift risk. However, the same adapter pattern applies: a `frontend-display/src/lib/hostStore.ts` module would own the key pattern and backend. This is **out of scope for the initial implementation** but is the correct follow-on work once `sessionStore.ts` is established as the pattern.

---

## 5. Verification

### Automated

```bash
# From frontend-mobile/
npm test -- --run

# Expected: all 4 App.routing tests pass
# Expected: no TypeScript errors (tsc --noEmit)
```

### Manual check

1. Open `frontend-mobile/src/lib/sessionStore.ts` — confirm `SESSION_KEY` and `store` are the only two configuration points.
2. Search for `'ww_session'` string literals across `frontend-mobile/src/` — should appear only in `sessionStore.ts` and nowhere else.
3. Search for `localStorage.setItem` and `sessionStorage.setItem` in `frontend-mobile/src/App.tsx` — should return zero results after migration.

### Regression guard

A deliberate break-and-fix test: change `const store = localStorage` to `const store = sessionStorage` in `sessionStore.ts`, run the routing tests — all four should fail immediately. Revert and confirm they pass. This validates that test helpers are now coupled to the module and will catch future backend changes.

---

## 6. Open Questions

| # | Question | Notes |
|---|----------|-------|
| 1 | Should `sessionStore.ts` live in `src/lib/` or `src/utils/`? | Prefer `lib/` — it is a domain module, not a generic utility. |
| 2 | Should `clearSession` clear only `SESSION_KEY` (current proposal) or all `ww_*` keys? | Current: `removeItem(SESSION_KEY)`. Clearing all `ww_*` keys is a broader operation and may be undesirable (e.g., should not clear seer history on session reset). Stay narrow. |
| 3 | Should `saveSession` validate the `Session` shape before writing? | No — the `Session` type provides compile-time safety. Runtime validation adds complexity for an internal API. |
