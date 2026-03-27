# Coding Practices: Werewolf Game Server

**Scope:** Backend engine (`backend-engine/`). This document covers patterns, conventions, and architectural rules used in this codebase. It is a reference for contributors — not a debugging guide.

---

## Core Principles

1. **Server-authoritative state.** All game state lives in Redis. Clients send intents only; they never push state. The server is always right.
2. **Pure functions everywhere.** Resolvers (`resolve_night`, `resolve_day_vote`, `check_win_condition`) and phase transitions (`transition_phase`) accept a `MasterGameState` and return a new one. No I/O, no side effects, no globals.
3. **One writer per game.** Each game has a single `asyncio.Queue`. All intents are enqueued and processed sequentially — no locks, no race conditions.
4. **Security boundary at the stripper.** `player_view(G, player_id)` is the only place where the full state is reduced to a client-safe view. Every broadcast goes through it. Never bypass it.

---

## State Mutation: Pydantic V2 Patterns

### Always deep-copy before mutating

```python
G = G.model_copy(deep=True)
```

Call this at the top of every resolver and phase transition function. The caller's state must never be modified.

### Enum fields use `use_enum_values=True`

`MasterGameState` (and all nested models) is configured with `use_enum_values=True`. This means:

- Assign enum members or their `.value` strings — both work.
- When reading back from the model, you get a `str`, not the enum member.
- JSON serialisation is automatic and produces clean lowercase strings.

```python
# Both are valid assignments:
player.team = Team.VILLAGE
player.team = "village"

# When reading back:
player.team  # → "village" (str, not Team.VILLAGE)
```

### `StrEnum` for all enums

All enums in `engine/state/enums.py` extend `StrEnum`. This gives:

- Direct string comparison: `player.team == "village"` works.
- `.value` is the lowercase string used in JSON.
- No need for `.value` when passing to Pydantic fields.

---

## Resolvers

### Night resolver (`engine/resolver/night.py`)

13 steps, always run in order. Never skip steps. Never run steps conditionally based on game state outside each step's own guard.

Step ordering is load-bearing:
1. Roleblock (step 1) must resolve before any ability that can be blocked (steps 2–11).
2. Framer (step 2) must set `is_framed_tonight` before Seer (step 6) reads it.
3. Infector (step 4) marks `infect_used` before step 7 checks it.
4. Tracker (step 11) reads all other resolved actions — it is always last among action roles.

**Roleblock check pattern** (used in steps 2–11):

```python
if role_pid == G.night_actions.roleblocked_player_id:
    return G  # action discarded
```

**`_find_role_player` helper:** Returns the first *living* player with the given `role` string, or `None`. Use this instead of iterating `G.players` inline.

### Day resolver (`engine/resolver/day.py`)

Strict majority means `> 50%` of **all alive players**, not just those who voted. The denominator is always `sum(p.is_alive for p in G.players.values())`.

### Win condition (`engine/resolver/_win.py`)

Called after every elimination event (including Hunter revenge). Must check all three factions in a defined priority order. See the resolver for the exact sequence.

---

## Phase Machine (`engine/phases/machine.py`)

### `transition_phase` entry effects

Every phase transition is handled in `transition_phase()`. Side effects on entry:

| Target phase | Entry side effects |
|---|---|
| `NIGHT` | Deep-copy; increment round (if not from LOBBY/ROLE_DEAL); reset `is_protected`, `is_framed_tonight`, `night_action_submitted`; clear `day_votes` and `vote_target_id`; create fresh `NightActions` |
| `DAY` | Clear `day_votes` and `vote_target_id` |
| `ROLE_DEAL` | Reset all `role_confirmed` flags |
| All timed phases | Set `timer_ends_at` from config |
| `LOBBY`, `GAME_OVER` | `timer_ends_at = None` |

**Round increment rule:** `round` increments on every `NIGHT` entry **except** when coming from `LOBBY` or `ROLE_DEAL`. This means `round` stays `1` through the first night.

### `compute_actions_required`

Counts living players whose role has `wakeOrder > 0` AND `actionPhase` is not `"none"`, `"day"`, or `"on_death"`. Cupid (`actionPhase == "night_one_only"`) is excluded when `round > 1`. This count gates auto-advance.

---

## Intent Dispatch (`api/intents/`)

### File layout

```
api/intents/
  errors.py    ← IntentError lives here (prevents circular import)
  dispatch.py  ← routes intent type strings to handler functions
  handlers.py  ← one handler per intent type; imports IntentError from errors.py
```

### Why `IntentError` is in its own module

`dispatch.py` imports `handlers.py` (to call handlers). `handlers.py` imports `dispatch.py` (to raise `IntentError`). This circular dependency is broken by extracting `IntentError` to `errors.py`. Both modules import from `errors.py`.

### Handler contract

Every handler has this signature:

```python
async def handle_<intent>(G: MasterGameState, payload: dict, player_id: str) -> MasterGameState:
```

- Validate intent preconditions first — raise `IntentError(code, message)` on any violation.
- Call the appropriate pure resolver.
- Return the new `MasterGameState`.
- Never write to Redis — the caller (queue consumer) handles persistence.

