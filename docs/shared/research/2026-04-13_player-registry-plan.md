---
title: Plan — Player Registry, Game History DB & 4-Char Match IDs
date: 2026-04-13
commit: a71bfb93e6d25cdaa5e9f1b0556c572a03a04a89
branch: main
---

# Implementation Plan

## Desired End State

After this work:
- Match IDs are 4 characters (e.g. `K7BX`), easy to read aloud
- A player opens the app for the first time → enters their name → it is registered permanently
- Every subsequent game, the app pre-fills their name; they only pick a color and code
- On rejoin after a crash, the name is shown read-only — they cannot impersonate someone else in the same game
- Postgres stores a permanent player registry and game history (game_id, outcome, participants)

## Anti-Scope

- No login/password — identity is opt-in via localStorage `permanent_id` only
- No player stats dashboard or leaderboard (DB schema supports it later)
- No name-change endpoint (open question — not building now)
- No game record archiving/deletion cron (DB will grow; out of scope)
- No changes to the Display frontend
- No changes to how Redis stores live game state

---

## Phase 1 — Infrastructure: Postgres + Alembic

### 1.1 `docker-compose.yml`
Add `postgres` service and `DATABASE_URL` env to `backend`.

```yaml
postgres:
  image: postgres:16-alpine
  environment:
    POSTGRES_DB: werewolf
    POSTGRES_USER: werewolf
    POSTGRES_PASSWORD: werewolf
  restart: unless-stopped

backend:
  environment:
    REDIS_URL: redis://redis:6379
    DATABASE_URL: postgresql+asyncpg://werewolf:werewolf@postgres/werewolf
  depends_on:
    - redis
    - postgres
```

### 1.2 `pyproject.toml` — add to `dependencies`
```toml
"sqlalchemy[asyncio]>=2.0",
"asyncpg>=0.29.0",
"alembic>=1.13.0",
```

### 1.3 `backend-engine/engine/config.py`
Add field (alongside `redis_url`):
```python
database_url: str = "postgresql+asyncpg://werewolf:werewolf@postgres/werewolf"
```

### 1.4 NEW `backend-engine/storage/db.py`
```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from engine.config import get_settings

_engine = None
_session_factory = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, echo=False)
    return _engine

def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory

async def get_db() -> AsyncSession:
    async with get_session_factory()() as session:
        yield session
```

### 1.5 NEW `backend-engine/storage/models_db.py`
```python
from sqlalchemy import BigInteger, Column, ForeignKey, SmallInt, String, TIMESTAMP, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class DBPlayer(Base):
    __tablename__ = "players"
    permanent_id  = Column(String(36), primary_key=True)   # UUID str
    display_name  = Column(String(16), nullable=False)
    created_at    = Column(TIMESTAMP(timezone=True), nullable=False)

class DBGame(Base):
    __tablename__ = "games"
    game_id       = Column(String(4), primary_key=True)
    started_at    = Column(TIMESTAMP(timezone=True), nullable=False)
    ended_at      = Column(TIMESTAMP(timezone=True), nullable=True)
    winner_team   = Column(String(16), nullable=True)
    player_count  = Column(SmallInt, nullable=False)

class DBGamePlayer(Base):
    __tablename__ = "game_players"
    id                 = Column(BigInteger, primary_key=True, autoincrement=True)
    game_id            = Column(String(4), ForeignKey("games.game_id"), nullable=False)
    permanent_id       = Column(String(36), ForeignKey("players.permanent_id"), nullable=False)
    per_game_player_id = Column(String(36), nullable=False)
    role               = Column(String(32), nullable=True)
    outcome            = Column(String(16), nullable=True)
    __table_args__ = (UniqueConstraint("game_id", "permanent_id"),)
```

### 1.6 Alembic scaffold
```
cd backend-engine
alembic init alembic
```
Edit `alembic/env.py`:
- Import `Base` from `storage.models_db`
- Set `target_metadata = Base.metadata`
- Read `DATABASE_URL` from `engine.config.get_settings().database_url`

Generate initial migration:
```
alembic revision --autogenerate -m "initial_player_registry"
```

### 1.7 `backend-engine/Dockerfile` — run migrations on startup
Replace `CMD` with an entrypoint script that runs `alembic upgrade head` then starts uvicorn:
```dockerfile
COPY backend-engine/entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
```
`entrypoint.sh`:
```bash
#!/bin/sh
set -e
cd /app/backend-engine
alembic upgrade head
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 1.8 `backend-engine/api/main.py` — wire DB engine into lifespan
In `lifespan`, after Redis init, call `get_engine()` to warm the connection pool.

---

## Phase 2 — Shorten Match ID to 4 Characters

### 2.1 NEW helper in `backend-engine/storage/id_gen.py`
```python
import secrets

# Omit I, O, 0, 1 to avoid read-aloud confusion
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

