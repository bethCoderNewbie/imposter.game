# Werewolf — Operations Runbook

**Audience:** Server operators and on-call engineers.
**Format:** Symptom → Diagnosis → Fix.

---

## Local Dev Setup

### Prerequisites
- Python 3.11+
- Redis 7+ (`redis-server` or Docker)
- Node 18+ (for frontends)

### Backend

```bash
cd backend-engine
pip install -e ".[dev]"
redis-server &          # or: docker run -p 6379:6379 redis
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Mobile frontend

```bash
cd frontend-mobile
npm install
npm run dev             # proxies /api and /ws to localhost:8000
```

### Display frontend

```bash
cd frontend-display
npm install
npm run dev
```

---

## Running Tests

The test suite uses pytest markers to separate tiers by dependency level. No tier leaks into a faster tier.

### Tier 1 — Unit tests (no external services)

```bash
# All unit tests (engine, storage, intent handlers)
pytest -m "not integration and not e2e" -v

# Stripper security tests only (highest priority — run these first)
pytest backend-engine/tests/engine/test_stripper.py -v

# Redis store tests only (uses fakeredis in-process)
pytest backend-engine/tests/storage/ -v

# With coverage report
pytest -m "not integration and not e2e" --cov=backend-engine --cov-report=term-missing
```

### Tier 2 — Integration tests (fakeredis, no real Redis)

Integration tests exercise the full HTTP and WebSocket stack via `starlette.TestClient` with an in-process `FakeRedis` instance replacing the production Redis connection.

```bash
pytest -m "integration" -v
```

### Tier 3 — E2E tests (real Redis required)

E2E tests run the complete request path through a real Redis instance. They automatically skip when Redis is unreachable, so running `pytest` without `REDIS_URL` set is always safe.

```bash
# Requires Redis at the URL specified (defaults to localhost:6379/15)
REDIS_URL=redis://localhost:6379/15 pytest -m "e2e" -v

# Or start a throwaway Redis container first:
docker run -d --rm -p 6379:6379 redis
pytest -m "e2e" -v
```

### Frontend (Vitest + jsdom — no browser required)

```bash
cd frontend-display

# Run all tests once (CI mode)
npm run test -- --run

# Watch mode (re-runs on file change)
npm run test:watch

# With V8 coverage report
npm run test:coverage
```

### Full suite (all tiers)

```bash
# Single command — runs all backend + frontend tests
REDIS_URL=redis://localhost:6379/15 pytest && cd frontend-display && npm run test -- --run
```

### Running only the full game flow tests

The phase-integration and win-condition tests drive the game through complete phase loops. Run them in isolation when debugging game logic:

```bash
# Phase integration: ROLE_DEAL → NIGHT → DAY → DAY_VOTE → GAME_OVER (fakeredis, fast)
pytest backend-engine/tests/api/test_game_phases_integration.py -v

# Win conditions: full village-wins and werewolf-wins round-trips (real Redis required)
REDIS_URL=redis://localhost:6379/15 pytest backend-engine/tests/e2e/test_game_win_conditions.py -v

# Both together with verbose output
REDIS_URL=redis://localhost:6379/15 pytest \
  backend-engine/tests/api/test_game_phases_integration.py \
  backend-engine/tests/e2e/test_game_win_conditions.py \
  -v --tb=short
```

### When E2E tests are skipped

E2E tests auto-skip when Redis is unreachable. This is safe — it is the intended behavior for developer machines without local Redis.

```
SKIPPED [1] tests/e2e/conftest.py:XX - Redis not available at redis://localhost:6379/15 — skipping E2E tests
```

To run them, start Redis first:

```bash
# Option A: use a local Redis server
redis-server &

# Option B: throwaway Docker container
docker run -d --rm -p 6379:6379 redis:7-alpine

# Then run with explicit URL
REDIS_URL=redis://localhost:6379/15 pytest -m "e2e" -v
```

If you want to confirm E2E tests skip cleanly (no failures, no hanging):

```bash
# No REDIS_URL set → all e2e tests should show SKIPPED, not FAILED
pytest -m "e2e" -v
```

### Full suite via Docker (no local Python/Node required)

```bash
# Backend tests (unit + integration)
docker compose -f docker-compose.test.yml run --rm backend-test

# Frontend tests
docker compose -f docker-compose.test.yml run --rm frontend-test
```

### Test counts (as of 2026-04-13)

| Suite | Marker | Tests |
|-------|--------|-------|
| Backend — engine (pure unit) | *(none)* | 118 |
| Backend — storage/Redis (fakeredis) | *(none)* | 35 |
| Backend — intent handlers (unit) | *(none)* | 13 |
| Backend — lobby REST API (integration) | `integration` | 35 |
| Backend — WebSocket auth (integration) | `integration` | 14 |
| Backend — full phase flow (integration) | `integration` | 29 |
| Backend — game win conditions (E2E) | `e2e` | 18 |
| Frontend display — hooks | — | 39 |
| Frontend display — components | — | 105 |
| Frontend mobile — hooks | — | 10 |
| Frontend mobile — components + routing | — | 82 |
| **Total** | | **~431** |

*+2 display `useGameState` regression tests for state-id fence reset (ADR-019)*
*+6 `CreateMatchScreen` tests for pre-game settings UI and PATCH flow (PRD-011)*
*+2 mobile `useGameState` regression tests for rematch redirect fence reset (ADR-019)*

The 29 phase-integration tests cover ROLE_DEAL→NIGHT→DAY→DAY_VOTE→HUNTER_PENDING→GAME_OVER, security stripping, and the state_id fence (1 skipped when doctor is not in the seeded composition). The 18 E2E tests cover full village-wins and werewolf-wins round-trips via real Redis (auto-skipped without Redis).

### Using the `tests/helpers/` package for debugging

The three helper modules in `backend-engine/tests/helpers/` are reusable from the Python REPL or a scratch test when you need to reproduce a specific game scenario:

**`game_driver.py`** — drive a game through phases via the real HTTP+WS stack:

```python
from tests.helpers.game_driver import create_and_fill, drive_role_deal, drive_night, drive_to_day_vote, drive_votes

