# PRD-006: Test Helper Storage Parity

## §1. Context & Problem

### §1.1 The Bug

`ADR-013` (2026-03-29) migrated `frontend-mobile` session token storage from `sessionStorage` to `localStorage`. The migration changed three functions in `App.tsx:22-37` but left the test helper file unchanged.

`App.routing.test.tsx:26-32` contained:

```typescript
function setSession() {
  sessionStorage.setItem('ww_session', JSON.stringify(SESSION))  // WRONG after ADR-013
}
function clearSession() {
  sessionStorage.clear()                                         // WRONG after ADR-013
}
```

Because `App.tsx loadSession()` reads from `localStorage`, every routing test that called `setSession()` received `null` from `loadSession()` — the app showed the onboarding form instead of the expected game screen. All four `App phase routing` tests failed silently until the discrepancy was noticed and the helpers were updated.

### §1.2 Root Cause

Session storage configuration (key name + storage backend) is defined in two separate files with no shared contract:

| Location | Artifact | Storage | Key |
|----------|----------|---------|-----|
| `frontend-mobile/src/App.tsx:22-37` | `loadSession / saveSession / clearSession` | `localStorage` | `ww_session` |
| `frontend-mobile/src/test/App.routing.test.tsx:26-32` | `setSession / clearSession` | `localStorage` (fixed) | `ww_session` |

Both files must agree on (a) the key name and (b) the storage backend. There is no compile-time or lint-time enforcement of this agreement. A future storage migration — or even a key rename — will silently re-introduce the same class of bug.

### §1.3 Scope

This PRD covers the `ww_session` key in `frontend-mobile`. The `ww_host_{gameId}` key in `frontend-display/src/App.tsx:33-52` is subject to the same structural risk and is in scope for the long-term solution defined in RFC-001, but is not the driver of this PRD.

---

## §2. Current Structure

### §2.1 Storage Keys in Use

| Key Pattern | Backend | Owner File | Purpose |
|-------------|---------|------------|---------|
| `ww_session` | `localStorage` | `frontend-mobile/src/App.tsx:22-37` | Player reconnect session (game_id, player_id, session_token) |
| `ww_note_{gameId}_{playerId}_{targetId}` | `localStorage` | `DayDiscussionScreen.tsx:14-57` | Per-player opinion tags |
| `ww_seer_{gameId}_{playerId}` | `sessionStorage` | `SeerPeekUI.tsx:21-56` | Seer investigation history (tab-scoped by design — ADR-003 §9) |
| `ww_host_{gameId}` | `localStorage` | `frontend-display/src/App.tsx:33-52` | Host secret for display authentication |

### §2.2 Test Helper Inventory

| File | Helper | Current State |
|------|--------|---------------|
| `frontend-mobile/src/test/App.routing.test.tsx:26-32` | `setSession / clearSession` | Fixed — uses `localStorage` |

No other test file currently contains storage helpers that mirror production storage functions.

---

## §3. Requirements

### §3.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| F-1 | A single authoritative module owns the key name and storage backend for `ww_session`. All consumers (production code + test helpers) import from it. |
| F-2 | Changing the storage backend for `ww_session` requires editing exactly one file. No test file requires a coordinated update. |
| F-3 | Test helpers that seed or clear session state import the same `loadSession`/`saveSession`/`clearSession` functions that production code uses, or a thin test-facing wrapper that delegates to the same underlying module. |
| F-4 | The `SESSION_KEY` string (`ww_session`) is exported as a named constant — not duplicated as a string literal in test files. |

### §3.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NF-1 | The abstraction adds zero runtime overhead. The adapter functions are thin wrappers over `localStorage.getItem/setItem/removeItem`. |
| NF-2 | The module is TypeScript-typed: `loadSession` returns `Session \| null`; `saveSession` accepts `Session`; `clearSession` returns `void`. |
| NF-3 | No new test infrastructure (no new mocking layers, no `vi.mock` on the module) is required to use the adapter in tests. Tests call `saveSession(SESSION)` directly against jsdom's in-memory localStorage. |

### §3.3 Anti-Scope

- Not changing the `ww_seer_*` sessionStorage pattern — that is intentionally tab-scoped (ADR-003 §9).
- Not introducing a dependency injection pattern or abstract storage interface — the adapter is a concrete localStorage module.
- Not adding lint rules to ban raw `localStorage`/`sessionStorage` calls — enforced by convention, not tooling (may be revisited).

---

## §4. User Stories

| As a | I want to | So that |
|------|-----------|---------|
| Test Author | import `saveSession` from the production session module | I never need to know which Web Storage API the app uses |
| Test Author | have `clearSession` clear the correct storage backend | My `beforeEach` teardown does not leave stale state that silently poisons the next test |
| CI Pipeline | have routing tests fail loudly if the session is seeded into the wrong storage | A storage migration caught in CI rather than discovered manually |
| Storage Maintainer | change the storage backend in one file | All callers — production and test — pick up the change automatically |
| Storage Maintainer | rename the `ww_session` key | No test file needs a coordinated string-literal update |

---

## §5. Acceptance Criteria

```gherkin
Given the app reads session from localStorage under key "ww_session"
When a test calls saveSession({ game_id: 'g1', player_id: 'p1', session_token: 'tok' })
Then localStorage.getItem('ww_session') returns the serialized session object
And sessionStorage.getItem('ww_session') returns null

Given the production session module exports SESSION_KEY = 'ww_session'
When a developer renames the key to 'ww_session_v2' in the module
Then all consumers (App.tsx, test helpers) use the new key without any other file changes

Given a test runs setSession() followed by clearSession()
When the test ends and beforeEach runs clearSession() for the next test
Then localStorage contains no 'ww_session' key
And no prior-test session bleeds into the next test's loadSession() call
```

---

## §6. Phase-Gate Plan

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 1 — Immediate fix | Update `setSession`/`clearSession` helpers in `App.routing.test.tsx` to use `localStorage` | **Done** (2026-03-29) |
| 2 — Storage adapter | Extract `frontend-mobile/src/lib/sessionStore.ts` with exported session functions and constants | Proposed in RFC-001 |
| 3 — Migration | Update `App.tsx` and `App.routing.test.tsx` to import from `sessionStore.ts` | Follows RFC-001 approval |
| 4 — Display parity | Apply same adapter pattern to `frontend-display/src/App.tsx` for `ww_host_*` | Follow-on work |

---

## §7. Open Questions

| # | Question | Owner |
|---|----------|-------|
| 1 | Should `saveSession` / `clearSession` be re-exported from `App.tsx` for backward compatibility, or should callers be updated to import directly from `sessionStore.ts`? | Engineering |
| 2 | Is a Vitest custom matcher (`expect(session).toBeStoredInLocalStorage()`) worth the setup cost, or is direct `localStorage.getItem` assertion sufficient? | Engineering |
