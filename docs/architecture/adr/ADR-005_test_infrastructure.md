# ADR-005: Werewolf — Test Infrastructure

## Status
Accepted

## Date
2026-03-27

## Context

The project had 114 backend engine tests (pytest) but zero frontend tests and no Redis-layer tests. Two gaps drove this work:

1. **Frontend had no test suite.** Nine display components and three custom hooks had no automated coverage. Bugs like the audio-spy not being cleared between tests or incorrect vote-majority thresholds could only be caught by manual testing.

2. **Redis store had no isolated tests.** `storage/redis_store.py` contains session-token issuance, TTL management, and game serialization. These had never been tested against a real or simulated Redis — they were only exercised end-to-end through the running server.

The project also had no containerized test runner, so tests could not be run reproducibly without a local Python and Node environment.

---

## Decision

### 1. Frontend: Vitest + jsdom (Not Jest)

**Chosen:** Vitest with the jsdom environment, driven via `vitest.config.ts` in `frontend-display/`.

**Rejected:** Jest with `ts-jest` or `babel-jest`.

**Rationale:**
- Vitest reuses the existing Vite build pipeline. No separate Babel configuration, no `ts-jest` version pinning, no duplicate TypeScript compilation. The test runner reads the same `vite.config.ts` (or a parallel `vitest.config.ts`) that the dev build uses.
- The project already has Vite as the build tool. Adding Jest would introduce a second transformation layer for TypeScript and JSX, with a non-trivial risk of subtle differences between test compilation and production compilation.
- jsdom is preferred over happy-dom because the Display codebase uses `sessionStorage`, `requestFullscreen`, `getBoundingClientRect`, and `document.querySelectorAll` — all of which are fully implemented in jsdom. happy-dom has known gaps for `getBoundingClientRect` (returns zeroes) that break the `VoteWeb` centroid-calculation tests.

**Key configuration choices:**
- `clearMocks: true` — resets spy `.mock.calls` between every test. Required because audio `HTMLMediaElement.play` is a `vi.fn()` stub mounted on the prototype; without clearing, call counts accumulate across tests in the same file.
- `globals: true` — exposes `vi`, `describe`, `it`, `expect` globally. Required for `@testing-library/jest-dom` matchers and consistent with the jsdom environment convention.
- `setupFiles: ['./src/test/setup.ts']` — stubs `HTMLMediaElement.prototype.play/pause` and `document.documentElement.requestFullscreen` so audio components do not throw in the test environment.

### 2. Backend Redis Layer: fakeredis[aioredis] (Not a Real Redis Server)

**Chosen:** `fakeredis.aioredis.FakeRedis()` as an in-memory async Redis fake, injected per-test as a pytest fixture.

**Rejected:** A real Redis server (Docker or native) for unit tests; mocking individual Redis methods with `unittest.mock`.

**Rationale:**
- `fakeredis` is an in-memory implementation of the Redis protocol, not a mock. It enforces correct Redis semantics: TTL expiry, key namespacing, binary value storage, `KEYS` pattern matching. A `unittest.mock.AsyncMock` of `redis.get()` can return anything — it does not verify that the caller used the correct key format or that the TTL was actually set.
- Using a real Redis Docker container in unit tests introduces an external process dependency, makes tests non-deterministic if the container is not isolated per test, and slows the test suite significantly.
- Each test receives a fresh `FakeRedis()` instance from a pytest fixture, so tests are fully isolated with zero teardown overhead.

### 3. Frontend Test Patterns

**FakeWebSocket class:** Tests for `useWebSocket` use a class-based fake rather than patching `window.WebSocket` with individual mocks. The class implements the same interface (`OPEN`, `CLOSED`, `CONNECTING`, `CLOSED` static constants; `send`, `close` as `vi.fn()`; `onopen`, `onclose`, `onmessage`, `onerror` callbacks) and exposes explicit `triggerOpen()`, `triggerClose()`, `triggerMessage(data)`, `triggerError()` methods. This makes test scenarios deterministic and readable.

**Module-level `vi.mock` for hooks:** Component tests for `NightScreen`, `DayScreen`, and `GameOverScreen` mock `useTimer` at the module level (`vi.mock('../../hooks/useTimer', ...)`). This isolates component rendering behavior from hook internals — timer values are injected as test parameters rather than driven by `requestAnimationFrame` timing.

