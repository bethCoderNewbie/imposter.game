---
title: WebSocket Real-Time Sync Bug — Root Cause Analysis
date: 2026-04-19
branch: main
researcher: bethCoderNewbie
---

## Problem Statement

Both `frontend-mobile` and `frontend-display` require a full page refresh to pick up game state changes. WebSocket connections are established and stay open, but incoming state broadcasts are silently dropped after a reconnect.

---

## Root Cause 1 (PRIMARY): State Fence Not Reset on Reconnect

### Where
`frontend-mobile/src/hooks/useGameState.ts:30–34`  
`frontend-display/src/hooks/useGameState.ts:28–30` (identical pattern)

### What the code does
```ts
const lastStateIdRef = useRef(-1)

// Only resets when gameId changes (rematch guard):
useEffect(() => {
  lastStateIdRef.current = -1
  setGameState(null)
}, [gameId])

// Fence check on every incoming message:
if (msg.state_id > lastStateIdRef.current) {
  lastStateIdRef.current = msg.state_id
  setGameState(msg.state)
}
```

### Why it breaks

When a WebSocket drops and **reconnects to the same game** (no `gameId` change), `lastStateIdRef` retains its last value. The backend always sends a `sync` message on new connections containing the current `state_id`.

Example trace:
1. Frontend is live: `lastStateIdRef.current = 50`
2. Network hiccup — WebSocket closes
3. `useWebSocket` reconnects (exponential backoff, 1–30 s)
4. Backend sends `{ type: "sync", state_id: 50, state: {...} }`
5. Fence check: `50 > 50` → **false** → message silently dropped
6. Frontend is now frozen at its pre-disconnect snapshot

A manual page refresh re-initializes `useRef(-1)`, so `50 > -1` passes and the sync is accepted.

### Why it doesn't self-heal

`useWebSocket` (`useWebSocket.ts:61–71`) correctly reconnects with exponential backoff. But on each reconnect, the backend sends the same `state_id` (nothing changed while the client was offline). Since no new actions advance the `state_id` past `lastStateIdRef.current`, every subsequent sync is also rejected until the game progresses to a new action.

---

## Root Cause 2 (SECONDARY): Double `state_id` Increment

### Where
`backend-engine/api/game_queue.py:92` — queue always increments  
`backend-engine/api/intents/handlers.py:546, 669, 758, 814, 937, 970` — six handlers also increment

### What happens
```python
# In game_queue.py:
G_new = await dispatch_fn(G, intent, ...)  # handler may increment internally
G_new.state_id += 1                        # queue always increments again
await connection_manager.broadcast(game_id, G_new)
```

For `handle_phase_timeout` specifically (line 546):
1. Handler: `G.state_id += 1` (N → N+1), then `await cm.broadcast(...)` at state_id=N+1
2. Queue: `G_new.state_id += 1` (N+1 → N+2), then broadcasts at state_id=N+2
3. Frontend receives **two broadcasts** for one action: N+1 then N+2

For the other five handlers (grid_node, grid_answer, sonar, charge, defend):
1. Handler: `G.state_id += 1` (N → N+1), does NOT broadcast
2. Queue: `G_new.state_id += 1` (N+1 → N+2), broadcasts N+2
3. Frontend receives only N+2; state_id skipped a value

### Impact
- State_id advances by 2 per affected action instead of 1
- `handle_phase_timeout` sends the same game state twice per phase transition (wasted broadcast, minor bandwidth)
- The drift accelerates the scenario in Root Cause 1: a reconnect is more likely to produce a state_id that already matches `lastStateIdRef`
- The intent fence check (`intent_state_id != G.state_id` in `game_queue.py:67`) can reject valid client intents if the client sends an intent tagged with state_id=N+1 but the server has advanced to N+2

---

## Root Cause 3 (MINOR): Fire-and-Forget Broadcast

### Where
`backend-engine/api/intents/handlers.py:151–153`

```python
asyncio.create_task(
    cm.broadcast_raw(G.game_id, {"type": "wolf_kill_queued"})
)
```

This sound-trigger event is fire-and-forget. If the event loop is busy, the broadcast may arrive after the state update that reflects the wolf vote, or be silently dropped on WebSocket error. Not a realtime-sync regression but a reliability gap.

---

## What Works Correctly

| Component | Status | Notes |
|-----------|--------|-------|
| WebSocket upgrade (nginx) | ✅ Correct | `Upgrade`/`Connection` headers set, `proxy_read_timeout 3600s` |
| Reconnect with backoff | ✅ Correct | `useWebSocket.ts:68–70`, 1 s → 30 s exponential |
| Auth on reconnect | ✅ Correct | `session_token` sent immediately on `ws.onopen` |
| Single uvicorn worker | ✅ No issue | No multi-worker broadcast fan-out problem |
| Cloudflare Tunnel SSL | ✅ Fixed | Resolved in INC-002 (2026-04-17) |
| State stripper security | ✅ Correct | No role data leaking |

---

## Fix Plan

### Fix 1 — Reset fence on reconnect (PRIMARY, both frontends)

In `useGameState.ts`, replace the bare `setStatus` passed to `onStatusChange` with a handler that also resets the fence:

```ts
// frontend-mobile/src/hooks/useGameState.ts
const handleStatusChange = useCallback((s: WsStatus) => {
  if (s === 'open') lastStateIdRef.current = -1
  setStatus(s)
}, [])

const { send } = useWebSocket({
  url,
  sessionToken,
  onMessage: handleMessage,
  onStatusChange: handleStatusChange,   // was: setStatus
})
```

Apply the same change to `frontend-display/src/hooks/useGameState.ts`.

**Why this is safe:** The fence resets to -1 at the moment the socket opens, before the backend sends the `sync` message (the auth round-trip adds ~1 ms of ordering). Every sync/update that arrives after open will pass `state_id > -1`.

### Fix 2 — Single point of `state_id` increment (SECONDARY, backend)

Remove the six internal `G.state_id += 1` lines from handlers. The queue at `game_queue.py:92` is the sole authority.

For `handle_phase_timeout` (line 546–547): remove the increment AND the `await cm.broadcast(...)` inside the handler. The queue will broadcast after the handler returns.

```python
# handlers.py — handle_phase_timeout, around line 546
# REMOVE:
G.state_id += 1
await cm.broadcast(G.game_id, G)
# The queue handles both after this handler returns.
```

Same removal for lines 669, 758, 814, 937, 970 (remove only the `G.state_id += 1`; these don't have internal broadcasts).

### Fix 3 — Await the wolf_kill_queued broadcast (MINOR)

```python
# handlers.py line 151
# Change from:
asyncio.create_task(cm.broadcast_raw(G.game_id, {"type": "wolf_kill_queued"}))
# To:
await cm.broadcast_raw(G.game_id, {"type": "wolf_kill_queued"})
```

---

## Files to Change

| File | Change |
|------|--------|
| `frontend-mobile/src/hooks/useGameState.ts` | Reset fence on `status === 'open'` |
| `frontend-display/src/hooks/useGameState.ts` | Same |
| `backend-engine/api/intents/handlers.py:546,669,758,814,937,970` | Remove internal `state_id +=1`; remove handler-internal broadcast at 547 |
| `backend-engine/api/intents/handlers.py:151` | Await `broadcast_raw` |