game_id, host_secret, players = create_and_fill(client, n=5)
client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})

with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
    display_ws.receive_json()          # consume initial sync
    drive_role_deal(client, game_id, players, display_ws)
    # game is now in NIGHT — inspect display_ws state here
```

**`role_utils.py`** — discover which player has which role (must call BEFORE opening display WS):

```python
from tests.helpers.role_utils import collect_role_map, first_with_role, players_with_role

# Call BEFORE opening display WebSocket to avoid disconnect-broadcast buffer pollution
role_map = collect_role_map(client, game_id, players)
# role_map = {"pid-1": "werewolf", "pid-2": "seer", ...}

wolf = first_with_role(role_map, "werewolf", players)
villagers = players_with_role(role_map, "villager", players)
```

**`ws_patterns.py`** — drain WS messages until a condition is met:

```python
from tests.helpers.ws_patterns import consume_until, until_phase

# Tolerates disconnect-noise broadcasts; raises AssertionError after max_messages
night_msg = consume_until(display_ws, until_phase("night"), max_messages=20)
```

---

### Game test failure modes

**`drive_night` / `consume_until` hangs indefinitely (timeout)**
- Cause: Not all `actions_required_count` night actions were submitted. Auto-advance never fires, so no DAY broadcast is sent, and `consume_until` blocks waiting.
- Most common cause: Doctor is present in the composition but no doctor action was included in `night_acts`. Doctor has `wakeOrder > 0` so it counts toward `actions_required_count`.
- Fix: Always include doctor in `night_acts` when doctor is in the composition. Use `_build_night_acts()` from the integration tests — it auto-fills doctor protecting seer.

**`AssertionError: predicate not matched after N messages` (consume_until)**
- Cause: Disconnect-broadcast noise from a closed player WS was consumed instead of the expected phase broadcast.
- After `drive_role_deal` returns (consuming NIGHT), the last `send_player_intent` disconnect broadcast may still be buffered. The next `receive_json()` reads that noise message instead of the expected update.
- Fix: Always use `consume_until(ws, predicate)` rather than a bare `ws.receive_json()` to drain WS; the helper tolerates noise broadcasts automatically.

**Role discovery returns wrong role / `None` role**
- Cause: `collect_role_map()` was called AFTER a display WS was already open. When player WS connections close during role collection, each closure generates a `player_disconnected` broadcast. These accumulate in the display WS buffer, and a subsequent `consume_until` may read them first.
- Fix: Always call `collect_role_map()` before `client.websocket_connect(".../display")`.

**`STALE_STATE` error in tests**
- Cause: Test sent an intent with an explicit `state_id` that is no longer current (e.g., state advanced between the read and the submit).
- Fix for tests: Omit `state_id` from all test intents unless the test is specifically validating the fence. Missing `state_id` = fence bypassed. The fence only activates when `state_id` is explicitly present and doesn't match.

**Self-vote error (`SELF_VOTE_NOT_ALLOWED`) in voting tests**
- Cause: A naive loop like `for pid in alive_pids: vote(pid, target=target_pid)` fails when `pid == target_pid` (player voting for themselves).
- Fix: Use `_vote_everyone_for(target)` from the integration tests: target votes for any other alive player; everyone else votes for target. Guarantees strict majority for N≥2 without self-votes.

**Win-condition test fails: `winner == None` after game should be over**
- Cause: Game hasn't reached a win condition yet. Wolf count and village count math may differ from expectations if the composition varies (doctor can save, hunter can kill after elimination).
- Fix: Verify `alive_pids` before driving votes; after eliminating the wolf, check `phase == "game_over"` via `consume_until` with `lambda m: m.get("state",{}).get("phase") == "game_over"`.

**Doctor save test skipped (1 skipped in phase-integration suite)**
- This is expected. `test_doctor_save_prevents_wolf_kill` is skipped when the seeded game composition doesn't include a doctor. The skip message is: `no doctor in this game composition — skipping doctor save test`. This is correct behavior; do not convert to a failure.

---

### Grid system failures (production + test)

**`INVALID_GRID_COORDS` error returned on `select_grid_node`**
- Cause: Mobile client sent `row` or `col` outside [0, 4], or a non-integer value.
- Diagnosis: Check the intent payload logged by `logger.exception` in `game_queue.py`. Values of `5`, `null`, or strings are the typical culprits.
- Fix: Ensure the `GridMapUI` component clamps indices from the `gridLayout` array and never passes out-of-range values. The 5×5 grid is always 0-indexed — any `row/col >= 5` is a client bug.

**`NODE_OCCUPIED` error on node tap**
- Cause: A node already appears in `grid_activity` (it was completed earlier in the same night). The display greys out completed nodes, but a stale or replayed intent can target them.
- Diagnosis: Compare `grid_activity` in the current state broadcast against the tapped coordinates.
- Fix: The `GridMapUI` `completedSet` check prevents this in normal play. If occurring in tests, verify `grid_activity` is reset by `transition_phase("night")` and not carried over from the previous round.

**`PUZZLE_ALREADY_ACTIVE` error on node tap**
- Cause: Player tapped a new node while `grid_puzzle_state.active == true`. The grid UI disables node buttons when a puzzle is active, but a double-tap or race condition can bypass this.
- Diagnosis: Confirm `myPlayer.grid_puzzle_state?.active` is `true` in the state snapshot received before the second tap.
- Fix: UI guard in `GridMapUI`: `if (hasActivePuzzle) return` on `handleNodeTap`. If triggered in tests, ensure the mock state has `grid_puzzle_state = null` before simulating a node select.

**Sonar ping results empty despite grid activity**
- Cause: Wolf pinged a quadrant before any villager solved a node in that quadrant, OR `grid_activity` was not yet broadcast when the ping fired.
- Diagnosis: Check `grid_activity` in the wolf's state view. Confirm `node_to_quadrant(row, col)` maps the completed node to the expected quadrant (center row 2 and center col 2 fall in "bottom_right" and "right" respectively — see `puzzle_bank.py:node_to_quadrant`).
- Fix: No fix needed — empty ping result is correct behavior when the quadrant has no activity.

**Wolf radar ripple animation not firing**
- Cause: `grid_ripple` side-channel WS event not handled by the client.
- Diagnosis: Check browser DevTools Network → WS frames for `{"type":"grid_ripple",...}` messages.
- Fix: Confirm `useGameState.ts` has the `grid_ripple` branch in `handleMessage`, and `App.tsx` passes `onRipple` to `useGameState`. Confirm `latestRipple` prop is forwarded through `NightActionShell` to `WolfRadarUI`.

**`grid_layout` is `null` during night phase**
- Cause: `generate_grid_layout` import failed, or the NIGHT phase entry block in `machine.py` did not execute (e.g., early return bug).
- Diagnosis: Check server logs for import errors on `engine.puzzle_bank`. Verify the `transition_phase("night")` code path reaches `G.night_actions.grid_layout = generate_grid_layout(...)`.
- Fix: Ensure `puzzles.md` is accessible (see `FileNotFoundError` above — `puzzle_bank.py` reads it at module load, and the import fails if the file is missing).

---

### Common test failure symptoms

**`FileNotFoundError: roles.json not found`** (backend Docker tests)
- The test container is missing `docs/architecture/roles.json`
- Fix: add `COPY docs/architecture/roles.json ./docs/architecture/roles.json` to `backend-engine/Dockerfile.test`

**`FileNotFoundError: puzzles.md not found`** (backend Docker tests)
- The test container is missing `puzzles.md` at the project root
- Fix: add `COPY puzzles.md ./puzzles.md` to `backend-engine/Dockerfile.test`

**`play spy was called unexpectedly`** (NightScreen / GameOverScreen frontend tests)
- Mock call counts not reset between tests
- Fix: ensure `clearMocks: true` is set in `vitest.config.ts`

**`jsdom does not implement HTMLMediaElement.play`** (audio component tests)
- Fix: confirm `src/test/setup.ts` stubs `HTMLMediaElement.prototype.play` with `vi.fn().mockResolvedValue(undefined)`

---

## Redis Session Management

### View active game keys

```bash
redis-cli KEYS "wolf:game:*"
```

### Inspect a game state

```bash
redis-cli GET wolf:game:<GAME_ID> | python -m json.tool
```

### Delete a stuck game

```bash
redis-cli DEL wolf:game:<GAME_ID>
```

### Check session token

```bash
redis-cli GET wolf:token:<TOKEN>
# Returns "game_id:player_id" or (nil)
```

### Flush all game sessions (⚠ destructive — use only in dev)

```bash
redis-cli --scan --pattern "wolf:*" | xargs redis-cli DEL
```

---

## Database Management (Postgres + Alembic)

### Check current migration state

```bash
docker compose exec postgres psql -U werewolf -d werewolf \
  -c "SELECT version_num FROM alembic_version;"
