---
title: Player Registry, Game History DB & Shortened Match ID
date: 2026-04-13
commit: a71bfb93e6d25cdaa5e9f1b0556c572a03a04a89
branch: main
researcher: bethCoderNewbie
---

# Research: Persistent Player Registry + 4-Char Match IDs

## 1. Problem Statement

| # | Gap | Impact |
|---|-----|--------|
| 1 | Players are anonymous UUIDs — a new UUID is generated on every join/rematch | No cross-game identity; players must retype their name each game |
| 2 | Match IDs are 8-char base64 (e.g. `QCRB5_85`) — hard to read aloud | Join friction on mobile |
| 3 | No game history stored beyond Redis 4 h TTL | Cannot audit past games or link player stats |

---

## 2. Current Architecture (Ground Truth)

### 2.1 ID Generation

| Token | Generator | File | Line | Example |
|-------|-----------|------|------|---------|
| `game_id` | `secrets.token_urlsafe(6).upper()` | `api/lobby/routes.py` | 60 | `QCRB5_85` (8 chars) |
| `player_id` | `str(uuid.uuid4())` | `api/lobby/routes.py` | 94 | `a4c49f08-…` |
| `session_token` | `secrets.token_urlsafe(32)` | `storage/redis_store.py` | 57 | 43-char base64 |

### 2.2 Persistence Layer

- **Redis only** — `wolf:game:{game_id}` (TTL 4 h), `wolf:token:{token}` (TTL 4 h)
- **No SQL DB, no ORM, no migrations** — confirmed by docker-compose.yml (only `redis:7-alpine`) and absence of SQLAlchemy/Alembic/Prisma anywhere
- `MasterGameState` is a Pydantic model; `PlayerState` is nested inside it

### 2.3 Player Identity Lifecycle

```
Player opens app
  └─ localStorage["ww_session"] exists?
       ├─ YES → POST /api/games/{game_id}/rejoin (session_token)
       │          └─ backend validates wolf:token:{token} → sets is_connected=True
       └─ NO  → OnboardingForm: type name → POST /api/games/{game_id}/join
                  └─ backend mints new UUID + session_token
```

- `display_name` lives **only** in `PlayerState` inside `MasterGameState` in Redis
- After 4 h (or game_over + localStorage clear) the name is **gone**
- No concept of a "registered player" across multiple games

### 2.4 Rematch Flow

`POST /api/games/{game_id}/rematch` (routes.py:213)
- Generates a **new** `game_id` via `secrets.token_urlsafe(6).upper()`
- Assigns a **new** `player_id` UUID to every player
- Issues new `session_token`s for all
- Old game stores `rematch_redirect` payload so disconnected players get forwarded

---

## 3. Desired End State

1. **Player Registry** — a Postgres table `players(permanent_id, display_name, created_at)` keyed by a stable ID stored in localStorage
2. **Game History** — a Postgres table `games(game_id, started_at, ended_at, winner_team, player_count)`
3. **Game–Player Join** — `game_players(game_id, permanent_id, per_game_player_id, role, outcome)`
4. **Shortened Match ID** — 4-char alphanumeric (`[A-Z0-9]`, e.g. `K7BX`), replacing the current 8-char format
5. **Auto-fill on rejoin** — when a player's `permanent_id` is in localStorage, the join screen pre-fills their name; they cannot choose a different one for the same match

---

## 4. Key Design Decisions

### 4.1 Short Match ID: 4 chars vs "4 digits"

| Option | Alphabet | Combinations | Collision at 100 concurrent games |
|--------|----------|--------------|-----------------------------------|
| 4 numeric digits | 10 | 10,000 | ~1% |
| 4 alphanumeric (A-Z0-9) | 36 | 1,679,616 | <0.001% |
| 4 alpha-only (A-Z) | 26 | 456,976 | <0.01% |

**Recommendation:** 4-char `[A-Z0-9]` — still easy to say aloud ("K-7-B-X"), collision-safe at expected scale.
Generator: `''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(4))`
(Omits `I`, `O`, `0`, `1` to avoid read-aloud confusion.)

### 4.2 `permanent_id` Strategy

Mobile stores `permanent_id` in localStorage (`ww_session` key, adding a new field).  
This is **not** an auth credential — it is only a lookup key to pre-fill the name field.  
The existing `session_token` flow (per-game) remains the auth mechanism.

### 4.3 DB Technology