### Error codes

All error code strings are documented in `docs/architecture/data_dictionary.md` § Error Codes. Use the exact strings defined there — clients pattern-match on them.

---

## State Stripper (`engine/stripper.py`)

`player_view(G, player_id)` returns a `dict` (not a Pydantic model). Six view types:

| Condition | View type |
|---|---|
| `player_id is None` | Display client — no roles, no votes, counts only |
| `player.is_alive == False` | Dead spectator — sees all roles |
| `player.team == "werewolf"` | Wolf team — sees teammates + `wolf_votes` |
| `player.role == "seer"` | Seer — sees `seer_target_id`, `seer_result`, `seer_knowledge` |
| `player.role == "tracker"` | Tracker overlay — sees `tracker_knowledge` |
| Default alive village/neutral | Own role only; no sensitive `night_actions` fields |

**Fields that are NEVER sent to any client:**

- `is_protected`
- `is_framed_tonight`
- `hunter_fired`
- `last_protected_player_id`
- `session_token`
- `infect_used`
- `false_hint_queued`
- `puzzle_data.correct_index`

---

## Role System (`engine/roles_loader.py`)

### `ROLE_REGISTRY`

A `dict[str, dict]` loaded from `docs/architecture/roles.json` at startup. Key is the snake_case role ID. Access pattern:

```python
role_def = ROLE_REGISTRY.get(player.role or "", {})
wake_order = role_def.get("wakeOrder", 0)
```

### `investigationResult` vs `team`

These are distinct fields. **Never use `player.team` in Seer resolution logic.** Use `role_def["investigationResult"]` from the registry. Alpha Wolf has `team: "werewolf"` but `investigationResult: "village"`.

Valid `investigationResult` values: `"village"` | `"wolf"` | `"neutral"` — note `"wolf"`, not `"werewolf"`.

### `DYNAMIC_TEMPLATES`

A `dict` keyed by player-count string (e.g., `"5-7"`), not a list. Each value is a dict with `playerCount.min/max`, `guaranteed`, and `flexPools`. The `_find_template` function iterates `.values()` and matches on the `playerCount` range.

---

## Test Patterns (`tests/`)

### Backend fixtures

`tests/conftest.py` provides two game fixtures:

- `_eight_player_game()` → `(MasterGameState, dict)` — 8 players: p1/p2=werewolf, p3=seer, p4=doctor, p5=tracker, p6/p7/p8=villager
- `_five_player_game()` → `(MasterGameState, dict)` — minimal 5-player game

Fixtures return `(G, player_map)` where `player_map` is `{player_id: role_id}`.

### State isolation

Always call `G = G.model_copy(deep=True)` before mutating fixture state in a test. The fixture object is shared across tests in the same class if not deep-copied.

### `compute_actions_required` expectations

Wolves count toward `actions_required_count`. The 8-player fixture has 5 active-role players (2 wolves + seer + doctor + tracker), so `compute_actions_required(G)` returns `5`, not `3`.

### Redis store tests (`tests/storage/`)

Use `fakeredis.aioredis.FakeRedis()` as an async in-memory Redis replacement. Each test receives a fresh instance from a pytest fixture — no teardown required.

```python
import pytest
import fakeredis.aioredis

@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis()
```

`fakeredis` enforces real Redis semantics (TTL, key namespacing, binary values). Do not use `unittest.mock.AsyncMock` for Redis calls — mocks do not validate key format or TTL logic.

### Integration tests (`tests/api/`)

Integration tests exercise the full HTTP and WebSocket stack using `starlette.TestClient`. `FakeRedis` is injected by patching `redis.asyncio.from_url` before the lifespan runs. All integration tests are marked `@pytest.mark.integration`.

**Shared fixtures** (`tests/api/conftest.py`):

```python
@pytest.fixture
def client(fake_redis, monkeypatch):
    monkeypatch.setattr(redis.asyncio, "from_url", lambda *a, **kw: fake_redis)
    from api.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
```

The `reset_singletons` autouse fixture in `conftest.py` stops queued tasks and clears `_queues` and `_rooms` between tests. Always rely on this fixture — never manually clear these in individual tests.

**WebSocket test pattern:**

```python
with client.websocket_connect(f"/ws/{game_id}/display") as ws:
    msg = ws.receive_json()
    assert msg["type"] == "state_update"
```

When a player's auth is rejected, the server sends an error message *then* closes. Test the error message, not the disconnect:

```python
with client.websocket_connect(f"/ws/{game_id}/{player_id}") as ws:
    ws.send_json({"type": "auth", "session_token": "bad-token"})
    msg = ws.receive_json()
assert msg["type"] == "error"
assert msg["code"] == "AUTH_FAILED"
```

### E2E tests (`tests/e2e/`)

E2E tests run against a real Redis instance and are marked `@pytest.mark.e2e`. They self-skip when Redis is unavailable — never wrap them in a try/except.

