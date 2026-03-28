---
date: 2026-03-27
topic: display-flow-part1
title: "Front-End (Main Display) Flow Updates — Research & Gap Analysis"
spec: FrontendDisplayDesign.md
areas:
  - frontend-display
  - CreateMatchScreen
  - LobbyScreen
  - App.tsx
---

# Display Flow — Part 1: Research & Gap Analysis

## 0. Source of Truth

Two authoritative sources were cross-referenced:

| Source | Role |
|--------|------|
| `FrontendDisplayDesign.md` | **Target spec** — defines intended architecture, API contracts, state shape |
| `frontend-display/src/` (current code) | **Current implementation** — what is actually running today |

---

## 1. Scope Decision: What Is and Is Not Changing

Existing naming and API surface are **preserved**. Only the four targeted behaviors below are adopted from the spec:

| # | Change Adopted | Kept As-Is |
|---|---------------|------------|
| 1 | `host_secret` moves from `sessionStorage` → URL params | Name stays `host_secret` (not `host_token`) |
| 2 | WS message types: `state_update` → `sync` / `update` | All other WS logic unchanged |
| 3 | Display WS handshake: `{ player_id: null, credentials: null }` | Endpoint path unchanged (`/ws/{gameId}/display`) |
| 4 | Lobby roster source: `match_data` WS events → Zustand store | Component file paths and names unchanged |
| — | Min players to start: **5 — unchanged** | Not adopting spec's `roster.length > 0` |
| — | API prefix: `/api/games` — unchanged | Not adopting `/matches` |
| — | Response shape: `{ game_id, host_secret }` — unchanged | Not adopting `{ match_id, host_token }` |
| — | Component structure: `components/` — unchanged | Not adopting `scenes/` |

---

## 2. Landing Page: Game Initialization

### 2.1 Current Implementation

**File:** `frontend-display/src/components/CreateMatchScreen/CreateMatchScreen.tsx` (lines 37–55)

Single-option screen:
```
Title:    🐺 Werewolf
Subtitle: Social deduction for 5–18 players
Button:   "Create New Match"
```

**Current create flow:**
- `POST /api/games` (line 18) → `{ game_id, host_secret }`
- `host_secret` written to `sessionStorage` (App.tsx:41)
- URL updated to `?g={game_id}` (App.tsx:42)

**Silent resume path (URL-param only):**
- `App.tsx:28`: reads `?g=` on load and bypasses `CreateMatchScreen`
- No UI exposes this — an operator at the TV cannot resume without manually editing the URL

### 2.2 Required Changes

**State additions to `CreateMatchScreen.tsx`:**
```
showResume   boolean   Toggle collapsible resume input panel
resumeId     string    Text input value for saved game ID
resumeError  string    Error message for resume path
```

**`host_secret` persistence change (App.tsx:41):**
- Remove: `sessionStorage.setItem(HOST_SECRET_KEY, newHostSecret)`
- Add: append `&host_secret={newHostSecret}` to the URL alongside `?g={gameId}`
- On load: read `host_secret` from URL params (alongside the existing `?g=` read)
- On resume: `host_secret` is absent from URL → Display knows it is in spectator mode for start authority

**Resume flow:**
- User expands panel, enters a `game_id`
- App navigates to `?g={resumeId}` — no `host_secret` in URL
- `CreateMatchScreen` exits; `LobbyScreen` renders; `hostSecret` prop is `null`

### 2.3 Gaps

| Gap | Current | Required |
|-----|---------|----------|
| Resume UI | Absent | Collapsible panel with `resumeId` input + `resumeError` |
| `host_secret` storage | `sessionStorage` | URL params only |

---

## 3. Join Page & Host Authority (Lobby)

### 3.1 Current Implementation

**File:** `frontend-display/src/components/LobbyScreen/LobbyScreen.tsx`

**Start button condition** (lines 103–113):
```typescript
hostSecret ? (
  <button disabled={!canStart || starting} onClick={handleStart}>
    ...
  </button>
) : (
  'Waiting for host to start…'
)
```

**Handler guard** (line 25):
```typescript
async function handleStart() {
    if (!hostSecret || !gameId || starting) return
    // POST /api/games/{gameId}/start with { host_secret }
}
```

**Disabled when:** `playerCount < 5` OR `starting` OR `!hostSecret`