Add **Postgres 16** to docker-compose. Use **SQLAlchemy 2 (async)** + **Alembic** for migrations.  
This matches the FastAPI + asyncio stack with zero new runtime dependencies beyond what's already common.

---

## 5. Affected Files

| File | Change |
|------|--------|
| `docker-compose.yml` | Add `postgres:16-alpine` service |
| `backend-engine/requirements.txt` | Add `sqlalchemy[asyncio]`, `asyncpg`, `alembic` |
| `backend-engine/storage/db.py` | **NEW** — async engine, `get_db` dependency |
| `backend-engine/storage/models_db.py` | **NEW** — `players`, `games`, `game_players` ORM tables |
| `backend-engine/alembic/` | **NEW** — migration scaffold + initial migration |
| `backend-engine/api/lobby/routes.py` | `game_id` generation (line 60), `player_id` → `permanent_id` logic, join/rematch handlers |
| `backend-engine/storage/redis_store.py` | No change — Redis stays for live game state |
| `backend-engine/engine/state/models.py` | No change to `MasterGameState` — `permanent_id` is a DB-layer concern only |
| `frontend-mobile/src/App.tsx` | Extend `Session` type with `permanent_id`; send on join |
| `frontend-mobile/src/components/OnboardingForm.tsx` | Pre-fill name from `permanent_id` lookup |

---

## 6. Data Model

```sql
-- Permanent cross-game player registry
CREATE TABLE players (
    permanent_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name  VARCHAR(16) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Game index (summary written at game_over)
CREATE TABLE games (
    game_id       VARCHAR(4) PRIMARY KEY,   -- shortened to 4 chars
    started_at    TIMESTAMPTZ NOT NULL,
    ended_at      TIMESTAMPTZ,
    winner_team   VARCHAR(16),
    player_count  SMALLINT NOT NULL
);

-- Per-game player record (written at join, updated at game_over)
CREATE TABLE game_players (
    id               BIGSERIAL PRIMARY KEY,
    game_id          VARCHAR(4) NOT NULL REFERENCES games(game_id),
    permanent_id     UUID NOT NULL REFERENCES players(permanent_id),
    per_game_player_id VARCHAR(36) NOT NULL,   -- the UUID used inside MasterGameState
    role             VARCHAR(32),
    outcome          VARCHAR(16),              -- 'won', 'lost', null (in-progress)
    UNIQUE (game_id, permanent_id)
);
```

---

## 7. API Changes

### 7.1 Pre-register player name (new endpoint)
```
POST /api/players/register
Body: { "display_name": "Alice" }
Response: { "permanent_id": "<uuid>" }
```
Called from OnboardingForm before joining a game (or on first-ever launch).

### 7.2 Lookup player name (new endpoint)
```
GET /api/players/{permanent_id}
Response: { "permanent_id": "<uuid>", "display_name": "Alice" }
```
Called on app boot to pre-fill the name field.

### 7.3 Join endpoint change
```
POST /api/games/{game_id}/join
Body: { "permanent_id": "<uuid>", "avatar_id": "avatar_01" }
```
`display_name` is now looked up from DB via `permanent_id` — not supplied by the client at join time.

### 7.4 Rejoin behaviour
On rejoin: if `permanent_id` is in localStorage, call `GET /api/players/{permanent_id}` to confirm name.  
The join screen shows: `"Welcome back, Alice"` — name is read-only.

---

## 8. Mobile localStorage Schema (after change)

```typescript
interface Session {
  game_id: string        // 4-char, e.g. "K7BX"
  player_id: string      // per-game UUID (unchanged internally)
  session_token: string  // per-game auth token (unchanged)
  permanent_id: string   // NEW: cross-game UUID for name lookup
}
```

---

## 9. Open Questions for Plan Review

1. **Name change policy**: Can a player change their `display_name` after registering? If yes, add `PUT /api/players/{permanent_id}`. Needs age-gate or cooldown to prevent abuse.
2. **Collision retry for 4-char IDs**: At very high concurrency, a generated ID may already exist in Postgres. Need a DB-level uniqueness check + retry loop (max 5 attempts).
3. **Postgres TTL / archiving**: Old game records accumulate indefinitely. Add a `DELETE FROM games WHERE ended_at < now() - interval '30 days'` cron, or leave for now?
4. **Rematch + permanent_id**: Current rematch generates new `player_id` UUIDs — `game_players` insert for the new game can still link to the same `permanent_id`. No structural conflict.
5. **Display frontend**: The TV display screen never needs `permanent_id` — it uses `display_name` from the stripped game state. No display-client changes required.
