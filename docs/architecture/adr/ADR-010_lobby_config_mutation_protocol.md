# ADR-010: Werewolf — Lobby Config Mutation Protocol (Difficulty & Timers)

## Status

Accepted

## Date

2026-03-27

## Context

PRD-005 §1 identifies four gaps:

1. **No difficulty concept.** `build_composition()` in `setup.py:63` reads `targetRange` from the static `BALANCE_WEIGHT_SYSTEM` constant — it is not tunable per game. The Display host has no control over role balance.

2. **No per-game timer overrides.** `create_game` (lobby/routes.py:49–72) copies timers from global `Settings` at game creation. Once the game exists, there is no endpoint to change them. All games have identical timers.

3. **No config broadcast path.** Even if the server could mutate config, there is no mechanism to push the change to connected clients immediately.

4. **No shared timer component.** `NightScreen.tsx` and `DayScreen.tsx` each duplicate `useTimer` call, `MM:SS` format, and warning/critical class logic. A third phase (HunterPending) will need the same pattern.

**Related prior decisions:**
- ADR-001 §3: Server owns all timers — `timer_ends_at` is an absolute server-issued timestamp. This ADR concerns configuring the *duration* before that timestamp is issued, not overriding a live timestamp.
- ADR-009: `match_data` introduced a dedicated message type for lobby roster events. This ADR evaluates whether config changes need the same treatment.
- Existing lobby REST pattern: `POST /join`, `POST /rejoin`, `POST /start` — REST for lobby mutations, not WS intents.

---

## Decision

### 1. Difficulty as a Named Enum — Not a Raw Balance Range

**Decision:** `difficulty_level: DifficultyLevel` is added to `GameConfig` as a named enum (`easy | standard | hard`). The `targetBalanceRange` is **computed** server-side from this enum when `build_composition()` runs at game start. It is never stored in state and never sent to clients.

**Why not expose `targetBalanceRange` directly:**
- The balance weight system is an internal balancing mechanism, not a product concept. Exposing `[-4, 0]` to the display host is meaningless without knowing each role's weight.
- The named enum is the right UX surface. The server owns the mapping.
- Future difficulty tuning (e.g., adding an `expert` level) is a one-line change to the mapping, not a UI change.

**Mapping (not stored in state, only used in `build_composition()`):**

```python
DIFFICULTY_BALANCE_RANGE: dict[str, list[int]] = {
    "easy":     [0,  4],   # village-protective role bias
    "standard": [-2, 2],   # default (current behavior)
    "hard":     [-4, 0],   # wolf-power bias
}
```

`build_composition()` gains a `target_range` parameter:

```python
def build_composition(
    player_count: int,
    seed: str | None = None,
    target_range: list[int] | None = None,
) -> dict[str, int]:
    ...
    effective_range = target_range or BALANCE_WEIGHT_SYSTEM.get("targetRange", [-2, 2])
```

At `start_game`, the intent handler derives the range:

```python
from engine.setup import DIFFICULTY_BALANCE_RANGE
target_range = DIFFICULTY_BALANCE_RANGE[G.config.difficulty_level]
composition = build_composition(G.config.player_count, G.seed, target_range=target_range)
```

---

### 2. Config Mutation via REST `PATCH` — Not a WS Intent

**Decision:** A new `PATCH /api/games/{game_id}/config` endpoint handles config mutations. WS intents are not used for this.

**Why REST, not WS intent:**
- All other lobby mutations (`join`, `rejoin`, `start`) are REST. Consistency is a strong argument.
- WS intents require an authenticated socket connection. The Display host may want to adjust config before opening a WS connection (e.g., immediately after creating the game).
- PATCH naturally expresses partial updates. WS intents would require a `config_update` intent type with complex optional field handling.
- Error surfaces are cleaner: HTTP 403/409/422 vs WS error messages.

**Auth:** `host_secret` is required in the request body, mirroring `POST /start`:

```python
class ConfigUpdateRequest(BaseModel):
    host_secret: str
    difficulty_level: DifficultyLevel | None = None
    night_timer_seconds: int | None = None
    day_timer_seconds: int | None = None
    vote_timer_seconds: int | None = None
```

**Validation:**
- Phase gate: `G.phase != Phase.LOBBY` → `409`
- `host_secret` mismatch → `403`
- Timer out of range (see PRD-005 §2.2) → `422`
- Unknown `difficulty_level` (handled by Pydantic) → `422`

**Partial update:** Only supplied fields are changed. `G = G.model_copy(deep=True)` ensures immutability.

**Broadcast:** After a successful config mutation, `await manager.broadcast(game_id, G)` is called — the existing full-state `update` broadcast. No new message type is introduced.

---

### 3. No New Message Type for Config Changes — Reuse `update`

**Decision:** Config changes do not get a dedicated `config_update` WS message. The existing `update` message carries `state.config` on every broadcast.

**Why no dedicated message type (contrast with ADR-009 `match_data`):**

| | `match_data` (ADR-009) | config change |
|---|---|---|
| Content security | Safe — no secret fields | Same — `GameConfig` has no secret fields |
| Broadcast timing | Immediate on join/rejoin, before full state | Same — broadcast runs immediately after PATCH |
| Decoupling motivation | Roster arrives before first `update`; needs separate channel | Config change always co-occurs with an `update` broadcast |
| Frequency | Every player join (can be rapid) | User-driven, infrequent, ~1–10 changes per lobby |
| Client store motivation | Roster needed before `sync` (ADR-009 §5) | Config is always inside `sync`/`update`; no pre-seeding problem |

The `match_data` message type was justified by timing: roster events arrive *alongside* `update` and need to be handled distinctly. Config changes *are* the `update`. There is no gap to bridge.