```

Expected output on a fully migrated DB:

```
    version_num
--------------------
 c3d4e5f6a7b8
(1 row)
```

If the table does not exist yet, no migrations have been run (see "Apply pending migrations" below).

### Migration chain

```
04bbb7370b42 → a1b2c3d4e5f6 → b2c3d4e5f6a7 → c3d4e5f6a7b8
initial         narrator_scripts  reseed          hunter+no_elim
```

### Apply pending migrations (upgrade to head)

Run from the project root while the `postgres` container is healthy:

```bash
docker compose run --rm \
  -e DATABASE_URL=postgresql+asyncpg://werewolf:werewolf@postgres/werewolf \
  backend alembic upgrade head
```

Or, if the backend service is already running:

```bash
docker compose exec backend alembic upgrade head
```

### Full dev reset — wipe all data and re-seed

Use when you want a completely clean database (clears player registry, game history, and
narrator_scripts, then re-seeds via migrations):

```bash
# 1. Drop and recreate the public schema (removes all tables + alembic_version)
docker compose exec postgres psql -U werewolf -d werewolf \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION werewolf;"

# 2. Re-run all migrations to head (recreates tables + seeds narrator_scripts)
docker compose run --rm \
  -e DATABASE_URL=postgresql+asyncpg://werewolf:werewolf@postgres/werewolf \
  backend alembic upgrade head
```

### Verify after reset

```bash
# Confirm revision is at head
docker compose exec postgres psql -U werewolf -d werewolf \
  -c "SELECT version_num FROM alembic_version;"
# → c3d4e5f6a7b8

# Confirm narrator_scripts is seeded (11 trigger types)
docker compose exec postgres psql -U werewolf -d werewolf \
  -c "SELECT trigger_id, COUNT(*) FROM narrator_scripts GROUP BY trigger_id ORDER BY trigger_id;"

# Confirm data tables are empty
docker compose exec postgres psql -U werewolf -d werewolf \
  -c "SELECT COUNT(*) FROM players; SELECT COUNT(*) FROM games;"
# → 0, 0
```

### Narrator Scripts: data model and sync

`narrator_scripts` stores the subtitle text for every pre-baked narrator audio clip.
It does **not** store file paths; paths are computed at runtime.

| Column       | Type        | Description                                      |
|--------------|-------------|--------------------------------------------------|
| `id`         | Integer PK  | Auto-increment; determines subtitle index         |
| `trigger_id` | String(32)  | Event type (e.g. `game_start`, `vote_open`)       |
| `text`       | Text        | Script line; may contain `{eliminated_name}` placeholder |

**Index contract:** `pick_prebaked()` selects `game_start_07.wav` and derives index `7`.
`get_preset_script(trigger_id, index=7)` then fetches the 8th row (0-based) from
`SELECT … WHERE trigger_id='game_start' ORDER BY id`. The WAV suffix and the DB row order
**must stay in sync** — the `b2c3d4e5f6a7` reseed migration preserves this by doing
`DELETE` + `bulk_insert` in the exact same order as the pre-baked files were generated.

#### Expected row counts after full migration (head = c3d4e5f6a7b8)

```bash
docker compose exec postgres psql -U werewolf -d werewolf \
  -c "SELECT trigger_id, COUNT(*) FROM narrator_scripts GROUP BY trigger_id ORDER BY trigger_id;"