**Valid Action Path (create flow only):**
- Display creates game → `host_secret` in sessionStorage → button renders and is callable
- On start: backend transitions `lobby → role_deal → night`; WebSocket broadcasts; App re-renders `NightScreen`

**Broken Path (resume flow):**
- `host_secret` is null → `'Waiting for host to start…'` rendered → no display-initiated start possible

### 3.2 Required Changes

**Start button visibility:**
- Remove the `hostSecret ?` ternary gate — button always renders when `!isDealing`
- Keep `disabled={!canStart || starting}` where `canStart = playerCount >= 5` (**unchanged**)

**`handleStart` handler:**
- Remove `!hostSecret` from the early-return guard
- When `hostSecret` is present (create flow): send `{ host_secret: hostSecret }` as before
- When `hostSecret` is absent (resume flow): send request without credential — backend accepts Display-origin start per spec §5 Key Design Constraints:
  > *"host_token (display host auth) and credentials (player auth) are both accepted by /start — either can launch the game"*

**`host_secret` source change:**
- Read from URL params on load (see §2.2) rather than sessionStorage
- Propagated from App.tsx to `LobbyScreen` as prop — interface unchanged

### 3.3 Gaps

| Gap | Current | Required |
|-----|---------|----------|
| Start button visibility | Gated on `hostSecret` truthy | Always visible (keep `canStart` ≥5 guard) |
| Handler guard | `!hostSecret` blocks call | Remove `!hostSecret` guard; allow no-credential start |
| `host_secret` source | sessionStorage | URL params (see §2.2) |

---

## 4. WebSocket: Message Types & Handshake

### 4.1 Current Implementation

**`useWebSocket.ts`** connects Display as:
```typescript
// useGameState.ts:19
const url = `${proto}//${window.location.host}/ws/${gameId}/${playerId}`
// called with playerId = 'display'
```

**`useGameState.ts`** handles one message type:
```typescript
if (msg.type === 'state_update') {
    if (msg.state_id > lastStateIdRef.current) {
        lastStateIdRef.current = msg.state_id
        setGameState(msg.state)
    }
}
```

### 4.2 Required Changes

**WS Handshake — Display identity (spec §6):**

Current (broken):
```typescript
player_id: 'display'
```
Required:
```typescript
{ type: "sync", match_id: gameId, player_id: null, credentials: null }
```

The Display connects as a spectator with no player identity. The backend uses `player_id: null` to identify it as the display client and routes stripped state accordingly.

**WS Message Types — full audit:**

| Event Direction | Current Type | Required Type | Notes |
|----------------|-------------|---------------|-------|
| Server → Client (full state) | `state_update` | `sync` | First broadcast after connect or start |
| Server → Client (incremental) | `state_update` | `update` | Subsequent phase/action events |
| Server → Client (lobby roster) | not handled | `match_data` | New: `{ type: "match_data", players: [...] }` |
| Server → Client (error) | `error` | `error` | Shape: `{ error: "UNAUTHORIZED" \| ... }` — unchanged |

**`useGameState.ts` handler update:**
```typescript
// Replace:
if (msg.type === 'state_update') { ... }

// With:
if (msg.type === 'sync' || msg.type === 'update') {
    if (msg.state_id > lastStateIdRef.current) {
        lastStateIdRef.current = msg.state_id
        setGameState(msg.state)
    }
}
if (msg.type === 'match_data') {
    // dispatch to Zustand store
    useGameStore.getState().setRoster(msg.players)
}
```

### 4.3 Gaps

| Gap | Current | Required |
|-----|---------|----------|
| Display WS identity | `player_id: 'display'` | `{ player_id: null, credentials: null }` |
| State message type (full) | `state_update` | `sync` |
| State message type (incremental) | `state_update` | `update` |
| Lobby roster events | not handled | `match_data` → Zustand `setRoster()` |

---

## 5. Lobby Roster Source

### 5.1 Current Implementation

`LobbyScreen.tsx` derives the player list from `gameState.players`:
```typescript
const players = Object.values(gameState.players)   // LobbyScreen.tsx:19
const playerCount = players.length                  // LobbyScreen.tsx:20
```

This means roster is only available after the first `state_update` resolves — there is no live join animation driven by discrete arrival events.

### 5.2 Required Change

Roster must be populated from `match_data` WebSocket events via Zustand store (spec §7):

```typescript
// Zustand store field:
roster: PlayerRosterEntry[]   // set by setRoster() on match_data
```

**`LobbyScreen.tsx` change:**
```typescript
// Replace:
const players = Object.values(gameState.players)

