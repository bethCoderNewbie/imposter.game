# ADR-006: Werewolf — Integration & E2E Test Tiers and GitHub Actions CI/CD

## Status
Accepted

## Date
2026-03-27

## Context

After ADR-005 established unit-level test coverage (265 tests: engine logic, Redis store, frontend hooks and components), three gaps remained:

1. **No HTTP integration tests.** The lobby REST endpoints (`POST /games`, `POST /games/{id}/join`, `POST /games/{id}/start`, `POST /games/{id}/rejoin`) were never exercised as a full HTTP stack. Bugs at the routing, dependency-injection, or serialization layer would only surface in a running server.

2. **No WebSocket integration tests.** The WebSocket endpoint's auth flow (session-token validation, display sentinel bypass, initial state unicast) was only tested by connecting a real browser. The `player_id="display"` sentinel, the `AUTH_FAILED` error path, and the live-join broadcast were untested.

3. **No automated CI/CD pipeline.** Tests ran locally only. There was no gate on pull requests, no automated coverage reporting, and no reproducible test execution on every commit.

---

## Decision

### 1. Three-Tier Test Architecture

Tests are separated into three tiers using pytest markers. Tiers must not bleed upward: a unit test must not require Redis, and an integration test must not require a running server port.

```
Tier 1 — unit       @pytest.mark.unit (implicit, no marker needed)
Tier 2 — integration  @pytest.mark.integration
Tier 3 — e2e          @pytest.mark.e2e
```

| Tier | What it tests | External dependency | Speed |
|------|---------------|---------------------|-------|
| Unit | Pure functions, Redis semantics (fakeredis) | None | < 2s |
| Integration | Full HTTP + WS stack via TestClient | None (fakeredis) | < 5s |
| E2E | Lobby → start → phase transition via real stack | Real Redis | < 10s |

### 2. Integration Tests: `starlette.TestClient` + Injected `FakeRedis`

**Chosen:** Starlette `TestClient` (synchronous) with `fakeredis.aioredis.FakeRedis(decode_responses=True)` injected by patching `redis.asyncio.from_url` before the lifespan runs.

**Rejected:** `httpx.AsyncClient` with `ASGITransport` (requires async test functions throughout, more complex fixture scoping); spinning up a real server process per test (too slow, requires port management).

**Injection pattern:**

```python
@pytest.fixture
def client(fake_redis, monkeypatch):
    monkeypatch.setattr(redis.asyncio, "from_url", lambda *a, **kw: fake_redis)
    from api.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
```

The monkeypatch intercepts the lifespan's `aioredis.from_url(settings.redis_url, ...)` call and returns the per-test `FakeRedis` instance instead. The lifespan teardown (`await app.state.redis.aclose()`) works because `FakeRedis` implements `aclose()`.

**Singleton reset:** `game_queue._queues` and `ConnectionManager._rooms` are module-level singletons. An `autouse` fixture in `tests/api/conftest.py` clears both before and after every test to prevent cross-test leakage.

```python
@pytest.fixture(autouse=True)
def reset_singletons():
    from api import game_queue
    from api.connection_manager import manager
    for q in list(game_queue._queues.values()):
        q.stop()
    game_queue._queues.clear()
    manager._rooms.clear()
    yield
    for q in list(game_queue._queues.values()):
        q.stop()
    game_queue._queues.clear()
    manager._rooms.clear()
```

**WebSocket testing:** `TestClient.websocket_connect(url)` opens a synchronous WebSocket session backed by anyio. Multiple connections within a single test work because the ASGI app runs in a background thread with its own event loop.

The `game_queue` background task (`asyncio.create_task`) runs inside the TestClient's event loop. After `POST /api/games/{id}/start`, the intent processes and broadcasts to any connected WebSocket within the same request cycle — `ws.receive_json()` blocks until the broadcast arrives.

### 3. E2E Tests: Real Redis, Auto-Skip When Unavailable

**Chosen:** A module-scoped `require_redis` fixture that pings the configured Redis URL and calls `pytest.skip()` if unreachable. The `e2e_client` fixture creates a `TestClient` against a fresh `create_app()` that connects to real Redis.

**Rejected:** Always requiring Redis for E2E (breaks developer workflow without local Redis); mocking Redis for E2E (defeats the purpose — the goal is to verify Redis round-trips actually work).

**Skip mechanism:**

```python
@pytest.fixture(scope="module", autouse=True)
def require_redis():
    url = os.getenv("REDIS_URL", "redis://localhost:6379/15")
    if not _redis_available(url):
        pytest.skip(f"Redis not available at {url} — skipping E2E tests")
```