```

Expected output:

```
    trigger_id     | count
-------------------+-------
 day_open          |    40
 game_start        |    32
 hunter_revenge    |    20
 night_close       |    32
 night_open        |    30
 no_elimination    |    20
 player_eliminated |    33
 village_wins      |    21
 vote_elimination  |    20
 vote_open         |    33
 wolves_win        |    20
(11 rows)
```

Any deviation — wrong count, missing trigger_id, or extra row — means the table is out of sync.

#### Symptom: subtitle shown does not match what is being played

Cause: `narrator_scripts` row counts or order do not match the pre-baked WAV files in
`backend-engine/api/narrator/audio/<voice>/`.

Fix: **Full dev reset** (see "Full dev reset" above). This is the only supported path because
`b2c3d4e5f6a7`'s `downgrade()` is a no-op — running `alembic downgrade` then `upgrade head`
will **not** reseed the table; use the DROP SCHEMA approach instead.

### Symptom: alembic_version table does not exist

The DB has never been migrated. Run `alembic upgrade head` (see above).

### Symptom: version_num does not match current head

One or more migrations are pending. Run `alembic upgrade head` to apply them.

### Note: narrator_voice does not require a migration

`narrator_voice` is a field on `GameConfig` which is stored in Redis, not Postgres.
Adding or changing it requires no Alembic migration.

---

## Match Lifecycle (Step by Step)

1. **Display TV** opens `POST /api/games` → receives `game_id`, `host_player_id`, `session_token`
2. **Display TV** connects WebSocket `/ws/{game_id}/display`
3. **Players** scan QR code → `POST /api/games/{game_id}/join` → receive `player_id`, `session_token`
4. **Players** connect WebSocket `/ws/{game_id}/{player_id}` → send `{"type":"auth","session_token":"..."}`
5. **Host player** sends `{"type":"start_game","player_id":"...","state_id":0}`
6. **Server** assigns roles, transitions to `role_deal` phase, broadcasts stripped state per socket
7. **Players** hold to reveal role → send `confirm_role_reveal` → server auto-advances to `night` when all confirmed
8. **Night loop:** players submit night actions → server auto-resolves when all `wakeOrder>0` players submitted
9. **Day loop:** host sends `advance_phase` (DAY → DAY_VOTE) → players cast votes → server resolves
10. **Repeat** night/day until win condition met

---

## Duplicate Players in Lobby or Active Game

### Symptom: Display shows two (or more) entries with the same name

Players in the lobby or mid-game appear multiple times on the display TV. Each duplicate entry has the same `display_name` but a different `player_id`. Only one entry ever shows as connected; the rest remain permanently grey/disconnected.

**Cause:** A mobile player retried the join form after a network failure. The server processed each retry as a new join during the LOBBY phase, creating one player slot per HTTP attempt. See ADR-024 for full root-cause analysis. Fixed in commit after 2026-04-14 — this symptom cannot recur once the fix is deployed.

---

### Diagnosing a game that already started with ghost players

**1. Identify the game ID** from the display URL or host's browser (e.g., `QVN9`).

**2. Inspect the live game state in Redis:**
```bash
redis-cli GET wolf:game:QVN9 | python3 -m json.tool | grep -A3 '"permanent_id"'
```
Look for repeated `permanent_id` values — each occurrence is a separate player slot for the same physical person.

**3. Find the ghost player IDs** (the ones with no active WebSocket):
```bash
redis-cli GET wolf:game:QVN9 | python3 -m json.tool | python3 -c "
import json, sys
G = json.load(sys.stdin)
seen = {}
for pid, p in G['players'].items():
    perm = p.get('permanent_id', '')
    seen.setdefault(perm, []).append((pid, p.get('display_name'), p.get('is_connected')))
for perm, entries in seen.items():
    if len(entries) > 1:
        print(f'DUPLICATE permanent_id={perm}:')
        for pid, name, conn in entries:
            print(f'  player_id={pid}  name={name}  is_connected={conn}')
"
```

**4. Identify which is the active slot** — it will have `is_connected: true` or will be the one whose `session_token` is still valid in Redis:
```bash
# Check if a session token is still live (replace TOKEN with value from game state)
redis-cli GET wolf:token:TOKEN
```

**5. Accept the situation** — there is no safe hot-patch to remove a ghost slot from an in-progress game without risking state corruption. Ghost players:
- Hold a role (they received one at game start)
- Will never submit night actions or votes (permanently disconnected)
- The game engine's auto-resolve logic will time out their action slot and advance normally
- They show as grey/dead-looking on the display for the remainder of the game

**6. At game over** — the ghosts appear in the role-reveal grid. Explain to players that the extra entries are disconnected retry slots, not real participants.

---

### Prevention

ADR-024 (`docs/architecture/adr/ADR-024_lobby_join_idempotency.md`) documents the fix: `POST /api/games/{game_id}/join` is now idempotent during LOBBY phase. Retrying a failed join returns the existing player slot and a fresh token instead of creating a new entry. Deploy the fix to prevent recurrence.

---

## Diagnosing WebSocket Issues

### Symptom: Mobile client shows "Reconnecting…" immediately after joining via QR code

**Cause (display logic):** `App.tsx` uses `status === 'connecting'` to decide whether to show "Connecting…" or "Reconnecting…". After the WebSocket handshake completes, `status` becomes `'open'` while the client waits for the first `sync` message from the server. Since `'open' !== 'connecting'`, the screen incorrectly shows "Reconnecting…" during this window.

**Cause (backend silent failure):** If `load_game` returns `None` after a successful auth (rare edge case: game TTL expired between join and WS connect), the server never sends the initial `sync` and never sends an error. The client stays at `status='open'`, `gameState=null`, and "Reconnecting…" persists indefinitely.

**Fix applied (frontend `App.tsx:115`):**
```tsx
// Before — wrongly shows "Reconnecting…" when status is 'open'
<p>{status === 'connecting' ? 'Connecting…' : 'Reconnecting…'}</p>

