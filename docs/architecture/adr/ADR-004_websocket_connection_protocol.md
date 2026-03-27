# ADR-004: Werewolf — WebSocket Connection Protocol

## Status
Accepted

## Date
2026-03-27

## Context

Two bugs discovered in the Display TV's WebSocket connection path caused it to show a persistent dark background on `http://<LAN-IP>/display/`:

1. **Double `ws.accept()` crash.** `api/ws/endpoint.py` called `await websocket.accept()` (line 38) to allow sending auth-error messages before closing invalid connections. `ConnectionManager.connect()` also called `await ws.accept()` on the same socket. Starlette/uvicorn raises a `RuntimeError` when `websocket.accept` is sent twice for one connection — the ASGI lifecycle only permits one accept event. This exception closed the socket before the display client was registered in `manager._rooms`, so no broadcasts were ever delivered.

2. **No initial state push on connect.** After a client successfully connected and was registered, the backend sent nothing until the *next* game event triggered a broadcast. A display client that connected mid-game (or after a page refresh) would stay on "Waiting for game…" indefinitely.

These two bugs combined to produce the dark background: the display never received a `state_update`, so `gameState` remained `null`, phase classes were never applied to `<html>`, and the default `#060810` body background persisted.

---

## Decision

### 1. Endpoint Is the Sole Acceptor

`api/ws/endpoint.py` calls `await websocket.accept()` once, before any auth logic. This allows the server to send an `{"type":"error","code":"..."}` message to the client and then close cleanly if auth fails — if the socket is never accepted, `send_text` raises.

`ConnectionManager.connect()` no longer calls `ws.accept()`. It only registers the already-accepted socket into `manager._rooms[game_id]`.

**Rule:** The WebSocket endpoint accepts; the ConnectionManager registers. Never accept twice.

### 2. Initial State Unicast on Connect

After `manager.connect()` and `queue.start()` succeed, the endpoint:

1. Calls `load_game(redis, game_id)` to read the current `MasterGameState`.
2. Calls `player_view(G, authenticated_player_id)` to strip the state for the connecting client's view.
3. Sends a `state_update` payload directly to the connecting WebSocket (unicast, not broadcast).
4. Enters the receive loop.

If `load_game` returns `None` (game not yet created, or Redis TTL expired), no initial push is sent — the client waits for the next broadcast. This is acceptable for the pre-game lobby creation flow.

**Effect:** A display client connecting mid-game, or reconnecting after a page refresh, receives the current state immediately without needing another player to take an action.

### 3. Display Client Authentication

The display client connects to `/ws/{game_id}/display`. The `player_id` path segment `"display"` is a sentinel value that bypasses session-token validation. `player_view(G, None)` is called (passing `None` as the authenticated player ID), which applies the Display view: no role data, no alignment data, aggregate `actions_submitted_count` only.

---

## Consequences

**Positive:**
- Display client is guaranteed to receive game state on connect, regardless of when it joins or reconnects.
- Removing the second `ws.accept()` eliminates the `RuntimeError` that silently closed display connections.
- The unicast pattern is reusable for any future reconnect scenarios (mobile client rejoining mid-game).
- No change to the broadcast path — all other connected clients continue to receive state via `manager.broadcast()`.

**Negative:**
- `endpoint.py` now imports `load_game`, `player_view`, `get_settings`, and `json` — slightly more coupling between the WebSocket transport layer and the game-state layer. Accepted as a pragmatic trade-off; the endpoint is the correct place to perform the initial state push, not inside `ConnectionManager`.
- If Redis is unavailable at connect time, `load_game` may raise. The endpoint's existing exception handler catches this and closes the socket, which is the correct behavior (the client retries).
