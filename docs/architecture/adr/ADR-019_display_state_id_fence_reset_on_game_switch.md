# ADR-019: Reset State-ID Fence on Game Switch — Display & Mobile (Rematch Bug)

## Status
Accepted

## Date
2026-04-13

## Context

### The Bug

Both the Display and Mobile clients share an identical `lastStateIdRef` fence in their respective `useGameState` hooks. This fence silently dropped all state messages from a new game after a rematch redirect, leaving both clients frozen on the old `game_over` screen.

**Root cause (present in both hooks):** `useGameState.ts` maintains a `lastStateIdRef` — a monotonically-increasing fence used to discard out-of-order or replayed state messages:

```ts
if (msg.state_id > lastStateIdRef.current) {
  lastStateIdRef.current = msg.state_id
  setGameState(msg.state)
}
```

This fence is **never reset** when `gameId` changes. A game that ran for several rounds might reach `state_id = 100`. When either client switches to a new game, the new game starts at `state_id = 1`. The condition `1 > 100` is `false`, so every sync message from the new game is silently dropped. The stale `gameState` persists, keeping `phase === 'game_over'` and rendering `GameOverScreen` indefinitely.

**Display client** — affected transitions:
- **Play Again**: `handlePlayAgain` → `setGameId(newGameId)` → WebSocket reconnects → new-game messages dropped
- **New Match → Create**: `setGameId(null)` → then `setGameId(createdGameId)` → same drop

**Mobile client** — affected transition:
- **Rematch redirect received**: backend broadcasts `{ type: "redirect", new_game_id, players }` to all live sockets on the old game → `handleRedirect` in `App.tsx` updates `session` with new `game_id` + `player_id` + `session_token` → `useGameState` gets new `gameId` → WebSocket reconnects to new game → `state_id = 1` sync is dropped by the stale fence → mobile stays on old `game_over` screen

**Secondary issue (Display only):** `onNewMatch` in `App.tsx` used `history.pushState({}, '', '/')`, which is wrong in production where the Vite build base is `/display/`. After "New Match", the React SPA keeps running correctly (state-driven, no reload), but if the user refreshes the browser at `/`, nginx serves the wrong document. The correct URL is `import.meta.env.BASE_URL`.

---

## Decision

### 1. Reset the state-id fence and game state when `gameId` changes

**Changed:** both `frontend-display/src/hooks/useGameState.ts` and `frontend-mobile/src/hooks/useGameState.ts`

Added a single `useEffect` that fires whenever `gameId` changes (identical in both hooks):

```ts
useEffect(() => {
  lastStateIdRef.current = -1
  setGameState(null)
}, [gameId])
```

- `lastStateIdRef.current = -1` resets the fence so any `state_id ≥ 0` from the new game is accepted.
- `setGameState(null)` clears the stale game state, preventing the old `game_over` screen from persisting during reconnection.

**Rejected alternatives:**
- *Pass `gameId` as a render key to `App`*: Would force full unmount/remount of the entire app tree, losing audio unlock state and causing a flash. Disproportionate.
- *Clear stale state only in the `onPlayAgain`/`onNewMatch` handlers*: Fragile — the reset must live co-located with the fence, not dispersed across callers. Every future game-switch path would need to be updated manually.
- *Check `game_id` field in the incoming state message*: The `sync` message payload includes the game's `game_id`. We could compare and discard cross-game messages. But this is defense-in-depth, not a replacement — the fence still needs resetting, and comparing game IDs adds coupling to the message schema.

### 2. Fix `onNewMatch` base URL

**Changed:** `frontend-display/src/App.tsx:177`

```diff
- history.pushState({}, '', '/')
+ history.pushState({}, '', import.meta.env.BASE_URL)
```

`import.meta.env.BASE_URL` is `/` in development and `/display/` in production (set by `vite.config.ts` `base` option).

---

## Consequences

**Positive:**
- "Play Again" now works end-to-end: Display triggers rematch → mobile receives redirect → both clients navigate to the new game's lobby.
- "New Match → Create New Match" also works on the Display client.
- The fix is minimal (one `useEffect` per hook, one URL fix) with no changes to the backend or WebSocket protocol.
- Regression tests added to both hooks' test files:
  - `resets gameState to null when gameId changes`
  - `accepts low state_id from new game after gameId change` / `...after redirect (rematch scenario)`

**Negative / Trade-offs:**
- The `useEffect` on `gameId` introduces a momentary `gameState = null` render between the old and new game states. This causes a brief "Connecting…" flash. This is correct behavior — the display is genuinely connecting to a different game — and it is shorter than the WebSocket handshake latency.
- If `gameId` changes identity without the game actually changing (edge case: host re-enters the same game ID via the Resume flow), the state is unnecessarily cleared. This is harmless — the WebSocket will reconnect and the server will send a fresh `sync`.

---

## Related

- ADR-013: Mobile session persistence & rematch redirect forwarding (the backend side of the rematch flow)
- PRD-011: Display pre-game settings (the UX feature delivered in the same change set)