// After — "Reconnecting…" only when connection is actually down
<p>{status === 'closed' ? 'Reconnecting…' : 'Connecting…'}</p>
```

**Fix applied (backend `endpoint.py:101`):**
Added `else` branch: if game state not found after auth, send `GAME_NOT_FOUND` error and close with code 1011, so the client can surface an error instead of hanging.

**Diagnosis steps (if still occurring after the fix):**
1. Open browser DevTools → Network → WS tab → confirm the WebSocket upgrades to 101 Switching Protocols
2. Inspect WS frames: look for `{"type":"error","code":"AUTH_FAILED"}` — if present, the session token is invalid; clear `localStorage` (`ww_session` key) and rejoin
3. Inspect WS frames: if only the auth frame is sent and the socket closes silently, check backend logs for Redis errors

---

### Symptom: Mobile client stuck on "Connecting..."

**Possible causes:**
- Session token expired (4-hour TTL)
- Game not found in Redis (TTL expired or game deleted)
- Backend not running

**Fix:**
1. Check backend logs: `uvicorn` output
2. Verify Redis: `redis-cli KEYS "wolf:game:*"`
3. Player must `POST /api/games/{game_id}/rejoin` with stored session token

### Symptom: Mobile client shows "Auth Failed"

**Possible causes:**
- Wrong game_id in URL vs session token's game_id
- Stale token from a previous game session

**Fix:**
- Clear `localStorage` in browser DevTools (Application → Local Storage → `ww_session`)
- Rejoin the game via the join URL

---

### Symptom: Mobile player lands on onboarding form after the game has already started

**Cause:** The player's `localStorage` entry for `ww_session` is missing (browser cleared storage, or the player is on a new device). Without a stored session token, `App.tsx loadSession()` returns `null` and shows onboarding. `POST /api/games/{id}/join` then rejects with 409 "Game already started" because the game is past the `lobby` phase.

**Resolution (current behavior):**

1. **Bootstrap auto-rejoin**: On mount, `App.tsx` calls `POST /api/games/{stored.game_id}/rejoin` with the stored token. If successful, the player is returned to the game directly without seeing the form. The bootstrap now only clears the session on 401/404 (definitively invalid) — transient 5xx/network errors preserve the token so the next app open retries automatically.

2. **OnboardingForm 409 → auto-rejoin**: If the player enters a game code and JOIN returns 409 (game already started), `OnboardingForm` silently tries `POST /rejoin` using any matching session stored in `localStorage`. If this succeeds, the player is returned to the game without manual action.

3. **Manual rejoin via token**: If both auto-paths fail (session genuinely lost), the form switches to "Rejoin" mode showing a session token input + game code. The player pastes their token and clicks "Rejoin Game" → calls `POST /rejoin`.

4. **"Returning player?" link**: Visible on the join form at all times — lets a player skip directly to rejoin mode without hitting the 409 first.

**Finding the session token for manual rejoin (host / dev):**
```bash
# Get the token for a specific player in a game
docker compose exec redis redis-cli GET wolf:game:<GAME_ID> | \
  python -m json.tool | grep -A2 '"display_name": "<PLAYER_NAME>"'
# Look for "session_token" field in that player's object
```

**When the player genuinely cannot rejoin** (new device, no token, game in progress):
- The host can extract the token from Redis as above and share it out-of-band
- Or the host waits for game-over, then triggers a rematch which migrates all players

---

### Symptom: Mobile player sees old game-over screen after "Play Again" — cannot reach new game

**Cause:** The Display host clicked "Play Again" (triggering `POST /api/games/{id}/rematch`) while the mobile player's WebSocket was closed. The `redirect` message was broadcast only to live sockets; the disconnected player never received it. On reconnecting to the old game, they see `phase: game_over` with no path forward.

**Root fix (ADR-013):** `MasterGameState.rematch_redirect` stores the full redirect payload on the old game. `endpoint.py` replays it to any reconnecting player whose `player_id` is in the migration map. This should auto-forward them to the new game lobby.

**Diagnosis if the fix does not trigger:**
1. Check Redis: `redis-cli GET wolf:game:<OLD_GAME_ID> | python -m json.tool | grep rematch_redirect`
   If `null`, the rematch was called before ADR-013 was deployed — old game has no forwarding pointer.
2. Check WS frames in DevTools: after the initial `sync`, a second `redirect` frame should arrive within milliseconds.
3. If `rematch_redirect` is present but player is not in the `players` map: the player joined with a different `player_id` than the one in the migration map (should not happen in production — player IDs are stable per join).

**Workaround (if needed):** Player uses the new game QR code directly. The new game is in `lobby` phase until the host starts it, so `POST /api/games/{new_id}/join` accepts new entries.

### Symptom: Display stuck on game-over screen after "Play Again" or "New Match → Create New Match"

**Cause (ADR-019):** `useGameState.ts` maintains a `lastStateIdRef` fence to discard replayed messages. This fence was not reset when `gameId` changed. The new game starts at `state_id = 1`, but the fence from the completed game may be at `state_id = 100+`. Every message from the new game fails the `msg.state_id > fence` check and is silently dropped. `gameState` stays frozen at the old `phase: "game_over"`.

**Fix applied (both `frontend-display/src/hooks/useGameState.ts` and `frontend-mobile/src/hooks/useGameState.ts`):**
```ts
// Resets fence (-1 accepts any state_id ≥ 0) and clears stale state
useEffect(() => {
  lastStateIdRef.current = -1
  setGameState(null)
}, [gameId])
```

**Diagnosis (if regression):**
1. Open DevTools → Network → WS tab. After "Play Again", confirm the display opens a new WebSocket to `/ws/<new_game_id>/display`.
2. In the new WS frame list, verify a `sync` frame is received with `state_id: 1` and `phase: "lobby"`.
3. If the `sync` frame is present but the screen does not update: `lastStateIdRef` is above 1. The `useEffect` reset is not running — check that `gameId` state is actually changing (confirm `setGameId(newGameId)` fires in the `onPlayAgain` callback).

---

### Symptom: Player gets `STALE_STATE` error

**Cause:** Client sent an intent with `state_id` that doesn't match current server `state_id` — this means another action was processed between the client reading state and submitting the intent.

**Fix:** Client should retry automatically after receiving updated `state_update` from the server.

### Symptom: "Phase timeout" fires but phase doesn't advance

**Possible causes:**
- Game already advanced (stale timeout, expected behavior — logged and ignored)
- Backend restarted — all in-memory timer tasks are cleared on restart

**Fix:** On backend restart, active games have no timer tasks. The host can manually advance phase or the next player action will trigger auto-advance.

### Symptom: Display shows wrong phase

**Cause:** Display WebSocket may have reconnected and received a cached `state_update`.

**Fix:** Display client sends `player_id="display"` — no auth required. Disconnect and reconnect to re-receive current state broadcast.

### Symptom: QR code not reachable from phones

**Cause:** Display and phones on different network segments, or firewall blocking port 3001.

**Fix:**
- Verify all devices on same LAN/Wi-Fi
- Check `start.sh` auto-detected LAN IP is correct: `hostname -I | awk '{print $1}'`
- Manually export: `export MOBILE_BASE_URL=http://<correct-ip>:3000`
- Run `./start.sh <correct-ip>` to override