def new_game_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(4))
```

### 2.2 `backend-engine/api/lobby/routes.py`

**Line 60** — `create_game`:
```python
# Before
game_id = secrets.token_urlsafe(6).upper()
# After
from storage.id_gen import new_game_id
game_id = new_game_id()
```

**Line 213** — `rematch_game`:
```python
# Before
new_game_id = secrets.token_urlsafe(6).upper()
# After (variable rename needed to avoid shadowing the import)
new_game_id_val = new_game_id()
```
(Rename the local variable throughout `rematch_game` to `new_game_id_val`)

### 2.3 `frontend-mobile/src/components/OnboardingForm/OnboardingForm.tsx`

Update all `maxLength={8}` → `maxLength={4}` (lines 131 and 218).
Update placeholder text `"e.g. ABC123"` → `"e.g. K7BX"` (lines 134 and 219).

---

## Phase 3 — Player Registry Backend

### 3.1 NEW `backend-engine/api/players/routes.py`

```python
router = APIRouter(prefix="/api/players", tags=["players"])

class RegisterRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=16)

@router.post("/register")
async def register_player(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    permanent_id = str(uuid.uuid4())
    db.add(DBPlayer(
        permanent_id=permanent_id,
        display_name=body.display_name.strip(),
        created_at=datetime.now(UTC),
    ))
    await db.commit()
    return {"permanent_id": permanent_id, "display_name": body.display_name.strip()}

@router.get("/{permanent_id}")
async def get_player(permanent_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(DBPlayer, permanent_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found.")
    return {"permanent_id": player.permanent_id, "display_name": player.display_name}
```

### 3.2 Mount in `backend-engine/api/main.py`
```python
from api.players.routes import router as players_router
app.include_router(players_router)
```

### 3.3 `backend-engine/engine/state/models.py` — add `permanent_id` to `PlayerState`
Add one server-only field (stripped from broadcast, same pattern as `session_token`):
```python
permanent_id: str | None = None   # cross-game registry key; server-only
```
Verify this field is included in the state stripper's server-only exclusion list.

### 3.4 `backend-engine/api/lobby/routes.py` — update `join_game`

Change `JoinGameRequest`:
```python
class JoinGameRequest(BaseModel):
    permanent_id: str          # replaces display_name
    avatar_id: str = "default_01"
```

In `join_game` handler:
```python
# Lookup display_name from DB
player_rec = await db.get(DBPlayer, body.permanent_id)
if player_rec is None:
    raise HTTPException(status_code=404, detail="Player not registered.")
display_name = player_rec.display_name

player_id = str(uuid.uuid4())
G.players[player_id] = PlayerState(
    player_id=player_id,
    display_name=display_name,
    avatar_id=body.avatar_id,
    permanent_id=body.permanent_id,   # stored server-side only
)
```

Add `db: AsyncSession = Depends(get_db)` to `join_game` signature.

### 3.5 `rematch_game` — preserve `permanent_id` across rematch
In the player migration loop (routes.py ~line 221), copy `permanent_id` from old PlayerState:
```python
new_G.players[new_pid] = PlayerState(
    player_id=new_pid,
    display_name=ps.display_name,
    avatar_id=ps.avatar_id,
    permanent_id=ps.permanent_id,   # carry forward
)
```

---

## Phase 4 — Game History DB Writes

### 4.1 `create_game` — insert `DBGame` row
After `setup_game(...)`, before `return`:
```python
db.add(DBGame(
    game_id=game_id,
    started_at=datetime.now(UTC),
    player_count=0,
))
await db.commit()
```
Add `db: AsyncSession = Depends(get_db)` to `create_game` signature.

### 4.2 `join_game` — insert `DBGamePlayer` row
After saving to Redis, insert:
```python
db.add(DBGamePlayer(
    game_id=game_id,
    permanent_id=body.permanent_id,
    per_game_player_id=player_id,
))
# Update game player_count
game_rec = await db.get(DBGame, game_id)
if game_rec:
    game_rec.player_count = len(G.players)
await db.commit()
```

### 4.3 Write `ended_at` + `winner_team` on GAME_OVER
In `backend-engine/api/intents/handlers.py`, after any transition to `Phase.GAME_OVER`, call a new helper:

NEW `backend-engine/storage/db_writes.py`:
```python
async def record_game_over(db: AsyncSession, G: MasterGameState):
    game_rec = await db.get(DBGame, G.game_id)
    if game_rec:
        game_rec.ended_at = datetime.now(UTC)
        game_rec.winner_team = G.winner
    # Update role + outcome on each game_players row
    for pid, ps in G.players.items():
        result = await db.execute(
            select(DBGamePlayer).where(
                DBGamePlayer.game_id == G.game_id,
                DBGamePlayer.per_game_player_id == pid,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.role = ps.role
            row.outcome = _outcome(ps, G.winner)
    await db.commit()
```

`_outcome(ps, winner)` → `"won"` if player's team matches winner, `"lost"` otherwise.

The tricky part: `handlers.py` currently has no DB session. Pass `db` into the handler signature via a context variable, or fire-and-forget with a background task. Cleanest: add `db` as an optional kwarg to `dispatch_intent` and thread it through to handlers that need it.

### 4.4 `rematch_game` — insert `DBGame` + new `DBGamePlayer` rows for the new game
Same as 4.1/4.2, using `new_game_id_val` and players from `new_G`.

---

## Phase 5 — Mobile Frontend

### 5.1 `frontend-mobile/src/App.tsx`

Extend `Session` interface:
```typescript
interface Session {
  game_id: string
  player_id: string
  session_token: string
  permanent_id: string    // NEW
}
```

Add a separate persistent key (survives game-over session clear):
```typescript
const PERMANENT_ID_KEY = 'ww_permanent_id'

function loadPermanentId(): string | null {
  return localStorage.getItem(PERMANENT_ID_KEY)
}
function savePermanentId(id: string) {
  localStorage.setItem(PERMANENT_ID_KEY, id)
}
```

Update `handleRedirect` — carry `permanent_id` into new session:
```typescript
const newSession: Session = {
  game_id: msg.new_game_id!,
  player_id: entry.new_player_id,
  session_token: entry.new_session_token,
  permanent_id: prev.permanent_id,   // unchanged across rematch
}
```

Pass `permanent_id` down to `OnboardingForm`:
```typescript
<OnboardingForm
  prefillCode={URL_GAME_CODE}
  permanentId={loadPermanentId()}
  onJoined={(s) => { saveSession(s); savePermanentId(s.permanent_id); setSession(s) }}
/>
```

### 5.2 `frontend-mobile/src/components/OnboardingForm/OnboardingForm.tsx`

Update `Props`:
```typescript
interface Props {
  prefillCode: string
  permanentId: string | null      // NEW
  onJoined: (session: JoinedSession) => void
}
```

Update `JoinedSession`:
```typescript
interface JoinedSession {
  game_id: string
  player_id: string
  session_token: string
  permanent_id: string
}
```

On mount: if `permanentId` prop is set, call `GET /api/players/{permanentId}` and set `name` state read-only:
```typescript
const [registeredName, setRegisteredName] = useState<string | null>(null)

useEffect(() => {
  if (!props.permanentId) return
  fetch(`/api/players/${props.permanentId}`)
    .then(r => r.ok ? r.json() : null)
    .then(data => { if (data) setRegisteredName(data.display_name) })
    .catch(() => {})
}, [props.permanentId])
```

In the name field: if `registeredName` is set, render it read-only:
```tsx
{registeredName ? (
  <p className="onboarding__registered-name">Playing as <strong>{registeredName}</strong></p>
) : (
  <input id="player-name" ... value={name} onChange={...} />
)}
```

Update `handleJoin`:
```typescript
async function handleJoin() {
  let pid = props.permanentId

  // First-time player: register name
  if (!pid) {
    const reg = await fetch('/api/players/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: name.trim() }),
    })
    if (!reg.ok) { setError('Could not register. Try again.'); return }
    const regData = await reg.json() as { permanent_id: string }
    pid = regData.permanent_id
  }

  // Join the game
  const res = await fetch(`/api/games/${code.trim()}/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ permanent_id: pid, avatar_id: avatarId }),
  })
  // ... existing status handling ...
  const data = await res.json() as { game_id: string; player_id: string; session_token: string }
  onJoined({ ...data, permanent_id: pid })
}
```

Remove the manual rejoin-via-token mode (the token textarea). Rejoining is now fully automatic via `ww_session` localStorage — no user action needed. Simplify the fallback error to: `"Game already started. Please close and reopen the app to rejoin."` 

Update all `maxLength={8}` → `maxLength={4}`, placeholder `"e.g. ABC123"` → `"e.g. K7BX"`.

---

## Phase 6 — State Stripper Verification

Check `backend-engine/engine/stripper.py` (or wherever player state is stripped before broadcast) that `permanent_id` is in the server-only fields exclusion list alongside `session_token`, `is_protected`, `hunter_fired`, etc.

---

## Execution Order

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6
  (infra)   (IDs)  (registry) (history)  (mobile) (strip verify)
```
Each phase can be verified independently before proceeding.

---

## Verification

### Automated
```bash
pytest backend-engine/tests/ -v -k "not integration"
```

### Manual
1. `docker compose up --build`
2. Display creates game → join code shows 4 chars
3. Player 1 opens mobile → no localStorage → types name → clicks Join → backend registers name → game joined
4. Close mobile tab → reopen → name is pre-filled, read-only → enter same game code → Join → arrives in lobby as same player
5. Rejoin after crash: kill tab mid-game → reopen → automatic rejoin restores session, name shown correctly
6. Rematch: after game over, host clicks rematch → all players see new 4-char code → mobile auto-redirects → `permanent_id` preserved in new session

### DB spot-check
```sql
SELECT * FROM players;
SELECT * FROM games;
SELECT gp.*, p.display_name FROM game_players gp JOIN players p USING (permanent_id);
```

---

## Open Questions (resolved)

| Q | Decision |
|---|----------|
| Name change? | Not building now |
| 4 numeric or alphanumeric? | 4-char `[A-Z0-9]` minus ambiguous chars |
| Old 8-char game IDs in Redis? | DB only tracks new games; backward compat not needed |
| Postgres data retention? | Indefinite for now |
