# PRD-005: Werewolf — Lobby Game Configuration: Difficulty Level & Phase Timers

## §1. Context & Problem

**REQ-3 — Game Balance (Difficulty Level) Visualization & Control:**
The Display's lobby screen must prominently broadcast the chosen match difficulty to all participants in the room and provide direct configuration controls.

**REQ-4 — Custom Phase Timers Visualization & Control:**
The Display must act as the central visual authority for all game timers. During setup, it must allow configuration of the timers; during active gameplay, it must prominently broadcast countdowns to the room.

**Current state (post-ADR-009):**
- `GameConfig` holds five timer fields and a `roles` composition dict. No `difficulty_level` field exists.
- `create_game` sets all timers from global `Settings` defaults — no per-game overrides are possible.
- `build_composition()` (setup.py:44) uses a hardcoded `targetRange` drawn from `BALANCE_WEIGHT_SYSTEM` — no per-game difficulty influence.
- `NightScreen` and `DayScreen` each inline their own `useTimer` + `MM:SS` formatting — no shared component.
- The lobby screen has no visibility into timer config and no controls for either difficulty or timers.

**Desired end state:**
- Display host selects difficulty (Easy / Balanced / Hard) and adjusts phase timer values from the lobby screen.
- Every change is immediately visible on the Display TV and on every mobile client's next `update` message.
- During gameplay, a shared `<PhaseTimer>` component renders the active countdown consistently across all phases.

---

## §2. Rules Execution

### §2.1 Difficulty Level

Difficulty is a host-facing abstraction over the balance weight composition system (see `setup.py:36–41`). Three named presets are defined. Each preset shifts the `targetBalanceRange` passed to `build_composition()`:

| `difficulty_level` | Display Label | `targetBalanceRange` | Effect on Composition |
|--------------------|---------------|---------------------|-----------------------|
| `easy`             | Easy          | `[0, 4]`            | Biased toward village-protective roles (Doctor, Seer, Tracker…) |
| `standard`         | Balanced      | `[-2, 2]`           | Current default — equal probability of village and wolf power |
| `hard`             | Hard          | `[-4, 0]`           | Biased toward wolf-powered / fewer protective roles |

**Enforcement:** `difficulty_level` is validated at `PATCH /api/games/{id}/config` and rejected if the game has already passed `lobby` phase. At `start_game`, `build_composition()` receives the `targetRange` derived from `difficulty_level` — it does **not** store the raw range in `GameConfig`.

**Broadcast:** `difficulty_level` is a field of `GameConfig` and therefore included in every `sync`/`update` message. No new message type is required.

**Lock-in:** Once `start_game` fires, `difficulty_level` is frozen; subsequent PATCH requests return `409 Game already started`.

---

### §2.2 Phase Timer Configuration

Three phase timers are user-configurable in the lobby. Two internal timers (`role_deal`, `hunter_pending`) are fixed and not exposed.

| Timer Field | Phase | Default | Min | Max | Step |
|-------------|-------|---------|-----|-----|------|
| `night_timer_seconds` | `night` | 60 | 30 | 120 | 15 |
| `day_timer_seconds`   | `day`   | 180 | 60 | 300 | 30 |
| `vote_timer_seconds`  | `day_vote` | 90 | 30 | 120 | 15 |

**Enforcement:** The server validates min/max bounds on each PATCH. Out-of-bounds values return `422`. Partial updates are allowed — omitting a field leaves it unchanged.

**Authority:** Server timers remain authoritative. The `timer_ends_at` ISO-8601 timestamp in state is the single source of truth. The config values (`*_timer_seconds`) define the deadline offset when a phase starts — they do not override a live timer.

---

### §2.3 Visibility by Client Type

| UI Element | Display (host) | Display (spectator — no `hostSecret`) | Mobile (any player) |
|---|---|---|---|
| Difficulty badge | Visible + editable button group | Visible, read-only | Not shown (config in state, no UI surface) |
| Timer values | Visible + stepper controls | Visible, read-only | Not shown |
| Phase countdown | Full-screen `<PhaseTimer>` during game | Full-screen `<PhaseTimer>` during game | Not in scope (mobile displays its own timer separately) |

---

## §3. Payload Schema

### §3.1 Backend: `GameConfig` Model Extension

Add one field to `backend-engine/engine/state/models.py`:

```python
from engine.state.enums import DifficultyLevel  # new enum

class GameConfig(BaseModel):
    # existing fields unchanged
    night_timer_seconds: int = 60
    day_timer_seconds: int = 180
    vote_timer_seconds: int = 90
    role_deal_timer_seconds: int = 30
    hunter_pending_timer_seconds: int = 30
    player_count: int
    roles: dict[str, int]
    # new field
    difficulty_level: DifficultyLevel = DifficultyLevel.STANDARD
```

New enum in `backend-engine/engine/state/enums.py`:

```python
class DifficultyLevel(str, Enum):
    EASY     = "easy"
    STANDARD = "standard"
    HARD     = "hard"
```

`targetBalanceRange` map (used only inside `build_composition()`, not stored):

```python
DIFFICULTY_BALANCE_RANGE: dict[str, list[int]] = {
    "easy":     [0,  4],
    "standard": [-2, 2],
    "hard":     [-4, 0],
}
```

---

### §3.2 REST Endpoint: `PATCH /api/games/{game_id}/config`

**Location:** `backend-engine/api/lobby/routes.py`

**Request body:**

```json
{
  "host_secret": "string (required)",
  "difficulty_level": "easy | standard | hard (optional)",
  "night_timer_seconds": 60,
  "day_timer_seconds": 180,
  "vote_timer_seconds": 90
}
```

All config fields are optional. Omitted fields are unchanged. `host_secret` is always required.

**Validation rules:**
- `host_secret` mismatch → `403 Invalid host secret`
- Phase is not `lobby` → `409 Game already started`
- Timer value out of bounds → `422 Unprocessable Entity` with field detail
- Unknown `difficulty_level` → `422`

**Response on success:**

```json
{ "ok": true }
```

**Side effects:**
1. `G.config` is updated for the changed fields only.
2. `await manager.broadcast(game_id, G)` — sends `update` to all sockets with the new config in state.

---

### §3.3 Frontend: Type Changes

**`frontend-display/src/types/game.ts`** — extend `GameConfig`:

```typescript
export type DifficultyLevel = 'easy' | 'standard' | 'hard'

export interface GameConfig {
  night_timer_seconds: number
  day_timer_seconds: number
  vote_timer_seconds: number
  role_deal_timer_seconds: number
  hunter_pending_timer_seconds: number
  player_count: number
  roles: Record<string, number>
  difficulty_level: DifficultyLevel          // new
}
```

**`backend-engine/api/schemas/shared_types.ts`** — mirror the same change.

---

## §4. Client-Server Specification

### §4.1 Display Client — `<LobbyConfigPanel>` Component

**Location:** `frontend-display/src/components/LobbyConfigPanel/LobbyConfigPanel.tsx`

**Props:**

```typescript
interface Props {
  config: GameConfig
  hostSecret?: string
  gameId?: string
}
```

**Render — host view (`hostSecret` present):**

```
┌──────────────────────────────────────────┐
│  DIFFICULTY                              │
│  [ Easy ]  [ Balanced ]  [ Hard ]        │  ← 3-button toggle; active button highlighted
│                                          │
│  PHASE TIMERS                            │
│  Night      [−] 60s  [+]                 │
│  Day        [−] 3:00 [+]                 │
│  Vote       [−] 1:30 [+]                 │
└──────────────────────────────────────────┘
```

Each `[−]` / `[+]` click fires `PATCH /api/games/{gameId}/config` with the single changed field. All buttons are disabled during an in-flight request.

**Render — spectator view (no `hostSecret`):**

```
┌──────────────────────────────────────────┐
│  BALANCED  ·  Night 60s  ·  Day 3:00  ·  Vote 1:30
└──────────────────────────────────────────┘
```

Single read-only row: difficulty label + formatted timer values.

**Timer display format:** `≥ 60s` → `M:SS`, `< 60s` → `Xs`.

**Integration in `LobbyScreen.tsx`:** `<LobbyConfigPanel>` is placed between the avatar parade and the start button area.

---

### §4.2 Display Client — `<PhaseTimer>` Shared Component

**Location:** `frontend-display/src/components/PhaseTimer/PhaseTimer.tsx`

**Purpose:** Extract the `useTimer` call + `MM:SS` format + warning/critical class application that is currently duplicated inside `NightScreen.tsx` and `DayScreen.tsx`.

**Props:**

```typescript
interface Props {
  timerEndsAt: string | null
  className?: string
}
```

**Render:**

