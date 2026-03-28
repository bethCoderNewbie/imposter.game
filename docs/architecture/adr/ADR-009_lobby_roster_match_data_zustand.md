# ADR-009: Werewolf — Lobby Roster Broadcast via `match_data` and Zustand Store

## Status
Accepted

## Date
2026-03-27

## Context

`LobbyScreen.tsx` currently derives its player list directly from `gameState.players`:

```typescript
const players = Object.values(gameState.players)  // LobbyScreen.tsx:19
```

`gameState` is populated by `sync` and `update` WS messages, which carry the full stripped `MasterGameState`. This means the lobby roster only updates when a full state broadcast arrives — specifically, when `POST /api/games/{id}/join` triggers `manager.broadcast()`, which sends an `update` to every connected socket.

This model has three tracked problems:

1. **No discrete arrival events.** `LobbyScreen` detects new players by diffing the `players` object on every render via `knownIdsRef` (lines 39–60). This is a manual diff driven by the full-state polling cadence, not by a server-side join event. If the `update` message is batched or delayed, the diff fires late.

2. **Roster tightly coupled to game state shape.** The pop-in animation depends on `PlayerState.player_id` being stable across renders. Any change to the `MasterGameState` shape (e.g., player ordering, map → array refactor) silently breaks the diff.

3. **Design spec mismatch.** `FrontendDisplayDesign.md` §7 specifies a dedicated `match_data` WS message type for lobby roster events with a Zustand store as the client-side source of truth. This gap was flagged in `2026-03-27_display-flow-part1.md` §5 and deferred in ADR-007 §5.

**Current state (post-ADR-007):**
- `useGameState.ts:24` handles `sync | update` → `setGameState(msg.state)`
- No Zustand dependency in `frontend-display/package.json`
- `LobbyScreen.tsx:19` reads `Object.values(gameState.players)`
- `FakeWebSocket` test class (ADR-005 §3) needs a `triggerMessage` call for `match_data` to exercise the new handler — anticipated in ADR-005 §3: *"The FakeWebSocket class must be updated if useWebSocket ever uses WebSocket features beyond..."*

---

## Decision

### 1. New `match_data` Backend Broadcast

A new server-to-client WS message type `match_data` is introduced for lobby roster events. It is broadcast whenever the lobby player list changes — player joins, player disconnects, player reconnects — during the `lobby` phase only.

**Payload shape:**

```typescript
interface MatchDataMessage {
  type: "match_data";
  players: PlayerRosterEntry[];
}

interface PlayerRosterEntry {
  player_id: string;
  display_name: string;
  avatar_id: string;
  is_connected: boolean;
}
```

`PlayerRosterEntry` is a strict subset of `PlayerState`. It intentionally omits `role`, `team`, `night_action_submitted`, `vote_target_id`, and all server-only fields. This is the minimum needed for the lobby avatar parade.

**Backend broadcast sites** (three locations in `api/lobby/routes.py`):

```python
# After POST /api/games/{id}/join:
await manager.broadcast_roster(game_id, list(G.players.values()))

# After POST /api/games/{id}/rejoin:
await manager.broadcast_roster(game_id, list(G.players.values()))
```

**No broadcast on disconnect** during the lobby: the WebSocket `on_disconnect` handler in `endpoint.py` enqueues `player_disconnected` to the game queue, which is not processed during lobby phase. Disconnect visibility during the lobby is handled by the periodic `is_connected` flag in the next `update` broadcast (triggered by the next REST action). If real-time disconnect visibility is needed in the lobby, it can be added in a follow-up.

**New `ConnectionManager` method** (`api/connection_manager.py`):

```python
async def broadcast_roster(self, game_id: str, players: list[PlayerState]) -> None:
    """Sends a match_data roster event to all sockets in the lobby room."""
    room = self._rooms.get(game_id, {})
    payload = {
        "type": "match_data",
        "players": [
            {
                "player_id": p.player_id,
                "display_name": p.display_name,
                "avatar_id": p.avatar_id,
                "is_connected": p.is_connected,
            }
            for p in players
        ],
    }
    text = json.dumps(payload)
    dead_sockets: list[str | None] = []
    for pid, ws in list(room.items()):
        try:
            await ws.send_text(text)
        except (WebSocketDisconnect, RuntimeError):
            dead_sockets.append(pid)
    for pid in dead_sockets:
        self._rooms[game_id].pop(pid, None)
```

Unlike `broadcast()`, `broadcast_roster()` sends the same payload to all sockets (no per-socket `player_view()` stripping — roster entries contain no secret fields).

### 2. Backend TypeScript Schema

`api/schemas/shared_types.ts` — add after the existing message interfaces:

```typescript
export interface PlayerRosterEntry {
  player_id: string;
  display_name: string;
  avatar_id: string;
  is_connected: boolean;
}

export interface MatchDataMessage {
  type: "match_data";
  players: PlayerRosterEntry[];
}

// Updated ServerMessage union:
export type ServerMessage =
  | SyncMessage
  | UpdateMessage
  | MatchDataMessage
  | ErrorMessage
  | HintRewardMessage;
```

### 3. Add Zustand to `frontend-display`

```bash
npm install zustand
```

**New store file: `frontend-display/src/store/gameStore.ts`**

```typescript
import { create } from 'zustand'
import type { PlayerRosterEntry } from '../types/game'

interface GameStore {
  roster: PlayerRosterEntry[]
  setRoster: (players: PlayerRosterEntry[]) => void
}

export const useGameStore = create<GameStore>((set) => ({
  roster: [],
  setRoster: (players) => set({ roster: players }),
}))
```

The store is intentionally minimal for this ADR. It holds only the roster. Future ADRs (game balance config, timer config) may extend it.

