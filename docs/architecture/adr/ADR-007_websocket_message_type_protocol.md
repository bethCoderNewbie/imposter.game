# ADR-007: Werewolf — WebSocket Message Type Protocol Revision

## Status
Proposed

## Date
2026-03-27

## Context

ADR-004 resolved two bugs in the Display TV's WebSocket connection path (double `ws.accept()` crash; no initial state push on connect). In doing so it established a protocol with a single server-to-client message type — `state_update` — used for both the initial state unicast on connect and for every subsequent per-action broadcast.

A separate design document (`FrontendDisplayDesign.md`) specifies a different protocol using three message types: `sync` (full state push), `update` (incremental state push), and `match_data` (lobby roster events). This created two tracked violations flagged during the Part 1 Display Flow research pass:

1. **`state_update → sync / update`** (ADR compliance: blocked). ADR-004 §2 explicitly names `state_update`; the design spec calls for `sync` and `update`. The research concluded this cannot be a frontend-only change — it requires a coordinated backend rename.

2. **Display WS handshake `{ player_id: null, credentials: null }`** (ADR compliance: needs verification). ADR-004 §3 states the display client is identified by the URL path sentinel `/display`, not by a message body field. The spec's proposed body payload conflicted.

Before writing this ADR, the following was verified against the actual source:

**Backend — two hardcoded sites:**
- `api/ws/endpoint.py:106` — initial unicast uses `"type": "state_update"`
- `api/connection_manager.py:54` — every broadcast uses `"type": "state_update"`

Both send the same payload shape: `{ type, state_id, schema_version, state }`.

**Test surface — 9 assertions at risk:**
- `tests/api/test_websocket_integration.py`: lines 21, 103, 137
- `tests/e2e/test_full_game_flow.py`: lines 73, 102, 135 (three separate assertions)
- Plus the E2E assertion explicitly referenced in ADR-006 §3: *"`POST /api/games/{id}/start` triggers game queue processing and results in a `state_update` broadcast to the display WS"*

**Frontend — one handler:**
- `frontend-display/src/hooks/useGameState.ts:24`: `if (msg.type === 'state_update')`

**Display client first-message behavior — confirmed no-op:**
- `useWebSocket.ts:47`: `if (sessionToken) { ws.send(...) }` — the display client is called with no `sessionToken`; the `if` guard prevents any first message from being sent.
- The backend for `player_id == "display"` pushes `state_update` immediately without reading a first message.
- The spec's proposed `{ player_id: null, credentials: null }` body payload has no effect on the current backend. If sent, the backend would receive it in the receive loop as an unrecognised intent and silently drop it. It is not needed and not adopted.

---

## Decision

### 1. Rename `state_update` to `sync` for the initial unicast

The initial state push that the backend sends immediately after a client connects (or reconnects) will use message type `sync`. This push represents the **complete current game state** as of the moment of connection — it is a full replacement, not a diff.

**Backend change:** `api/ws/endpoint.py:106`
```python
# Before
{"type": "state_update", "state_id": ..., "schema_version": ..., "state": ...}

# After
{"type": "sync", "state_id": ..., "schema_version": ..., "state": ...}
```

### 2. Rename `state_update` to `update` for per-action broadcasts

Every broadcast triggered by a game intent (player action, phase timeout, system event) will use message type `update`. This push also carries the full current state (the backend has no diff/patch mechanism), but the `update` type signals to clients that the state changed in response to a game event — appropriate for triggering animations, sound effects, or conditional UI transitions.

**Backend change:** `api/connection_manager.py:54`
```python
# Before
{"type": "state_update", "state_id": ..., "schema_version": ..., "state": ...}

# After
{"type": "update", "state_id": ..., "schema_version": ..., "state": ...}
```

The payload shape — `{ type, state_id, schema_version, state }` — is **unchanged** for both types. The `state_id` monotonic fence, the `schema_version` field, and the `player_view`-stripped state are all preserved.

### 3. Update the TypeScript shared type definition

`api/schemas/shared_types.ts` currently defines one interface `StateUpdateMessage`. This is split into two:

```typescript
// Before
interface StateUpdateMessage {
  type: "state_update";
  state_id: number;
  schema_version: string;
  state: MasterGameState;
}
type ServerMessage = StateUpdateMessage | ErrorMessage | HintRewardMessage;

// After
interface SyncMessage {
  type: "sync";
  state_id: number;
  schema_version: string;
  state: MasterGameState;
}

interface UpdateMessage {
  type: "update";
  state_id: number;
  schema_version: string;
  state: MasterGameState;
}

type ServerMessage = SyncMessage | UpdateMessage | ErrorMessage | HintRewardMessage;
```

### 4. Update the frontend message handler

`frontend-display/src/hooks/useGameState.ts:24`:

```typescript
// Before
if (msg.type === 'state_update') {
    if (msg.state_id > lastStateIdRef.current) {
        lastStateIdRef.current = msg.state_id
        setGameState(msg.state)
    }
}

// After
if (msg.type === 'sync' || msg.type === 'update') {
    if (msg.state_id > lastStateIdRef.current) {
        lastStateIdRef.current = msg.state_id
        setGameState(msg.state)
    }
}
```

The `state_id` fence logic is unchanged. Both types carry the same payload and are processed identically for the purposes of state management. Future callers may differentiate on `msg.type` to trigger event-specific effects (e.g., play a sound only on `update`, not on `sync`).

### 5. `match_data` message type — deferred

The spec defines a `match_data` type for lobby roster events. Adopting `match_data` requires:
- A new backend broadcast path in the lobby phase (distinct from the game-state broadcast)
- A Zustand store for the display client's lobby roster
- Removal of the lobby roster from `gameState.players`

This is a larger change with its own test surface and is not bundled here. It will be addressed in a separate ADR when the lobby redesign sprint begins.

### 6. Display client WS handshake — no change

The display client's authentication mechanism (URL path sentinel `/display`, backend skips token validation for this path segment) is correct and remains unchanged per ADR-004 §3.

The spec's proposed `{ player_id: null, credentials: null }` first message is **explicitly rejected**:
- The display client currently sends no first message (`useWebSocket.ts:47` guards on `sessionToken`, which is `undefined` for the display).
- The backend never reads a first message from the display path before pushing state.
- If sent, this payload would arrive in the backend receive loop as an unrecognised intent and be silently dropped — it has no effect and adds noise.
- The URL sentinel is the correct and sufficient mechanism for display client identification.

---

## Consequences

### Backend

- `api/ws/endpoint.py` — one line changed (`state_update` → `sync`)
- `api/connection_manager.py` — one line changed (`state_update` → `update`)
- `api/schemas/shared_types.ts` — `StateUpdateMessage` split into `SyncMessage` + `UpdateMessage`; `ServerMessage` union updated

### Frontend

- `frontend-display/src/hooks/useGameState.ts` — one condition changed (`'state_update'` → `'sync' || 'update'`)
- `frontend-display/src/types/game.ts` — `ServerMessage` union must be updated to match the new TypeScript interface (remove `state_update`, add `sync` and `update`)

### Tests — 9 assertions require updates

| File | Lines | Change |
|------|-------|--------|
| `tests/api/test_websocket_integration.py` | 21 | `state_update` → `sync` (initial connect unicast) |
| `tests/api/test_websocket_integration.py` | 103 | `state_update` → `sync` (player initial auth state) |
| `tests/api/test_websocket_integration.py` | 137 | `state_update` → `update` (broadcast after join REST call) |
| `tests/e2e/test_full_game_flow.py` | 73 | `state_update` → `sync` (display initial connect) |
| `tests/e2e/test_full_game_flow.py` | 102 | `state_update` → `sync` (player initial connect) |
| `tests/e2e/test_full_game_flow.py` | 135 | `state_update` → `update` (ROLE_DEAL broadcast after start) |
| `tests/e2e/test_full_game_flow.py` | (ADR-006 §3 ref) | Same as line 135 — ROLE_DEAL post-start broadcast |

**Rule for disambiguation:** `sync` is the type for the initial unicast on connect (endpoint.py). `update` is the type for every broadcast triggered by a game event (connection_manager.py). Any test that asserts on a message received immediately after `websocket_connect()` without a prior game action → `sync`. Any test that asserts on a message received after a POST or intent → `update`.

### ADR-004 Amendment

ADR-004 §2 states: *"Sends a `state_update` payload directly to the connecting WebSocket (unicast, not broadcast)."*

This sentence is superseded by ADR-007. The pattern (unicast on connect, full stripped state, `state_id` fence) is unchanged; only the `type` field value changes from `state_update` to `sync`. ADR-004 §3 (display sentinel, accept-once rule) is unaffected.

### Positive

- Protocol terminology matches the design spec, eliminating future confusion between initial-load messages and game-event messages.
- Clients can cheaply distinguish a reconnect state-sync (`sync`) from a game-driven state change (`update`) by inspecting `msg.type` — without comparing state IDs or diffing payloads.
- The split lays groundwork for future optimisation: `update` messages could carry a delta payload instead of the full state, with `sync` always carrying the full baseline. No such optimisation is implemented now.

### Negative

- This is a **flag day change** — old frontend + new backend (or vice versa) will silently stop receiving state. Both sides must be deployed together. The Docker Compose deployment model (`docker compose up --build`) makes this atomic; partial deploys are not possible in the current self-hosting setup.
- 9 test assertions must be updated in the same commit. The update is mechanical (string replacement) but if missed the integration suite will fail loudly, which is the correct failure mode.
- The `FakeWebSocket` test class (ADR-005 §3) does not need changes — it operates below the message-type layer.
