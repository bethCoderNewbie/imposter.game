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
