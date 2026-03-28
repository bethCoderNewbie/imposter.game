---
date: 2026-03-27
topic: night-phase-puzzle-arch
title: "Night Phase Concurrency & Villager Puzzle Randomization — Research & Gap Analysis"
areas:
  - backend-engine/engine/phases/machine.py
  - backend-engine/engine/puzzle_bank.py
  - backend-engine/api/intents/handlers.py
  - backend-engine/api/timer_tasks.py
---

# Night Phase & Puzzle Architecture — Research & Gap Analysis

## 0. ADR-007 Scope Boundary

Both proposed changes (WakeOrder refactor, puzzle randomization) are **engine-layer concerns**. ADR-007 is strictly scoped to the WebSocket message type protocol (`state_update → sync/update`, display handshake). These changes have zero intersection with WS message types or the connection protocol. **ADR-007 must not be amended to cover engine changes.** A separate ADR (ADR-008) is proposed below for the puzzle randomization decision.

---

## 1. Change 1: Concurrent Night Phase (WakeOrder Refactor)

### 1.1 Premise Under Investigation

> "The current WakeOrder logic appears to handle night actions sequentially (one by one), creating bottlenecks or dead time for players."

### 1.2 Verified Architecture

**`engine/phases/machine.py` — `compute_actions_required()` (lines 36–59):**

```python
def compute_actions_required(G: MasterGameState) -> int:
    for pid, player in G.players.items():
        ...
        wake_order = role_def.get("wakeOrder", 0)
        if wake_order == 0:
            continue          # Villagers excluded — never block auto-advance
        ...
        count += 1
    return count
```

`wakeOrder` is used exclusively as a **binary inclusion flag**, not a sequencing mechanism:
- `wakeOrder == 0` → excluded from action count (Villager, no night action)
- `wakeOrder != 0` → included in action count (active role: wolf, seer, doctor, etc.)

The integer value of `wakeOrder` beyond 0 vs. non-0 is never read, compared, or used to order execution anywhere in the codebase. There is no "wake wolf first, then seer" logic.

**`engine/phases/machine.py` — `should_auto_advance()` (lines 124–127):**
```python
if G.phase == Phase.NIGHT:
    required = G.night_actions.actions_required_count
    submitted = G.night_actions.actions_submitted_count
    return required > 0 and submitted >= required
```

Auto-advance fires when `submitted >= required` — all active-role players have submitted, regardless of order or timing.

**`api/intents/handlers.py` — `handle_submit_night_action()` (lines 237–248):**

Each player's intent arrives via the game queue (`api/game_queue.py`) and is processed atomically in sequence. This is correct — concurrent state mutation requires serialization. The queue ensures atomicity, not sequencing of player wakeups. Players can and do submit their night actions at any time within the night timer window, in any order. All submissions are accepted and the auto-advance check fires after each one.

**Timer path (`api/timer_tasks.py`):**
- A single asyncio task sleeps until `timer_ends_at`
- On fire: enqueues `{ "type": "phase_timeout" }` → `handle_phase_timeout()` → calls `resolve_night()` and transitions to DAY regardless of submission count
- The timer is cancelled early if `should_auto_advance()` returns true after any submission

### 1.3 Finding

**The night phase is already fully concurrent.** All players (regardless of role) wake simultaneously at the start of night and can submit their actions at any point within the shared timer window. There is no sequential wake ordering, no per-role waiting, and no blocking of one player on another. Villagers run their Archive puzzle concurrently with active-role players completing their actions.

The `wakeOrder` field name is potentially misleading — it originated from classic Werewolf game rules where the Moderator wakes players in sequence. In this implementation, the field is repurposed as a boolean role classifier only.

### 1.4 Action Required

**None.** No code change is needed for Change 1. The architecture already satisfies the stated requirement.

**Optional documentation improvement:** The field name `wakeOrder` could be renamed to `hasNightAction` (bool) in `roles.json` and `WAKE_ORDER` dict to better reflect its actual usage. This is a cosmetic refactor — `WAKE_ORDER[role_id] != 0` → `HAS_NIGHT_ACTION[role_id]` — with no behavioral change. If pursued, it affects `engine/roles_loader.py`, `engine/phases/machine.py`, and `docs/architecture/data_dictionary.md` only.

---

## 2. Change 2: Villager Task Randomization

### 2.1 Premise Under Investigation

> "The puzzle assigned to the Villager role during their task phase is static or predictable."

### 2.2 Verified Architecture

**`engine/puzzle_bank.py` — `generate_night_puzzle()` (lines 37–54):**

```python
def generate_night_puzzle(G: "MasterGameState") -> "PuzzleState":
    rng = random.Random(f"{G.seed}:{G.round}:puzzle")
    puzzle_type = rng.choices(["logic", "math", "sequence"], weights=[50, 25, 25], k=1)[0]
    ...
```

The RNG is seeded with `f"{G.seed}:{G.round}:puzzle"`:
- `G.seed` — a fixed random token assigned at game creation, unique per game session
- `G.round` — increments by 1 each time the night phase is entered

**Effective puzzle variation:**

| Scenario | Same puzzle? |
|----------|-------------|
| Same player, same game, same round | Yes — deterministic |
| Same player, same game, different round | No — round number changes RNG seed |
| Different game (new session) | No — G.seed is a new random token |
| Two players in same game, same round | **Yes — all wakeOrder==0 players share one PuzzleState** |

