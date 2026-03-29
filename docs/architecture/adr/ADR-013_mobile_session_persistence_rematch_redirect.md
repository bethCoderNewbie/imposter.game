# ADR-013: Mobile Session Persistence & Rematch Redirect Forwarding

## Status
Accepted

## Date
2026-03-29

## Context

Two bugs prevented mobile players from resuming an in-progress game or rejoining after a rematch:

**Bug 1 — `sessionStorage` eviction on mobile browsers:**
Mobile clients (iOS Safari, Android Chrome) kill background tabs under memory pressure, clearing `sessionStorage` entirely. On reload, `App.tsx loadSession()` returned `null`, showing the onboarding form. The player's only re-entry path — `POST /api/games/{id}/join` — rejects games not in LOBBY phase with a 409, permanently locking them out of their own match.

**Bug 2 — Missed rematch redirect for disconnected players:**
`POST /api/games/{id}/rematch` creates a new game and broadcasts a `redirect` WebSocket message to currently-connected sockets on the old game. Any player whose WebSocket was closed at that moment never received the redirect. On reconnecting, they received the old game's `game_over` state with no route to the new game. The mobile `GameOverScreen.onPlayAgain` handler only clears the session and shows the onboarding form — it has no way to retrieve new credentials.

---

## Decision

### 1. `localStorage` for session token storage (was `sessionStorage`)

**Changed:** `frontend-mobile/src/App.tsx` — `loadSession`, `saveSession`, `clearSession` now use `localStorage` instead of `sessionStorage`.

**Rejected:** keeping `sessionStorage`.

**Rationale:**
- `sessionStorage` is per-tab and is cleared on tab kill. Mobile browsers routinely kill background tabs. For a party game where players are expected to switch apps on their phone during play, this is a near-certain disruption path.
- `localStorage` persists until the origin is cleared. The backend's 4-hour Redis TTL on session tokens is the natural expiry guard — a stale `localStorage` entry is handled cleanly: the `rejoin` endpoint returns 401, `App.tsx` calls `clearSession()`, and the onboarding form appears.
- The security model does not rely on session token ephemerality. The token is random (32-byte URL-safe), bound to `(game_id, player_id)`, and short-lived (4-hour TTL). `localStorage` persistence within that window is safe.
- **Scope note:** This change applies only to the reconnect session token (`ww_session` key). The Seer peek history (`ww_seer_*` keys) continues to use `sessionStorage` per ADR-003 §9 — that data should not outlast the tab session.

### 2. Persist redirect payload in old game state for WS replay

**Changed:** Three backend files + one new model field:

- `backend-engine/engine/state/models.py` — added `rematch_redirect: dict[str, Any] | None = None` to `MasterGameState` (server-only field).
- `backend-engine/engine/stripper.py` — added `"rematch_redirect"` to the `exclude={}` set in `player_view()`. This field must never reach any client via state broadcast.
- `backend-engine/api/lobby/routes.py` (`rematch_game`) — before broadcasting the redirect to live sockets, the full `redirect_payload` is written to `G.rematch_redirect` on the old game and re-saved to Redis.
- `backend-engine/api/ws/endpoint.py` — after sending the initial `sync` message to a reconnecting player, the endpoint checks `G_init.rematch_redirect`. If present and the reconnecting `player_id` is a key in `rematch_redirect["players"]`, the redirect payload is sent immediately as a second message.

**Rejected alternatives:**
- *Client-side polling:* Polling `/api/games/{id}` for a forwarding hint adds complexity and a round-trip delay; it also requires the Display to remember and surface the new game_id via a separate REST endpoint.
- *New REST endpoint (`/api/games/{id}/forward`):* Equivalent server work but requires a separate HTTP request from the client after WS connect, introducing a timing gap where the client shows the stale game_over state.
- *Re-send redirect only on rejoin response:* The HTTP `POST /rejoin` response is consumed before the WebSocket connects. The `handleRedirect` function in `useGameState.ts` needs to receive the redirect as a WebSocket message to trigger the session update and WS reconnect chain.

**Why WS replay works without client changes:**
The existing `handleRedirect` in `App.tsx` (line 52) is triggered by `useGameState.ts` whenever the WebSocket receives `{ type: "redirect" }`. It updates and saves the new session to `localStorage`, which triggers a `useGameState` re-render, which changes the WS URL, which reconnects to the new game. This path was already correct for connected players who received the live broadcast — replay on reconnect reuses it unchanged.

---

## Consequences

**Positive:**
- Mobile players who are killed, backgrounded, or briefly lose connectivity can reliably return to their in-progress game session.
- Disconnected players who miss the `rematch` redirect automatically receive it on the next WS connect — no manual action or re-entry of game code required.
- No new client-side code paths: the redirect replay reuses the existing `handleRedirect` chain.
- `rematch_redirect` is excluded from the state stripper, so it costs zero additional data on every regular state broadcast.

**Negative:**
- `localStorage` entries for expired games accumulate until the browser clears origin storage. The `clearSession()` call on 401 responses is the primary cleanup path; stale entries from crashes or unclean exits remain until the token expires and the next app open triggers cleanup.
- The `rematch_redirect` field (containing all players' new tokens) lives in the old game's Redis state until that key expires (4-hour TTL). This is acceptable — the tokens are short-lived by design, and the old game state already contains `session_token` per player.
- Display client reconnecting to the old game does not receive the redirect replay (the `is_display` guard in `endpoint.py` excludes it). The Display already has the new `game_id` and `host_secret` from the synchronous `POST /rematch` HTTP response — it does not need WS replay.