Running `pytest` without `REDIS_URL` is always safe — E2E tests self-skip rather than fail. CI sets `REDIS_URL=redis://localhost:6379/15` via a GitHub Actions service container.

**Settings cache:** `get_settings()` uses `lru_cache`. The E2E `conftest.py` calls `get_settings.cache_clear()` before creating the app so the `REDIS_URL` env var is re-read from the environment rather than a cached default.

**What E2E tests verify:**
- Full lobby flow (create → join 5 players → start) via REST
- Display WS receives initial lobby state immediately on connect
- Joining a player via REST while a display WS is open triggers a live broadcast
- Player WS receives initial state after authenticating with a valid session token
- `POST /api/games/{id}/start` triggers game queue processing and results in a `ROLE_DEAL` state update broadcast to the display WS
- Display view never exposes `host_secret` or player roles during `ROLE_DEAL`
- Player's own WS view exposes their own role during `ROLE_DEAL`
- **Full village-wins flow** (ROLE_DEAL → NIGHT → DAY → DAY_VOTE → `game_over winner=village`)
- **Full werewolf-wins flow** (2-round engineered WW majority)
- `elimination_log[*].role` populated at `game_over` (roles revealed via log, not `players` dict)
- Both display and player WS receive the `game_over` broadcast
- No post-game-over broadcasts sent (game queue stopped)

### 4. GitHub Actions CI/CD Pipeline

**Chosen:** A single `.github/workflows/ci.yml` file with five parallel jobs, triggered on every `push` and `pull_request`.

**Rejected:** A single monolithic job (one Redis failure blocks frontend tests); external CI services (GitHub Actions is already available with no additional account required).

**Jobs:**

```yaml
backend-unit:
  # pytest -m "not integration and not e2e" --cov=backend-engine
  # No services required. Uploads coverage to Codecov.

backend-integration:
  # pytest -m "integration" --timeout=30
  # No services required (fakeredis is in-process).
  # Covers: HTTP lobby, WS auth, ROLE_DEAL→NIGHT→DAY→DAY_VOTE→HUNTER_PENDING→GAME_OVER,
  #         security stripping, state_id fence, multi-round loop (~66 tests total).

backend-e2e:
  services:
    redis: {image: redis:7-alpine, health-cmd: "redis-cli ping"}
  # pytest -m "e2e" --timeout=60
  # REDIS_URL=redis://localhost:6379/15
  # Covers: full village-wins, full werewolf-wins, game_over broadcast, elimination_log roles.

frontend-display:
  # npm ci && npm run test -- --run --reporter=verbose

frontend-mobile:
  # npm ci && npm run build  (TypeScript build check)
```

**`fail-fast: false`** is implicit (default for parallel jobs): a failing backend job does not cancel frontend jobs.

**Coverage:** `backend-unit` uploads `coverage.xml` to Codecov using `codecov/codecov-action@v4`. The `CODECOV_TOKEN` secret is optional — upload failures do not break the build.

---

## Consequences

**Positive:**
- ~315 backend tests (154 unit + 38 prior integration + **28 new phase-integration** + 11 prior e2e + **7 new win-condition e2e**) run in < 15s on developer hardware (e2e auto-skip without Redis).
- Every pull request is gated by all five CI jobs before merge.
- Integration tests verify the HTTP/WS layer including auth, error codes, broadcast ordering, and state stripping — without requiring a running server or browser.
- E2E tests verify the full Redis round-trip and the `game_queue` processing pipeline, catching bugs that only appear when fakeredis semantics diverge from production Redis.
- E2E tests self-skip when Redis is unavailable, keeping the feedback loop fast for developers who just want to run unit + integration tests.

**Negative:**
- `starlette.TestClient` runs the ASGI app in a background thread. The `asyncio.create_task` calls inside endpoints run in the background event loop, which is transparent in tests but may create subtle race conditions if a test closes the `TestClient` context before a queued task completes. Mitigated by the `reset_singletons` fixture calling `q.stop()` on teardown.
- The E2E tests use database index `/15` by convention. If a developer runs other Redis-using services on `/15`, test data will be mixed. Mitigated by only writing to namespaced keys (`wolf:game:*`, `wolf:token:*`).
- Adding `httpx>=0.27.0` to test dependencies is required for `starlette.testclient.TestClient`. This is a transitive requirement of FastAPI already present in many environments.
- The `frontend-mobile` CI job only performs a TypeScript build check, not a Vitest suite, because no frontend-mobile test suite exists yet. This job should be upgraded to `npm run test -- --run` when mobile tests are added.