### Symptom: Villager mobile screen stuck on "The Archives await…" — puzzle never renders

**Cause:** Frontend type mismatch introduced by ADR-008. The backend stores `puzzle_state` on each `PlayerState` (at `players[pid].puzzle_state`), but the old frontend was reading `gameState.night_actions.puzzle_state` which is never populated by the stripper. The puzzle UI renders `null` forever and no hint can be earned.

**Fix applied (`VillagerDecoyUI.tsx:17`):**
```tsx
// Before — reads from wrong location (NightActions never has puzzle_state)
const puzzle = gameState.night_actions.puzzle_state ?? null

// After — reads from own PlayerState (correct per ADR-008)
const puzzle = myPlayer.puzzle_state ?? null
```
**Also fixed:** Added `puzzle_state?: PuzzleState | null` to `PlayerState` in `types/game.ts` and removed the stale `puzzle_state` field from `NightActions`.

---

### Symptom: Framer's night action rejected with `INVALID_ACTION`

**Cause:** `NightActionShell` routed the `framer` role to `WolfVoteUI`, which sends `{ type: "submit_night_action", target_id: "..." }`. The backend handler (`handlers.py:170`) requires `framer_action: "frame" | "hack_archives"` — without it the intent is rejected immediately.

**Fix applied:**
- Created `FramerUI.tsx` — two-step flow: mode selection → frame (pick target) or hack archives (preset/custom false hint builder). Submits proper `framer_action` field.
- Updated `NightActionShell.tsx` to route `role === 'framer'` to `FramerUI` before the `WOLF_ROLES.has(role)` fallback.

---

### Symptom: Hints are specific in round 1 (vague text not showing)

**Cause:** `G.round` starts at 1 for the first night. The vague threshold is `_VAGUE_ROUND_THRESHOLD = 3` (`puzzle_bank.py`), so rounds 1 and 2 (`G.round < 3`) should produce vague text. If specific text appears in round 1, the most likely cause is `G.round` being incorrectly incremented before the night phase starts.

**Diagnosis:** Check `MasterGameState.round` in the Redis state dump for the affected game. If `round >= 3` in what should be the first night, the phase machine is double-incrementing round. See `engine/phases/machine.py` — round is incremented at the top of `_enter_night()`.

---

### Symptom: `non_wolf_kill` hint never appears even when SK/Arsonist is active

**Causes to check (in order):**

