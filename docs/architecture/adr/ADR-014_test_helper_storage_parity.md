# ADR-014: Test Helper Storage Parity — Immediate Fix & Storage Adapter Pattern

## Status
Accepted (Phase 1); Proposed (Phase 2 — pending RFC-001 approval)

## Date
2026-03-29

## Context

`ADR-013` migrated `frontend-mobile` session token storage from `sessionStorage` to `localStorage`. The migration updated production code in `App.tsx:22-37` but did not update the test helper file. `App.routing.test.tsx:26-32` continued to write to `sessionStorage`, while `App.tsx loadSession()` reads from `localStorage`. All four `App phase routing — ADR-011 Decision 4a` tests failed because the session seeded in `beforeEach` was invisible to the app under test.

The immediate fix was a one-line change per helper. The structural problem that allowed the drift is that session storage configuration (key name + storage backend) is duplicated across two files with no shared contract. Any future storage migration — or key rename — reintroduces the same class of silent regression.

See PRD-006 for the full requirements analysis.

---

## Decision

### Phase 1 — Immediate fix (Applied 2026-03-29)

Updated `frontend-mobile/src/test/App.routing.test.tsx:26-32`:

**Before (broken after ADR-013):**
```typescript
function setSession() {
  sessionStorage.setItem('ww_session', JSON.stringify(SESSION))
}
function clearSession() {
  sessionStorage.clear()
}
```

**After (aligned with ADR-013):**
```typescript
function setSession() {
  localStorage.setItem('ww_session', JSON.stringify(SESSION))
}
function clearSession() {
  localStorage.clear()
}
```

No other files changed. All four routing tests pass.

### Phase 2 — Storage Adapter Pattern (Proposed — see RFC-001)

**Decision (pending RFC-001 approval):** Extract a `frontend-mobile/src/lib/sessionStore.ts` module that owns the key name and storage backend. Both `App.tsx` and all test helpers import from this module.

**Rationale:**

The Phase 1 fix repairs the symptom. The structural cause — two files independently expressing the same storage contract — is not addressed. The risk is proportional to how often the storage layer changes. It has already changed once (ADR-013). The correct long-term fix is a single authoritative module.

**Rejected alternatives:**

- **Comment-only documentation:** A comment in `App.tsx` pointing to the test helper is not machine-checked and will not fail CI. Rejected.
- **Test-only constant file (`test/storageConstants.ts`):** Centralizes the key string but not the backend choice. A test could still import the right key and write to the wrong storage. Rejected.
- **ESLint rule banning raw `localStorage` calls:** Prevents inline storage calls but adds a lint dependency and a custom rule to maintain. Disproportionate for a two-consumer problem. Deferred — may be reconsidered if the number of raw storage calls grows.
- **Keeping the current structure with a code review reminder:** Not machine-enforced. Rejected.

---

## Consequences

**Phase 1:**

Positive:
- All routing tests pass immediately.
- No production code changes; zero risk to live behavior.

Negative:
- The structural drift risk is not eliminated — a future storage change would require a coordinated update to both `App.tsx` and the test helper again.

**Phase 2 (if RFC-001 approved):**

Positive:
- Changing the storage backend or key name requires editing exactly one file (`sessionStore.ts`).
- Test helpers have no knowledge of which Web Storage API is used — they import functions, not strings.
- The `Session` type and `SESSION_KEY` constant become the canonical reference, importable by any future consumer.

Negative:
- Adds a new module file. Small cost; accepted.
- `App.tsx` import graph gains one internal dependency. No circularity risk — `sessionStore.ts` has no imports from `App.tsx`.
- Existing tests continue to work without mocking the module (they use jsdom's real in-memory localStorage), so no test infrastructure changes are required.

---

## Related

- ADR-005: Test Infrastructure (established Vitest + jsdom baseline)
- ADR-013: Mobile Session Persistence & Rematch Redirect Forwarding (decision that caused the drift)
- PRD-006: Test Helper Storage Parity (requirements)
- RFC-001: Storage Adapter Module (design for Phase 2)