### 4. Update Frontend Type Definitions

`frontend-display/src/types/game.ts` — add `PlayerRosterEntry` and `MatchDataMessage` interfaces; extend `ServerMessage` union:

```typescript
export interface PlayerRosterEntry {
  player_id: string
  display_name: string
  avatar_id: string
  is_connected: boolean
}

export interface MatchDataMessage {
  type: 'match_data'
  players: PlayerRosterEntry[]
}

export type ServerMessage = SyncMessage | UpdateMessage | MatchDataMessage | ErrorMessage
```

### 5. Update `useGameState.ts` Message Handler

`frontend-display/src/hooks/useGameState.ts` — extend `handleMessage` to handle `match_data` and seed roster from `sync`:

```typescript
import { useGameStore } from '../store/gameStore'

const handleMessage = useCallback((data: unknown) => {
  const msg = data as ServerMessage

  if (msg.type === 'sync' || msg.type === 'update') {
    if (msg.state_id > lastStateIdRef.current) {
      lastStateIdRef.current = msg.state_id
      setGameState(msg.state)
      // Seed roster from full state on initial sync
      if (msg.type === 'sync') {
        useGameStore.getState().setRoster(Object.values(msg.state.players))
      }
    }
  }

  if (msg.type === 'match_data') {
    useGameStore.getState().setRoster(msg.players)
  }

  if (msg.type === 'error') {
    console.warn('[WS error]', msg.code, msg.message)
  }
}, [])
```

**Roster seeding on `sync`:** When the display client connects (or reconnects), it receives a `sync` with the full current state. The Zustand roster is seeded from `sync.state.players` so the lobby is populated immediately, before the first `match_data` arrives. Subsequent joins update the store via `match_data`.

**`update` does not re-seed roster.** `update` messages carry the full state but roster changes during an active game (e.g., player disconnect mid-night) are not displayed in `LobbyScreen` (it is unmounted during non-lobby phases). Re-seeding roster on every `update` would be harmless but unnecessary.

### 6. Update `LobbyScreen.tsx` Roster Source

Replace the `gameState.players` derivation with Zustand store access:

```typescript
// Before (LobbyScreen.tsx:19-20)
const players = Object.values(gameState.players)
const playerCount = players.length

// After
import { useGameStore } from '../../store/gameStore'
// ...
const players = useGameStore(state => state.roster)
const playerCount = players.length
```

The existing pop-in animation logic (`knownIdsRef`, `newIds`, `useEffect`) at lines 39–60 **remains unchanged** — it already fires on `players` array reference changes, which now happen on each `match_data` dispatch.

The `useEffect` dependency array `[players.map(p => p.player_id).join(',')]` continues to work because `PlayerRosterEntry` has `player_id`.

### 7. `match_data` — Deferred: Phase Scope

`match_data` is broadcast only from lobby REST endpoints. No `match_data` is sent during active game phases (`night`, `day`, etc.). During active phases, `update` messages contain `state.players` which includes `is_connected` flags — mobile clients use this for their own player lists. This scope restriction keeps the broadcast surface minimal and avoids a `match_data` flood during gameplay.

---

## Consequences

### Backend

- `api/connection_manager.py` — new `broadcast_roster()` method
- `api/lobby/routes.py` — two new `await manager.broadcast_roster()` calls (join, rejoin)
- `api/schemas/shared_types.ts` — `PlayerRosterEntry`, `MatchDataMessage` interfaces; `ServerMessage` union extended

### Frontend

- `frontend-display/package.json` — add `zustand` dependency
- `frontend-display/src/store/gameStore.ts` — new file (Zustand store)
- `frontend-display/src/types/game.ts` — `PlayerRosterEntry`, `MatchDataMessage`; `ServerMessage` union extended
- `frontend-display/src/hooks/useGameState.ts` — `match_data` handler + `sync` roster seeding
- `frontend-display/src/components/LobbyScreen/LobbyScreen.tsx` — roster source changed to `useGameStore`

### Tests — New assertions required

| File | Change |
|------|--------|
| `tests/api/test_websocket_integration.py` | New: display receives `match_data` after player joins |
| `tests/e2e/test_full_game_flow.py` | New: display receives `match_data` with correct player list |
| `frontend-display/src/test/hooks/useGameState.test.ts` | New: `match_data` dispatches to store; `sync` seeds roster |
| `frontend-display/src/test/components/LobbyScreen.test.tsx` | Update: roster from store, not gameState |

`FakeWebSocket` in `useWebSocket.test.ts` needs no changes — `triggerMessage()` already supports arbitrary payloads. The handler tests use `triggerMessage({ type: 'match_data', players: [...] })` directly.

### Positive

- Lobby roster updates are driven by discrete server-side join events, not full-state diffs.
- Pop-in animation no longer requires manual diffing of `gameState.players` — `match_data` arrival *is* the animation trigger.
- `LobbyScreen` is decoupled from `StrippedGameState` shape for the roster field — `PlayerRosterEntry` is a stable minimal contract.
- Zustand store is now available for future ADRs (game config controls, timer state).

### Negative

- Display clients receive two message types on every join: `update` (full game state) and `match_data` (roster). The duplication is intentional — `update` serves non-lobby game phases; `match_data` serves the lobby roster specifically. If bandwidth becomes a concern, `update` could be suppressed for the display during lobby phase in a future optimization.
- `sync` seeds the roster from `msg.state.players`, which is the *stripped* display view of `PlayerState`. `PlayerRosterEntry` fields (`player_id`, `display_name`, `avatar_id`, `is_connected`) are all present in the stripped display view (none are server-only), so this is safe.
- Adding Zustand adds a new dependency. `zustand@^4` has no React peer dependency version constraints that conflict with `react@18`.