1. **Round guard.** `non_wolf_kill` requires `G.round >= 2`. It is impossible in round 1 (no previous night's data exists). Confirm the hint is being sought in round 2+.

2. **Phase mismatch in elimination_log.** The filter requires `e.phase == "night"`. Hunter revenge kills that occur during the day (`e.phase == "day"`) will not trigger this hint even though their cause (`hunter_revenge`) is in `_NON_WOLF_CAUSES`. Check the `elimination_log` entries for the relevant round.

3. **Cause value mismatch.** Verify the `EliminationCause` enum value is the string `"serial_killer_kill"` (not `"serial_killer"`). See `engine/state/enums.py:54`.

4. **Pool selection.** Even if `non_wolf_kill` enters the pool, `rng.choice(pool)` may select a different category. With 4–6 pool entries, the probability of selecting any specific one is ~17–25% per puzzle solve. Run `pytest tests/engine/test_puzzle_bank.py -k non_wolf_kill` to confirm the category enters the pool correctly.

---

### Symptom: `lovers_exist` hint never appears in a Cupid game

**Cause:** `G.lovers_pair` is `None`. Confirm Cupid's round-1 action was submitted and processed. Check `G.night_actions.cupid_link` in the round-1 state dump — if it is non-null but `G.lovers_pair` is still null, the night resolver failed to persist the link at step N (Cupid linking step). See `engine/resolver/night.py`.

---

### Symptom: Audio does not play on Display TV

**Cause:** Browser autoplay policy requires a user gesture before AudioContext can be unlocked.

**Fix:** The game host must click "Start Game" (or any interactive element) on the Display client before the first Night phase. The `useAudio()` hook unlocks AudioContext on this gesture.

---

## Narrator (LLM + TTS) — PRD-008

The narrator pipeline is: **game event → Ollama LLM** (generates text) **→ Kokoro TTS** (synthesises WAV) **→ WebSocket `narrate` message → display browser plays audio**.

All steps are fire-and-forget — failure at any stage is silent and the game continues normally.

### Enabling narrator

Set `NARRATOR_ENABLED=true` in `.env`. Ollama and Kokoro run as Docker Compose services; no host install is required.

### Checking service health

```bash
docker compose ps ollama          # should show "healthy"
docker compose ps tts             # should show "Up"
docker compose logs tts | tail -5 # Kokoro: "Uvicorn running on http://0.0.0.0:8880"
```

### Confirming narrator fires in-game

```bash
docker compose logs -f backend | grep -i narr
# Expected lines per night resolution:
#   Narrator: trigger=night_close ...
#   Narrator: trigger=day_open ...
```

### Symptom: Narration never fires (no `narr` lines in backend logs)

1. Check `NARRATOR_ENABLED` is set to `true` in the container:
   ```bash
   docker compose exec backend printenv NARRATOR_ENABLED
   ```
2. If `false`, update `.env` and restart: `docker compose up -d backend`

### Symptom: Ollama connection refused / timeout in backend logs

Ollama is not healthy. Check:

```bash
docker compose ps ollama
docker compose logs ollama | tail -20
```

If the service is up but the model hasn't been pulled yet, `ollama-pull` is still running or failed:

```bash
docker compose logs ollama-pull
```

Re-pull manually if needed:

```bash
docker compose run --rm ollama-pull
```

### Symptom: Ollama responds but narration text is empty

The model may not be loaded. Verify via the Ollama API from inside the backend container:

```bash
docker compose exec backend python -c "
import urllib.request, json
r = urllib.request.urlopen('http://ollama:11434/api/tags', timeout=3)
print([m['name'] for m in json.loads(r.read()).get('models', [])])
"
```

If `llama3.2:3b` is not listed, re-run the pull service.

### Symptom: Subtitle appears but no audio plays

The LLM and TTS steps succeeded (subtitle = text from LLM, cleared after `duration_ms`), but the browser couldn't play the audio. Check:

1. **Autoplay lock** — host must have clicked "Click to Begin" on the display before any narration fires.
2. **Audio URL reachable** — open `http://<LAN-IP>/tts/audio/<any>.wav` in the display browser; should return a WAV file (not 404).
3. **Kokoro health** — `docker compose logs tts | grep -i error`

### GPU vs CPU narrator services

`start.sh` auto-detects GPU via `nvidia-smi` and applies `docker-compose.gpu.yml` when found. CPU is the default — no manual changes needed.

To force GPU mode manually:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

To force CPU mode on a GPU host:
```bash
docker compose -f docker-compose.yml up --build
```

CPU inference is slower (~10–30 s per narration vs ~2–5 s on GPU).

### Clearing the model volume (forces re-download)

```bash
docker compose down
docker volume rm imposter_ollama_models
docker compose up -d
```

---

## Deployment (Docker Compose)

### Start all services

```bash
cp .env.example .env
# Edit SECRET_KEY in .env
./start.sh              # auto-detects LAN IP
```

### Service URLs

| Service | URL |
|---------|-----|
| Backend API | `http://<LAN-IP>:8000` |
| Mobile frontend | `http://<LAN-IP>:3000` |
| Display frontend | `http://<LAN-IP>:3001` |
| Health check | `http://<LAN-IP>:8000/health` |

### Stop all services

```bash
docker compose down
```

### View backend logs

```bash
docker compose logs -f backend
```

---

## Hybrid Deployment (Internet Play)

Allows players on **any network** to join without being on the same Wi-Fi.
Backend runs locally; mobile frontend is on Vercel; Cloudflare Tunnel bridges the two.

Full setup guide: `docs/ops/hybrid-deploy.md`

### Deployed endpoints

| Service | URL |
|---|---|
| Mobile (Vercel) | `https://imposter-mobile.vercel.app` |
| Backend tunnel | `https://backend.imposter.com` |
| Display | `http://<LAN-IP>/display/` (LAN only, Docker) |

### Per-session launch

```bash
./start.sh --tunnel
```

### Verify tunnel is up

```bash
curl -s https://backend.imposter.com/api/health
# Expected: {"status":"ok","schema_version":"0.4"}
```

### Ephemeral tunnel (no Cloudflare account needed)

```bash
./start.sh --tunnel-quick
docker compose logs cloudflared-quick | grep trycloudflare
# Copy the printed URL — it is auto-embedded in the QR code via ?b=
```

### One-time Cloudflare configuration (already done)

1. **DNS** — `dash.cloudflare.com` → `imposter.com` → DNS → Records:
   - Type: `CNAME`, Name: `backend`, Target: `b891dd22-6d40-441d-b60a-6479a61c8b4b.cfargotunnel.com`, Proxy: ☁️ Proxied

2. **SSL** — `dash.cloudflare.com` → `imposter.com` → SSL/TLS → Overview → **Full**

3. **Tunnel hostname** — Zero Trust → Networks → Tunnels → `imposter-backend` → Hostname routes:
   - Subdomain: `backend`, Domain: `imposter.com`, Service: `HTTP`, URL: `nginx:80`

### Vercel environment variables

**`imposter-mobile` project** (Settings → Environment Variables):

| Variable | Value |
|---|---|
| `VITE_BACKEND_URL` | `https://backend.imposter.com` |

### `.env` variables (hybrid mode)

| Variable | Value | Flows to |
|---|---|---|
| `CLOUDFLARE_TUNNEL_TOKEN` | `<token>` | `cloudflared` container |
| `BACKEND_URL` | `https://backend.imposter.com` | Backend `BACKEND_PUBLIC_URL` + display `VITE_QR_BACKEND_URL` |
| `MOBILE_URL` | `https://imposter-mobile.vercel.app` | Display `VITE_MOBILE_URL` → QR target |

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `curl` health fails — SSL error | SSL mode not Full | Cloudflare → `imposter.com` → SSL/TLS → **Full** |
| DNS resolves to home IP | CNAME record missing | Add CNAME in Cloudflare DNS (see above) |
| Tunnel shows Down in dashboard | Container not running | `./start.sh --tunnel` |
| "Network error" on Vercel mobile | `VITE_BACKEND_URL` not set or tunnel down | Set Vercel env var; confirm `curl` health passes |
| QR missing `?b=` | `BACKEND_URL` not in `.env` | Add to `.env` and `./start.sh --tunnel` |
| Display broken in LAN mode | Old bug (fixed) | `git pull` to get latest |
| Docker "network not found" | Stale Docker network | `docker network prune -f && ./start.sh --tunnel` |
| Stale game after restart | Old `?b=` in sessionStorage | Player opens a fresh tab |

---

## CI/CD (GitHub Actions)

The pipeline is defined in `.github/workflows/ci.yml`. It runs automatically on every push and pull request.

### Jobs

| Job | Trigger | Redis service | Pytest marker |
|-----|---------|---------------|---------------|
| `backend-unit` | push/PR | No | `not integration and not e2e` |
| `backend-integration` | push/PR | No (fakeredis) | `integration` |
| `backend-e2e` | push/PR | `redis:7-alpine` | `e2e` |
| `frontend-display` | push/PR | No | Vitest (`npm run test -- --run`) |
| `frontend-mobile` | push/PR | No | TypeScript build check |

All jobs run in parallel (`fail-fast: false`) so a failure in one does not cancel the others.

### Checking a failed run

```bash
# View the run in the GitHub UI:
gh run list --limit 5

# Download logs for a specific run:
gh run view <run-id> --log-failed
```

### Secrets

| Secret | Purpose |
|--------|---------|
| `CODECOV_TOKEN` | Coverage upload (optional — CI does not fail without it) |

### Adding a new marker

1. Add the marker declaration to `pyproject.toml` `[tool.pytest.ini_options].markers`.
2. Add a job (or a `run` step) to `.github/workflows/ci.yml` that runs `pytest -m "<new-marker>"`.

---

## Configuration Reference

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | App secret — change in production |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |
| `SCHEMA_VERSION` | `0.4` | Game state schema version |
| `NIGHT_TIMER_SECONDS` | `60` | Night phase duration |
| `DAY_TIMER_SECONDS` | `180` | Day discussion duration |
| `VOTE_TIMER_SECONDS` | `90` | Voting phase duration |
| `ROLE_DEAL_TIMER_SECONDS` | `30` | Role reveal timer |
| `HUNTER_PENDING_TIMER_SECONDS` | `30` | Hunter revenge window |
| `DEBUG` | `false` | Enable debug logging |
| `NARRATOR_ENABLED` | `false` | Enable LLM+TTS narration (PRD-008) |
| `NARRATOR_MODE` | `auto` | `auto` \| `live` \| `static` \| `prebaked` |
| `NARRATOR_PREBAKED_DIR` | (package `audio/`) | Base path for pre-baked WAV directories. Voice subdirectory (`kokoro/`, `cosyvoice-marvin/`, …) is selected per-game via `GameConfig.narrator_voice`. |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama service URL (Docker Compose internal) |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model used for narration text generation |
| `KOKORO_URL` | `http://tts:8880` | Kokoro TTS service URL (Docker Compose internal) |
| `NARRATOR_VOICE` | `af_bella` | Kokoro voice ID |

---

## Narrator — Prebaked Mode (CPU, no external services)

Serves pre-generated WAV files from `backend-engine/api/narrator/audio/` instead of calling
Ollama or Kokoro at runtime. See ADR-021 for design rationale.

### Enabling

```bash
NARRATOR_ENABLED=true
NARRATOR_MODE=prebaked
docker compose up   # no --profile tts needed
```

### Generating audio (developer, one-time)

Fish-Speech must be installed; GPU recommended for speed.

```bash
pip install fish-speech   # or: pip install -e /path/to/fish-speech
python scripts/prebake_tts.py
git add backend-engine/api/narrator/audio/
git commit -m "feat(narrator): add pre-baked Rickman-voice audio files"
```

Naming convention: `{trigger_id}_{index:02d}.wav` → `game_start_00.wav` … `village_wins_19.wav`
Total: 180 files (9 triggers × 20 lines). Estimated size: ~150–200 MB.

### Symptom: audio silent, subtitle shows

1. Check files are present:
   ```bash
   docker compose exec backend ls /app/api/narrator/audio/ | head
   # → empty: WAVs not committed; run prebake script then recommit
   ```
2. Check static route responds:
   ```bash
   curl -I http://localhost:8000/tts/static/game_start_00.wav
   # → 404: backend started before audio/ dir existed; restart backend
   ```
3. Confirm mode:
   ```bash
   docker compose exec backend printenv NARRATOR_MODE
   # → should print "prebaked"
   ```

### Note: audio says "a player", subtitle shows real name

Intentional — see ADR-021. Dynamic triggers (`vote_elimination`, `player_eliminated`) were baked
with `"a player"` substituted for `{eliminated_name}`. The subtitle text uses the real player name
drawn from the DB preset at runtime.

### Symptom: Display client plays wrong voice or gets silent narrator after host changed voice

**Cause:** `narrator_voice` set to a directory with no WAV files, or a directory name typo.
**Fix:** `PATCH /api/games/{id}/config` with a valid voice name — must match a populated subdir
under `api/narrator/audio/`. Available voices: any directory produced by `scripts/prebake_tts.py`
(e.g. `"kokoro"`, `"cosyvoice-marvin"`).

```bash
curl -X PATCH http://localhost:8000/api/games/{game_id}/config \
  -H "Content-Type: application/json" \
  -d '{"host_secret":"...","narrator_voice":"cosyvoice-marvin"}'
# Returns 400 if the subdir does not exist or contains no WAVs.
```