**RAF stub for timer tests:** `useTimer` tests stub `requestAnimationFrame` by collecting callbacks in an array and exposing a `flushRaf()` helper that executes all pending callbacks synchronously. This avoids infinite recursion (the hook's RAF loop would call itself indefinitely in a synchronous environment) and gives tests precise control over when the countdown updates.

### 4. Containerized Test Runner: `docker-compose.test.yml`

**Chosen:** A separate `docker-compose.test.yml` with three services: `redis-test`, `backend-test`, and `frontend-test`.

**Rejected:** Running tests inside the production `docker-compose.yml` services; a single shared test container.

**Rationale:**
- The production `docker-compose.yml` runs a persistent Redis instance and long-lived backend/frontend servers. Tests must not share a Redis instance with a running game — a game key left from a previous run could corrupt test assertions.
- `redis-test` uses a Docker healthcheck (`redis-cli ping`) so `backend-test` only starts after Redis is confirmed ready. This eliminates a class of flaky test failures caused by the backend attempting to connect before Redis has initialized.
- Separate Dockerfiles (`backend-engine/Dockerfile.test`, `frontend-display/Dockerfile.test`) install only test dependencies (`pip install -e ".[test]"`, `npm ci`) — production serve dependencies (uvicorn workers, nginx) are excluded from test images.
- Both test Dockerfiles copy `docs/architecture/roles.json` and `puzzles.md` (project root) into the container. These files are read at module import time; omitting them causes `FileNotFoundError` before any test runs.

---

## Consequences

**Positive:**
- ~420 total tests (114 backend engine + 35 Redis store + 35 frontend hooks + 81 frontend components + 28 integration + 7 e2e + helpers) can be run locally or in Docker without any running services (e2e auto-skip without Redis).
- `storage/redis_store.py` now has 100% line coverage via the fakeredis suite.
- Frontend hook and component tests catch regressions in rendering logic, state transitions, and audio behavior that would otherwise require a full browser + running backend to discover.
- `docker-compose.test.yml` provides a reproducible test environment for CI/CD integration.

---

## Addendum — `tests/helpers/` Package (2026-03-29)

A shared helper package was added at `backend-engine/tests/helpers/` to support the phase-integration and win-condition test suites.

### Modules

| Module | Purpose |
|--------|---------|
| `ws_patterns.py` | `consume_until(ws, predicate)` — drain WS until a predicate matches, tolerating disconnect-noise broadcasts. Assertion helpers: `assert_phase`, `assert_player_dead`, `assert_game_over`, `assert_no_sensitive_role_data`. |
| `role_utils.py` | `collect_role_map(client, game_id, players)` — open each player WS, read their sync, extract role. **Must be called before opening the display WS** to avoid disconnect broadcasts polluting the display buffer. `first_with_role`, `players_with_role`, `get_alive_pids`. |
| `game_driver.py` | `create_and_fill`, `send_player_intent`, `drive_role_deal`, `drive_night`, `drive_to_day_vote`, `drive_votes` — stateless phase-driving helpers used by both integration and e2e test tiers. |

### Key contracts

- **Role discovery**: No REST endpoint exposes assigned roles. Each player's sync message after `start_game` transitions to `ROLE_DEAL` is the only authoritative source. `collect_role_map()` encapsulates this.
- **`state_id` in test intents**: Omit `state_id` from all test intents unless the test specifically validates the fence. Missing field = fence bypassed.
- **Auto-advance is synchronous**: The last required night action triggers `resolve_night()` inline and transitions to `DAY` before broadcasting. There is no intermediate "all submitted but still NIGHT" broadcast.
- **Disconnect-broadcast noise**: Closing a player WS enqueues `player_disconnected`, which causes a broadcast. `consume_until` tolerates this; tests that read exactly one message must account for leftover broadcasts from previous phases.
- **Doctor always in night_acts**: `_build_night_acts()` in both test files auto-fills doctor target (protect seer) when doctor is present, ensuring `actions_required_count` is met and auto-advance fires reliably.
- **Voting pattern**: `_vote_everyone_for(target)` — all alive players vote for target (target votes for someone else). Guarantees strict majority for any `N ≥ 2` alive, avoids self-vote errors.

**Negative:**
- `fakeredis` may not implement every Redis command or edge case identically to the production Redis 7 server. If `redis_store.py` ever uses an obscure command (e.g., scripting, streams), a fakeredis test could pass while the production Redis call fails. Mitigated by keeping `redis_store.py` to basic `GET`/`SET`/`DEL`/`EXPIRE` operations.
- jsdom `getBoundingClientRect` returns `{x:0,y:0,width:0,height:0,top:0,right:0,bottom:0,left:0}` by default. The `VoteWeb` tests must manually create DOM elements and mock `getBoundingClientRect` before testing line-drawing logic.
- Adding `vitest` and `@testing-library/*` as devDependencies increases `npm ci` time for the display frontend. Accepted cost.
- The `FakeWebSocket` class must be updated if `useWebSocket` ever uses WebSocket features beyond `send`, `close`, and the four callback properties.
