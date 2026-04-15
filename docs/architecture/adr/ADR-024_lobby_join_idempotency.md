# ADR-024: Idempotent Lobby Join via `permanent_id` Deduplication

## Status
Accepted

## Date
2026-04-14

## Context

### The Bug

During a live session (match ID QVN9), mobile players who experienced HTTP timeouts or dropped connections during lobby join pressed the Join button again to retry. Each retry successfully reached the server and created a **new player entry** — a different UUID with the same `permanent_id` and `display_name`. The display client received a broadcast after each successful join and rendered each entry as a separate player.

When the host started the game, the engine dealt roles to every entry in `G.players`, including the ghost entries. The display showed duplicate names; the ghost player slots remained permanently disconnected for the rest of the game.

### Root Cause

`POST /api/games/{game_id}/join` (`api/lobby/routes.py`) has two code paths:

**Non-LOBBY path (lines 108–123) — correctly idempotent:**
```python
if G.phase != Phase.LOBBY:
    existing = next(
        (p for p in G.players.values() if p.permanent_id == body.permanent_id),
        None,
    )
    if existing:
        new_token = await issue_session_token(redis, game_id, existing.player_id)
        return { "player_id": existing.player_id, "session_token": new_token, ... }
    raise HTTPException(status_code=409, detail="Game already started.")
```

**LOBBY path (lines 128–145) — missing deduplication:**
```python
player_id = str(uuid.uuid4())         # new UUID on every call
G.players[player_id] = PlayerState(   # appended unconditionally
    permanent_id=body.permanent_id,
    ...
)
await save_game(redis, game_id, G)
await manager.broadcast(game_id, G)   # display sees the ghost immediately
```

The asymmetry was intentional at write-time — during LOBBY it was assumed each HTTP request was a first-time join. This assumption breaks when the HTTP response is lost in transit: the server has committed the player but the client received a network error and retries.

### Why Frontend Guards Are Insufficient

`OnboardingForm.tsx` has a `loading` guard (line 121: `if (!canJoin || loading) return`) and disables the submit button during an in-flight request. This prevents double-clicks within a single request but does not cover the lost-response scenario:

1. Request fires → server saves player-A to Redis → server responds  
2. Response is lost in transit (mobile network drop)  
3. Client `catch` block runs → `setError('Network error...')` → `loading = false`  
4. Player retries → server creates player-B → response received → client stores player-B session  
5. Game state now contains both player-A (ghost) and player-B (active)

No amount of client-side rate-limiting or submit debouncing closes this gap because the duplication happens at the server after a response that the client never receives.

---

## Decision

Add a `permanent_id` idempotency check to the LOBBY phase join path, mirroring the check that already exists for the non-LOBBY path. The check is inserted in `api/lobby/routes.py` immediately after the lobby-full guard:

```python
# Idempotency: if this permanent_id already joined the lobby, re-issue their
# token and return the existing player slot rather than creating a ghost entry.
existing = next(
    (p for p in G.players.values() if p.permanent_id == body.permanent_id),
    None,
)
if existing:
    new_token = await issue_session_token(redis, game_id, existing.player_id)
    return {
        "game_id": game_id,
        "player_id": existing.player_id,
        "session_token": new_token,
    }
```

The join endpoint is now **fully idempotent for all phases**: any number of retries from the same `permanent_id` return the same `player_id` with a fresh session token. No new player entry is written to Redis on retry, so no broadcast occurs and the display never sees a ghost.

---

## Rejected Alternatives

### Frontend double-submit prevention (button disable / rate-limit)

Disabling the button for N seconds after each press, or adding a debounce, prevents rapid double-clicks but does not address the lost-in-transit case. The network can drop the response after any delay. Even a 10-second lockout would not help a player whose HTTP response was dropped after 12 seconds. The bug recurs whenever mobile network quality is poor.

**Rejected:** treats the symptom at the wrong layer.

### Unique constraint on `(game_id, permanent_id)` in Postgres

Adding a DB-level unique constraint and relying on an `INSERT ... ON CONFLICT DO NOTHING` pattern would prevent duplicate history records but does not protect the Redis game state, which is the source of truth for the running game. The ghost entry is created and broadcast before any DB write occurs (routes.py line 145 saves to Redis; line 148 writes to Postgres). A DB constraint would fire too late and in the wrong store.

**Rejected:** wrong layer and wrong timing.

### Returning 409 on duplicate LOBBY join

Returning a 409 error when `permanent_id` is already present in the lobby would prevent ghosts but would cause the client to display "Game already started and you were not part of it." (`OnboardingForm.tsx` line 172–174) — a misleading error for a player who legitimately retried a failed join. It would also require client-side handling for the 409-in-LOBBY case, which is currently treated as a hard rejection.

**Rejected:** user-visible error for a valid retry; requires coordinated client change.

---

## Consequences

**Positive:**
- `POST /api/games/{game_id}/join` is idempotent for all game phases. Retrying a failed join is always safe.
- Ghost player slots can no longer be created via the join endpoint. The display will never show duplicate names from the same `permanent_id`.
- No client-side changes required. Existing retry behavior (user re-presses Join after a network error) becomes correct without any frontend update.
- The fresh token issued on idempotent return allows the client to establish a valid WebSocket session even if the original token expired between the first (lost) request and the retry.

**Negative:**
- A player who intentionally joins with a different `permanent_id` (e.g., switched devices, cleared localStorage, or registered a new name) will be re-seated into their existing slot with their original `display_name` and `avatar_id`. The new avatar/name from the retry body is ignored. This is the correct game-integrity behavior — one physical seat per person — but operators should be aware that name/avatar changes after the first successful join are silently discarded during LOBBY.
- Ghost entries created before this fix are already baked into any in-progress games. They must be identified and noted as permanently disconnected (see runbook).