**When to write an E2E test vs an integration test:**
- Use **integration** when the test only verifies request/response contracts, auth logic, or state stripping. Redis is irrelevant.
- Use **E2E** when the test must verify that Redis persistence, game queue processing, or real-time broadcast actually works end-to-end (e.g., "start game → state transitions to ROLE_DEAL").

**E2E fixture:**

```python
# tests/e2e/conftest.py provides:
# - require_redis (autouse, module-scope): skip if Redis unreachable
# - e2e_client: TestClient connected to real Redis
```

Use the module-scoped `e2e_client` fixture. Do not create your own `TestClient` in E2E tests.

**E2E WS blocking pattern:**

```python
with e2e_client.websocket_connect(f"/ws/{game_id}/display") as ws:
    ws.receive_json()  # initial lobby state

    e2e_client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})

    role_deal_msg = ws.receive_json()  # blocks until game queue broadcasts
    assert role_deal_msg["state"]["phase"] == "role_deal"
```

`ws.receive_json()` blocks until a message arrives. The game queue background task runs in the TestClient's event loop and will deliver the broadcast before the timeout.

---

## Frontend Test Patterns (`frontend-display/src/test/`)

### Framework

Vitest + jsdom. Run via `npm run test` in `frontend-display/`. Configuration: `frontend-display/vitest.config.ts`.

**Critical config flags:**
- `clearMocks: true` — resets `vi.fn()` call counts between every test. Required for audio spy tests.
- `globals: true` — exposes `vi`, `describe`, `it`, `expect` without imports.

### FakeWebSocket (hook tests)

`useWebSocket` tests use a class-based fake that mimics the browser `WebSocket` API:

```typescript
class FakeWebSocket {
  static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
  readyState = FakeWebSocket.CONNECTING;
  send = vi.fn(); close = vi.fn();
  onopen: (() => void) | null = null;
  onclose: ((e: any) => void) | null = null;
  onmessage: ((e: any) => void) | null = null;
  onerror: ((e: any) => void) | null = null;
  triggerOpen() { this.readyState = FakeWebSocket.OPEN; this.onopen?.(); }
  triggerClose(code = 1000) { this.readyState = FakeWebSocket.CLOSED; this.onclose?.({ code }); }
  triggerMessage(data: string) { this.onmessage?.({ data }); }
  triggerError() { this.onerror?.(new Event('error')); }
}
```

Inject via: `vi.stubGlobal('WebSocket', vi.fn(() => new FakeWebSocket()))`.

### Module-level `vi.mock` for hooks in component tests

Mock hooks at the top of the test file (outside `describe`) so all tests in the file use the mock:

```typescript
vi.mock('../../hooks/useTimer', () => ({
  useTimer: vi.fn(() => ({ seconds: 0, isWarning: false, isCritical: false })),
}))
```

Then override per test: `vi.mocked(useTimer).mockReturnValue({ seconds: 30, ... })`.

### RAF stub for `useTimer` tests

`requestAnimationFrame` schedules async ticks. Stub it to collect callbacks without executing them, then flush manually:

```typescript
const rafCallbacks: FrameRequestCallback[] = []
vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
  rafCallbacks.push(cb); return rafCallbacks.length;
})
function flushRaf() {
  const pending = rafCallbacks.splice(0);
  pending.forEach(cb => cb(performance.now()));
}
```

Do NOT use a synchronous stub that immediately calls `cb` — the hook's RAF loop will recurse infinitely.

### jsdom limitations to know

- `getBoundingClientRect` returns all-zeroes by default. `VoteWeb` tests must mock it on specific elements before asserting SVG line positions.
- `HTMLMediaElement.play` is not implemented — stub it in `src/test/setup.ts`:
  ```typescript
  Object.defineProperty(window.HTMLMediaElement.prototype, 'play', {
    writable: true, value: vi.fn().mockResolvedValue(undefined),
  })
  ```

---

## Import Conventions

```
engine/
  config.py          ← settings (pydantic-settings, lru_cache)
  roles_loader.py    ← ROLE_REGISTRY, WAKE_ORDER, DYNAMIC_TEMPLATES (loaded once)
  state/
    enums.py         ← StrEnum definitions
    models.py        ← Pydantic models (MasterGameState, PlayerState, NightActions, …)
  resolver/
    night.py         ← resolve_night()
    day.py           ← resolve_day_vote()
    _win.py          ← check_win_condition()
  phases/
    machine.py       ← transition_phase(), compute_actions_required(), should_auto_advance()
  setup.py           ← build_composition(), assign_roles(), setup_game()
  stripper.py        ← player_view(), strip_fabricated_flag()

api/
  intents/
    errors.py        ← IntentError
    dispatch.py      ← route_intent()
    handlers.py      ← handle_*() functions
  lobby/
    routes.py        ← REST endpoints (POST /games, /join, /rejoin)
  main.py            ← FastAPI app, lifespan, WebSocket endpoint
  connection_manager.py  ← WebSocket room management
  timer_tasks.py     ← asyncio timer tasks for phase auto-advance
  store.py           ← Redis read/write helpers
```

Avoid importing from `api/` inside `engine/`. The engine layer is pure Python with no FastAPI dependency. Tests import directly from `engine/` without starting the server.
