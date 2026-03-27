---
title: Display Dark Background — Debug Report
date: 2026-03-27
symptom: http://192.168.68.182/display/ shows only a dark background, never renders game UI
status: Fixed
---

# Display Dark Background — Debug Report

## Symptom

`http://192.168.68.182/display/` shows a persistent dark background. The React app loads
(the "Click to Begin" overlay appears), but after clicking, the display never transitions to
a game screen — it stays on "Connecting…" or "Waiting for game…".

---

## Root Causes Found

### Bug 1 — Double `ws.accept()` (Critical)

**Files:**
- `backend-engine/api/ws/endpoint.py:38`
- `backend-engine/api/connection_manager.py:30` (now fixed)

**What happened:**

The WebSocket endpoint calls `await websocket.accept()` at line 38 (correct — needed so
auth error messages can be sent before the connection is closed). It then calls
`await manager.connect(game_id, ...)` at line 91.

`ConnectionManager.connect()` called `await ws.accept()` a second time on the same socket.
Sending two ASGI `websocket.accept` events to uvicorn for a single connection causes the
server to raise a `RuntimeError`. This exception propagated back to FastAPI's WebSocket
handler, which closed the connection. The socket was never registered in
`manager._rooms[game_id]`, so no broadcasts were ever delivered to the display client.

**Flow before fix:**
```
Browser                 nginx               backend
  |--- WS upgrade ------->|--- WS upgrade -->|
  |<-- 101 Switching ------| <-- 101 ---------|   endpoint.py:38  ws.accept() ✓
  |                        |                  |   manager.connect()
  |                        |                  |     ws.accept() ← SECOND TIME → RuntimeError
  |<-- connection closed --|<-- close --------|
  |  (display stuck on "Connecting…", retries MAX_RETRIES=5 times then gives up)
```

**Fix:** Removed `await ws.accept()` from `ConnectionManager.connect()`.
The endpoint is now the sole acceptor; the manager only registers the already-accepted socket.

---

### Bug 2 — No Initial State Push on Connect (Critical for reconnects)

**File:** `backend-engine/api/ws/endpoint.py` (after line 95, now fixed)

**What happened:**

After a display client successfully connected, the backend did nothing to send the current
game state. The display only received a `state_update` message when the *next* game event
triggered a broadcast (e.g., a player joining, a phase transition). On first load this meant
the display would wait silently. On page refresh mid-game, the display would show
"Waiting for game…" indefinitely unless another player took an action.

**Fix:** After `manager.connect()` and `queue.start()`, the endpoint now loads the current
`MasterGameState` from Redis, strips it via `player_view()`, and unicasts a `state_update`
directly to the newly connected WebSocket before entering the receive loop.

---

## Files Changed

| File | Change |
|---|---|
| `backend-engine/api/connection_manager.py:30` | Removed `await ws.accept()` |
| `backend-engine/api/ws/endpoint.py` | Added `json`, `get_settings`, `player_view`, `load_game` imports; added initial state unicast after connect |

---

## Verification Steps

1. `docker compose up --build backend` — rebuild backend container
2. Open `http://192.168.68.182/display/` — click "Click to Begin"
3. **No `?g=` param** → should see CreateMatchScreen ("🐺 Werewolf" + "Create New Match")
4. Click "Create New Match" → URL gets `?g=XXXXX`, display immediately shows LobbyScreen (warm dark substrate `phase-lobby`)
5. **Reconnect test:** Open `http://192.168.68.182/display/?g=XXXXX` in a new tab → LobbyScreen renders without waiting for a player to join
6. Browser DevTools → Network → WS connection → confirm status 101, no error close frames

---

## Why Only the Dark Background Was Visible

The body default `background: #060810` (set in `index.html`) is always visible while no
phase class is on `<html>`. Phase classes (`phase-lobby`, `phase-night`, `phase-day`) are
applied in `App.tsx` only when `gameState` is non-null (line 53–57). Since the display never
received a `state_update`, `gameState` was always `null`, the substrate classes were never
applied, and the dark fallback persisted indefinitely.