```tsx
export default function PhaseTimer({ timerEndsAt, className }: Props) {
  const { secondsRemaining, isWarning, isCritical } = useTimer(timerEndsAt)
  const minutes = Math.floor(secondsRemaining / 60)
  const secs = secondsRemaining % 60
  const formatted = `${minutes}:${String(secs).padStart(2, '0')}`
  const stateClass = isCritical ? 'timer--critical' : isWarning ? 'timer--warning' : ''
  return (
    <span className={['phase-timer', stateClass, className].filter(Boolean).join(' ')}>
      {formatted}
    </span>
  )
}
```

**CSS token usage (PRD-003 §2):**
- Default size: `font-size: clamp(2rem, 5.6vmin, 4rem)` (PRD-003 "timer-secondary")
- `timer--warning`: color → `var(--timer-warning)` (`#f6c90e`)
- `timer--critical`: color → `var(--timer-critical)` (`#e53e3e`)

**Migration:** Replace inline `useTimer` + format logic in `NightScreen.tsx:20–21` and `DayScreen.tsx:14–18` with `<PhaseTimer timerEndsAt={gameState.timer_ends_at} />`.

---

### §4.3 `<LobbyScreen>` Integration

The `LobbyScreen` receives `gameState` (which includes `gameState.config`) and passes it down:

```tsx
<LobbyConfigPanel
  config={gameState.config}
  hostSecret={hostSecret}
  gameId={gameId}
/>
```

No new state or store fields are needed — `gameState.config` is updated by every incoming `update` message.

---

## §5. Phase-Gate Plan

| Phase | Deliverable |
|-------|-------------|
| 1. Backend model | Add `difficulty_level` to `GameConfig`; add `DifficultyLevel` enum; update `build_composition()` to accept `target_range` parameter derived from `difficulty_level` |
| 2. Backend endpoint | `PATCH /api/games/{id}/config` with validation and broadcast |
| 3. Backend tests | Unit: `difficulty_level` → correct `target_range`; Integration: PATCH auth, bounds, lobby-phase gate |
| 4. Frontend types | `DifficultyLevel`, `GameConfig.difficulty_level` in `types/game.ts` and `shared_types.ts` |
| 5. `<PhaseTimer>` | New shared component; replace inline timer code in `NightScreen` + `DayScreen` |
| 6. `<LobbyConfigPanel>` | Host + spectator views; PATCH calls; read from `gameState.config` |
| 7. `<LobbyScreen>` wiring | Embed `<LobbyConfigPanel>` |
| 8. Frontend tests | `<PhaseTimer>` formatting + CSS class; `<LobbyConfigPanel>` host/spectator views, PATCH calls, in-flight disable |

---

## §6. User Stories

| As a | I want to | So that |
|------|-----------|---------|
| Display Client | show the current difficulty level prominently in the lobby | all participants in the room know the chosen challenge level before the game starts |
| Display Client | show all three timer values in the lobby at all times | players can set expectations for round pacing |
| Display Client (host) | select Easy / Balanced / Hard difficulty via a button toggle | the role composition is biased toward or against the village without needing to understand balance weights |
| Display Client (host) | increment or decrement each phase timer in 15–30s steps | I can tune round pacing to match the group's energy |
| Display Client (host) | see all config controls disabled while a PATCH request is in flight | I don't accidentally submit a double-change |
| Display Client (spectator) | see config values in a read-only summary row | I'm informed without having controls I can't use |
| Display Client | show a prominent `<PhaseTimer>` countdown during Night, Day, and Vote phases | the entire room stays synchronized on time pressure |
| Game Server | reject config changes after the lobby phase | the difficulty and timers that were set at start are the ones used |

---

## §7. Open Questions

| # | Question | Owner | Status |
|---|----------|-------|--------|
| 1 | Should `role_deal_timer_seconds` (30s) and `hunter_pending_timer_seconds` (30s) be exposed to users? The current 30s default covers all reasonable group sizes. | Game design | Deferred — expose only night/day/vote for now |
| 2 | Should changing difficulty in the lobby automatically reset custom timer values to difficulty-appropriate defaults (e.g., Hard → shorter day timer)? | Game design | Open — current spec keeps them independent |
| 3 | Should the Mobile client display a difficulty badge on the waiting screen? | UX | Deferred — mobile client scope is separate |
| 4 | Should `<PhaseTimer>` support a `phaseName` prop (e.g., "NIGHT PHASE — 0:45") for full-screen presentation, or keep it to the number only? | Display UX | Open — number-only is safe default |