// With:
const players = useGameStore(state => state.roster)
```

The existing pop-in animation logic (`knownIdsRef`, `newIds` state at LobbyScreen.tsx:39–60) already fires on `players` array changes — it will continue to work once roster is sourced from Zustand and updated per `match_data` event.

### 5.3 Gap

| Gap | Current | Required |
|-----|---------|----------|
| Roster source | `gameState.players` (state_update) | Zustand `roster` (match_data events) |

---

## 6. Main Game Display State

### 6.1 Current Implementation

**File:** `frontend-display/src/App.tsx` (lines 128–150)

Phase-to-component routing is exhaustive and backend-driven:

```typescript
lobby / role_deal    → <LobbyScreen />
night                → <NightScreen audioUnlocked={audioUnlocked} />
day / day_vote /
  hunter_pending     → <DayScreen frozenVotes={frozenVotes} />
game_over            → <GameOverScreen audioUnlocked={audioUnlocked} />
```

**Transition handling:**
- `night → day`: 4-second `NightResolution` interstitial (App.tsx:65–68), non-skippable
- `day_vote → *`: `frozenVotes` snapshot (App.tsx:72–74) for VoteWeb reveal
- Phase changes drive CSS substrate swap via `document.documentElement.className` (App.tsx:56)

### 6.2 Conformance Assessment

Once `state_update` is replaced with `sync`/`update` (§4), the phase routing logic requires no changes. All FSM states have render paths. Interstitial, vote freeze, and CSS substrate transitions are correctly wired.

**No additional gaps in this area.**

---

## 7. ADR Compliance Validation

Each adopted change was checked against all six accepted ADRs.

---

### Change 1 — `host_secret` moves to URL params

**ADRs checked:** ADR-001, ADR-003, ADR-004, ADR-005, ADR-006

**Result: COMPLIANT**

No ADR governs `host_secret` storage location. ADR-003 §7 covers `localStorage`/`sessionStorage` for player-facing data (notepad, seer history) — not for the display's host credential. URL params are not prohibited by any decision record.

---

### Change 2 — WS message types: `state_update → sync / update`

**ADRs checked:** ADR-004, ADR-006

**Result: VIOLATES ADR-004 and ADR-006**

**ADR-004 §2** (Initial State Unicast on Connect) explicitly names `state_update` as the payload type the backend sends:
> *"Sends a `state_update` payload directly to the connecting WebSocket (unicast, not broadcast)."*

Changing the message type on the frontend without a coordinated backend change would silently break all state reception — `useGameState.ts` would never match the incoming message type and `gameState` would stay `null` forever.

**ADR-006 §3** (E2E tests) further hardens this — one of the verified E2E assertions is:
> *"`POST /api/games/{id}/start` triggers game queue processing and results in a `state_update` broadcast to the display WS"*

This change **requires a companion ADR** (or amendment to ADR-004) that renames the backend payload type from `state_update` to `sync`/`update` simultaneously with the frontend handler change. It cannot be a frontend-only change.

**Recommendation:** Block this change until the backend is updated and ADR-004 is amended. Record the intent as a new ADR or ADR-004 revision.

---

### Change 3 — Display WS handshake: `{ player_id: null, credentials: null }`

**ADRs checked:** ADR-004, ADR-006

**Result: VIOLATES ADR-004 and ADR-006**

**ADR-004 §3** (Display Client Authentication) mandates:
> *"The display client connects to `/ws/{game_id}/display`. The `player_id` path segment `"display"` is a sentinel value that bypasses session-token validation."*

The sentinel is the **URL path segment**, not a message body field. The backend identifies the display client from the URL (`/display`) and never inspects a `player_id` field in the handshake body. Sending `{ player_id: null }` in the body is harmless if the URL path remains `/ws/{game_id}/display` — but removing `'display'` from the URL path would break auth entirely.

**ADR-006 §2** integration tests also explicitly verify:
> *"The `player_id="display"` sentinel, the `AUTH_FAILED` error path, and the live-join broadcast were untested"* (pre-ADR-006) → now covered by integration tests that assert on the sentinel bypass

**What this means for the proposed change:**
The spec's `{ player_id: null, credentials: null }` describes the message body of the first sync message — this does not conflict with ADR-004 as long as the URL path remains `/ws/{game_id}/display`. The change is safe only if scoped to the **message body**, not the URL path. Current `useWebSocket.ts` sends `{ type: "auth", session_token: "..." }` on open — replacing this with `{ type: "sync", ..., player_id: null, credentials: null }` would require backend changes to the auth handler. ADR-004 describes the backend accepting the connection purely on the path sentinel, with no first-message auth step for the display client.

**Recommendation:** Clarify whether the backend currently expects a first-message handshake from the display client at all. If not, the proposed message body change is a no-op to the backend and can be dropped. If yes, a backend change is required before this can land.

---

### Change 4 — Roster from `match_data` events → Zustand store

**ADRs checked:** ADR-001, ADR-003, ADR-004, ADR-005, ADR-006

**Result: COMPLIANT — with test impact**

No ADR mandates `gameState.players` as the roster source for the lobby. This is a frontend-internal refactor.

**ADR-005 side effect:** The `FakeWebSocket` class used in `useWebSocket` tests would need a `triggerMessage` call with `{ type: "match_data", players: [...] }` to exercise the new handler. ADR-005 §3 anticipates this:
> *"The `FakeWebSocket` class must be updated if `useWebSocket` ever uses WebSocket features beyond..."*

This is expected maintenance cost, not a violation.

---

### Validation Summary

| Change | ADR Status | Blocker |
|--------|-----------|---------|
| `host_secret` → URL params | ✅ Compliant | None |
| WS message types `state_update → sync/update` | ❌ Violates ADR-004 §2 + ADR-006 E2E | Requires backend change + ADR-004 amendment before landing |
| Display WS handshake `{ player_id: null }` | ⚠️ Conditionally compliant | Safe only if URL path `/ws/{game_id}/display` is unchanged; backend first-message handling must be verified |
| Roster from `match_data` → Zustand | ✅ Compliant | FakeWebSocket test update required (expected, not a violation) |

---

## 8. Recommendations Summary

| Priority | Area | File | Action | ADR Gate |
|----------|------|------|--------|----------|
| P0 | Landing — Resume UI | `CreateMatchScreen.tsx` | Add `showResume` / `resumeId` / `resumeError` state + collapsible resume panel | None |
| P0 | Landing — Persistence | `App.tsx:41` | Move `host_secret` from sessionStorage to URL params | None |
| P0 | Lobby — Start button | `LobbyScreen.tsx:103` | Remove `hostSecret ?` ternary; always render button | None |
| P0 | Lobby — Handler | `LobbyScreen.tsx:25` | Remove `!hostSecret` guard; allow no-credential start | None |
| **BLOCKED** | WS — Message types | `useGameState.ts` | `state_update → sync/update`; add `match_data` handler | **Amend ADR-004 + backend change first** |
| **VERIFY** | WS — Handshake | `useGameState.ts:19` | Confirm backend expects no first-message from display; if no-op, drop change | **Verify ADR-004 §3 auth flow** |
| P1 | Lobby — Roster | `LobbyScreen.tsx:19` + Zustand store | Source `players` from `roster` Zustand field via `match_data` events | Depends on `match_data` WS change landing |

---

## 9. File Reference

| File | Lines | Notes |
|------|-------|-------|
| `frontend-display/src/components/CreateMatchScreen/CreateMatchScreen.tsx` | 37–55 | Add resume state + UI |
| `frontend-display/src/components/LobbyScreen/LobbyScreen.tsx` | 19–20, 25, 103–113 | Remove hostSecret guard; switch roster source |
| `frontend-display/src/App.tsx` | 28–44, 128–150 | Move host_secret to URL params |
| `frontend-display/src/hooks/useGameState.ts` | 12–49 | WS handshake + message type handlers |
| `docs/architecture/adr/ADR-004_websocket_connection_protocol.md` | §2, §3 | Governs `state_update` type and display sentinel — must be amended before WS type changes land |
| `docs/architecture/adr/ADR-006_integration_e2e_cicd.md` | §3 E2E | E2E test asserts on `state_update` broadcast — will break if type changes without backend update |
| `FrontendDisplayDesign.md` | §5–8 | Backend endpoint auth, WS protocol, data flow |