**Frontend read path:** `LobbyConfigPanel` reads `props.config` which is `gameState.config` — updated by the existing `useGameState` handler on every `update` message. No Zustand store extension is needed for config.

---

### 4. `<PhaseTimer>` as a Shared Component — Not Inline

**Decision:** Extract timer display into a shared `<PhaseTimer>` component in `frontend-display/src/components/PhaseTimer/`.

**Why extract now:**
- Duplication already exists: `NightScreen.tsx:20–21` and `DayScreen.tsx:14–18` contain identical `useTimer` + format + CSS-class logic.
- `HunterPendingScreen` (future) will need the same.
- `LobbyConfigPanel` needs formatted timer values for its read-only spectator row. Rather than inline formatting again, `PhaseTimer`'s format function should be exported as a pure utility.
- PRD-003 §2 defines specific `clamp()` / `vmin` values for the timer. Centralizing the component makes PRD-003 compliance a single-site concern.

**Why not a custom hook:** `useTimer` is already the hook. `<PhaseTimer>` is the render layer — it owns CSS class application and text formatting. A component is the correct boundary.

**Migration scope:** `NightScreen.tsx` and `DayScreen.tsx` are modified to remove their inline timer logic and use `<PhaseTimer>`. No behavior change — only structure.

---

### 5. `<LobbyConfigPanel>` Controls — PATCH per Interaction, No Optimistic Update

**Decision:** Each stepper `[+]` / `[−]` click and each difficulty button click sends a `PATCH` immediately. All controls are disabled during an in-flight request. No optimistic local state update.

**Why not optimistic:**
- The lobby is a non-time-sensitive flow. 100–200ms round-trip is imperceptible.
- Optimistic update would require reconciling with the server's broadcast `update` message — this creates a state-conflict window when two hosts interact simultaneously (unlikely but possible if two displays connect with the same `host_secret`).
- Server is the single source of truth (ADR-001 §2). Optimistic UI contradicts this for a non-latency-critical interaction.

**Disable-during-flight:** A single `isPatching` boolean state in `LobbyConfigPanel` gates all interactive elements during any in-flight PATCH. This prevents double-submission and stacked partial updates.

---

## Consequences

### Backend

| File | Change |
|------|--------|
| `engine/state/enums.py` | Add `DifficultyLevel` enum (`easy`, `standard`, `hard`) |
| `engine/state/models.py` | Add `difficulty_level: DifficultyLevel = DifficultyLevel.STANDARD` to `GameConfig` |
| `engine/setup.py` | `build_composition()` gains optional `target_range` param; add `DIFFICULTY_BALANCE_RANGE` constant; `start_game` intent handler derives range from `difficulty_level` |
| `api/lobby/routes.py` | New `PATCH /{game_id}/config` endpoint with `ConfigUpdateRequest` body and `manager.broadcast()` side effect |
| `api/schemas/shared_types.ts` | Add `DifficultyLevel` type; add `difficulty_level` to `GameConfig` interface |

### Frontend

| File | Change |
|------|--------|
| `src/types/game.ts` | Add `DifficultyLevel` type; add `difficulty_level: DifficultyLevel` to `GameConfig` |
| `src/components/PhaseTimer/PhaseTimer.tsx` | New shared component (+ `PhaseTimer.css`) |
| `src/components/NightScreen/NightScreen.tsx` | Replace inline timer with `<PhaseTimer>` |
| `src/components/DayScreen/DayScreen.tsx` | Replace inline timer with `<PhaseTimer>` |
| `src/components/LobbyConfigPanel/LobbyConfigPanel.tsx` | New component (+ `LobbyConfigPanel.css`) |
| `src/components/LobbyScreen/LobbyScreen.tsx` | Embed `<LobbyConfigPanel config={gameState.config} hostSecret={hostSecret} gameId={gameId} />` |

### Tests — New Assertions Required

| File | Change |
|------|--------|
| `tests/unit/test_setup.py` | New: `build_composition` respects `target_range` param; `easy` produces higher village weight than `hard` |
| `tests/api/test_lobby_config.py` | New file: PATCH auth failure, phase gate, bounds validation, successful partial update, broadcast after change |
| `frontend-display/src/test/components/PhaseTimer.test.tsx` | New: MM:SS format, warning class at ≤30s, critical class at ≤10s |
| `frontend-display/src/test/components/LobbyConfigPanel.test.tsx` | New: host view shows controls; spectator view is read-only; PATCH fired on difficulty change; PATCH fired on timer step; controls disabled during flight |
| `frontend-display/src/test/components/LobbyScreen.test.tsx` | Update: `<LobbyConfigPanel>` rendered inside lobby |
| `frontend-display/src/test/components/NightScreen.test.tsx` | Update: timer rendered via `<PhaseTimer>` (no behavior change, structural assertion update only) |
| `frontend-display/src/test/components/DayScreen.test.tsx` | Update: same as NightScreen |

### Positive

- Host can tune game difficulty and pacing without touching code or restarting the server.
- `difficulty_level` is a stable, broadcast field — any future client (mobile spectator view, analytics) can read it from state without extra protocol work.
- `<PhaseTimer>` eliminates 20+ lines of duplication and makes PRD-003 timer styling a single point of change.
- No new WS message type → no FakeWebSocket changes, no `ServerMessage` union extension, no handler registration.

### Negative

- Each stepper click issues a PATCH. For rapid-fire increments (user holds `+`), this fires multiple sequential requests. Mitigated by disabling controls during flight.
- `build_composition()` now has an optional parameter that slightly complicates its signature. Existing callers pass nothing (defaults to standard range) — no breakage.
- `difficulty_level` in `GameConfig` is a new required field in serialized state. Existing saved games in Redis that predate this ADR will deserialize without it; Pydantic's default (`standard`) handles the migration silently.