**The shared puzzle_state discovery:**

`engine/phases/machine.py:92–94`:
```python
# Generate Archive puzzle for wakeOrder==0 players (logic/math/sequence)
from engine.puzzle_bank import generate_night_puzzle
G.night_actions.puzzle_state = generate_night_puzzle(G)
```

One `puzzle_state` is generated per round and stored in `NightActions`. Every player with `wakeOrder == 0` receives the same puzzle via the state stripper. If a game has 4 Villagers, all 4 see identical questions.

**Module docstring (puzzle_bank.py:3):**
> "All generation is deterministic given the game seed — no I/O after module load."

The seeded approach is intentional: it was designed for reproducibility (same seed + round = same puzzle, useful for debugging, testing, and state replay).

### 2.3 Gap Analysis

Two distinct interpretations of "static or predictable":

| Interpretation | Current State | Gap? |
|---------------|--------------|------|
| Same puzzle every round within one game | False — round number changes it | No gap |
| Same puzzle in the same game can be precomputed if seed is known | True — deterministic | Minor (seed is server-side only) |
| All villagers in the same game+round get identical puzzles | **True** | **Yes — real gap** |

The meaningful gap is the third row: **all Villagers in a round share one puzzle**. In a group where Villager players can see each other's screens or compare answers, the puzzle provides no differentiating information. Additionally, the puzzle pool for logic questions is finite (400 entries) — across many sessions, repeats are probable for frequent players.

### 2.4 Two Possible Resolutions

**Option A — Per-player puzzle generation (architectural change):**

Generate a unique `PuzzleState` per Villager player rather than one shared puzzle per round. Store puzzle state on `PlayerState` instead of `NightActions.puzzle_state`.

- Change to `machine.py`: call `generate_night_puzzle(G, player_id)` for each wakeOrder==0 player during NIGHT transition; set result on `player.puzzle_state`
- Change to `puzzle_bank.py`: add `player_id` to the RNG seed: `random.Random(f"{G.seed}:{G.round}:{player_id}:puzzle")`
- Change to stripper: read `player.puzzle_state` instead of `G.night_actions.puzzle_state`
- Change to `handlers.py` (`handle_submit_puzzle_answer`): validate against `player.puzzle_state`

This preserves determinism (reproducible per player per round) while ensuring each player sees a different puzzle. Tests remain deterministic.

**Option B — True randomization (remove seed):**

Replace `random.Random(f"{G.seed}:{G.round}:puzzle")` with `random.Random()` (unseeded, OS entropy). Puzzles become non-deterministic — different every call even with the same game state.

- Simple one-line change to `puzzle_bank.py:43`
- **Breaks test determinism**: any test asserting a specific puzzle type or content for a known seed will fail. Test fixtures in `tests/` that rely on seeded puzzle output must be updated to not assert on puzzle content.
- Loses replay reproducibility: a game state snapshot can no longer be used to reconstruct what puzzle a player was shown.

### 2.5 Recommendation

**Option A is preferred.** It fixes the real gap (identical puzzles for co-located Villagers), preserves all determinism guarantees, and keeps tests stable. The RNG seed `f"{G.seed}:{G.round}:{player_id}:puzzle"` ensures each player gets a reproducible but distinct puzzle.

Option B discards reproducibility for no additional benefit over Option A — any game that needs debugging loses the ability to reconstruct exact puzzle assignments.

**This change requires a new ADR** (ADR-008) because it alters a load-bearing architectural property (seeded determinism) and moves `puzzle_state` from `NightActions` to `PlayerState`, affecting the state model, the stripper, and the test surface.

> **Status (2026-03-27): Option A implemented.** ADR-008 accepted. All 7 files updated; 203/203 tests pass. `puzzle_state` now lives on `PlayerState`; `NightActions.puzzle_state` removed.

---

## 3. ADR Compliance Matrix

| Change | Violates ADR-007? | Violates other ADR? | Action |
|--------|------------------|---------------------|--------|
| WakeOrder concurrency refactor | No | No — architecture already concurrent | No code change needed |
| Puzzle randomization (Option A) | No | No — ADR-003 §8 governs delay, not puzzle content | New ADR-008 required |
| Puzzle randomization (Option B) | No | No — but breaks test determinism per ADR-005 | New ADR-008 required; test fixtures must be updated |

---

## 4. File Impact (if Change 2 / Option A proceeds)

| File | Change |
|------|--------|
| `engine/puzzle_bank.py` | Add `player_id` param to `generate_night_puzzle()`; update RNG seed |
| `engine/phases/machine.py` | NIGHT transition: loop wakeOrder==0 players, set per-player puzzle |
| `engine/state/models.py` | Add `puzzle_state: PuzzleState \| None` field to `PlayerState` |
| `engine/stripper.py` | Read `player.puzzle_state` instead of `G.night_actions.puzzle_state` |
| `api/intents/handlers.py` | `handle_submit_puzzle_answer`: validate `player.puzzle_state` |
| `tests/` | Update any test fixture asserting on shared `night_actions.puzzle_state` |
| `docs/architecture/data_dictionary.md` | Update `puzzle_state` field location and ownership |
