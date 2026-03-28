# ADR-008: Werewolf — Per-Player Night Puzzle Generation

## Status
Accepted

## Date
2026-03-27

## Context

The Villager Archive puzzle system (introduced alongside the night phase engine) generates one `PuzzleState` per round and stores it on `NightActions.puzzle_state`. Every player with `wakeOrder == 0` (Villager-class roles) receives the identical puzzle via the state stripper.

A research pass (`docs/shared/research/2026-03-27_night-phase-puzzle-arch.md`) confirmed:

1. **All Villagers in the same game and round see the same puzzle.** In a physical play session where multiple Villager players are seated near each other, they can compare screens and confirm they share a puzzle — leaking alignment information and defeating the puzzle's purpose as a solo cognitive decoy.

2. **The current generation is seeded by `f"{G.seed}:{G.round}:puzzle"`**, making puzzles deterministic and reproducible per (game, round) pair. This is intentional (ADR-005 test infrastructure relies on seed-deterministic outputs; the module docstring explicitly states this as a design property).

3. **The same research pass evaluated two resolution options:**
   - **Option A** — per-player RNG seed: `f"{G.seed}:{G.round}:{player_id}:puzzle"`. Each Villager gets a distinct puzzle; determinism is preserved.
   - **Option B** — unseeded `random.Random()`. Puzzles become non-deterministic; test fixtures asserting puzzle content would break.

4. **ADR-003 §8** governs the `decoy_reveal_delay_ms` field — a server-seeded timing value on `StrippedPlayerState` designed to prevent network timing analysis. That decision does not govern puzzle content generation. This ADR does not conflict with ADR-003 §8.

5. **ADR-007** governs WS message type protocol only. This ADR is engine-layer and does not intersect with ADR-007.

---

## Decision

### 1. Add `player_id` to the puzzle RNG seed

`engine/puzzle_bank.py` — `generate_night_puzzle()` signature and seed:

```python
# Before
def generate_night_puzzle(G: "MasterGameState") -> "PuzzleState":
    rng = random.Random(f"{G.seed}:{G.round}:puzzle")

# After
def generate_night_puzzle(G: "MasterGameState", player_id: str) -> "PuzzleState":
    rng = random.Random(f"{G.seed}:{G.round}:{player_id}:puzzle")
```

The seed string becomes `"{game_seed}:{round}:{player_id}:puzzle"`. For any fixed (game, round, player) triple, the output is fully reproducible. Across players in the same round, the seed differs → distinct puzzles. The 400-entry `BANK` and procedural math/sequence generators remain unchanged.

### 2. Move `puzzle_state` from `NightActions` to `PlayerState`

`engine/state/models.py` — `NightActions`:
```python
# Remove:
puzzle_state: PuzzleState | None = None
```

`engine/state/models.py` — `PlayerState`:
```python
# Add:
puzzle_state: PuzzleState | None = None   # only set for wakeOrder==0 players during NIGHT
```

This field is `None` for all players outside the night phase and for players with `wakeOrder != 0`. The state stripper already delivers only the current player's `PlayerState` fields — no additional stripping logic is needed for the field location change.

### 3. Generate per-player puzzles during NIGHT transition

`engine/phases/machine.py` — `transition_phase()`, NIGHT entry block:

```python
# Before
from engine.puzzle_bank import generate_night_puzzle
G.night_actions.puzzle_state = generate_night_puzzle(G)

# After
from engine.puzzle_bank import generate_night_puzzle
for pid, player in G.players.items():
    if not player.is_alive:
        continue
    role_def = ROLE_REGISTRY.get(player.role or "", {})
    if role_def.get("wakeOrder", 0) == 0:
        player.puzzle_state = generate_night_puzzle(G, pid)
    else:
        player.puzzle_state = None
```

The loop runs once at phase entry (pure function, no I/O). For a game with 4 Villager players, 4 distinct puzzles are generated — each seeded by the player's own `player_id`.

### 4. Update the state stripper

`engine/stripper.py` — the display and player view functions currently read `G.night_actions.puzzle_state`. Update to read from the player's own `PlayerState.puzzle_state`. The `correct_index` stripping rule is unchanged — it is stripped from `puzzle_data` before broadcast regardless of where `puzzle_state` lives.

### 5. Update the puzzle answer handler

`api/intents/handlers.py` — `handle_submit_puzzle_answer()` currently validates the answer against `G.night_actions.puzzle_state`. Update to validate against `G.players[player_id].puzzle_state`.

### 6. Option B (unseeded random) is explicitly rejected

Replacing `random.Random(seed)` with an unseeded `random.Random()` is rejected for two reasons:

- **Test breakage**: ADR-005 §3 notes that puzzle tests rely on the FakeWebSocket class being updated if the WS layer changes. By analogy, puzzle generation tests that assert on content for a known (seed, round) pair would become non-deterministic and untestable without extensive mocking.
- **Replay loss**: A game state snapshot stored in Redis can no longer reconstruct what puzzle a player was shown, making post-game debugging and dispute resolution impossible. The party game context does not require cryptographic randomness — per-player seed variation is sufficient.

---

## Consequences

### State Model

- `NightActions.puzzle_state` field removed.
- `PlayerState.puzzle_state: PuzzleState | None` field added (nullable; `None` for active-role players and outside night phase).
- `data_dictionary.md` must be updated to reflect the field migration.

### Engine

- `generate_night_puzzle(G)` → `generate_night_puzzle(G, player_id)` — one additional positional argument.
- NIGHT transition loop adds O(n) puzzle generation calls where n = number of Villager-class players. Each call is a pure deterministic computation with no I/O — negligible performance impact.

### Stripper

- `correct_index` stripping logic moves to read from `player.puzzle_state` instead of `G.night_actions.puzzle_state`. Security guarantee (no `correct_index` in any broadcast) is unchanged.

### Tests

- Any test asserting on `night_actions.puzzle_state` must be updated to assert on `G.players[player_id].puzzle_state`.
- The `generate_night_puzzle` call site in test fixtures must supply a `player_id` argument.
- Seeded test scenarios remain deterministic — a test that seeds with a known `(G.seed, G.round, player_id)` triple will always produce the same puzzle. No test randomness is introduced.

### Positive

- Villagers in the same game and round now receive distinct puzzles. Physical co-location cannot reveal alignment via puzzle comparison.
- Determinism is preserved. The seed `f"{G.seed}:{G.round}:{player_id}:puzzle"` gives full reproducibility per player.
- No new dependencies. The change is confined to four existing engine files plus stripper.
- The hint generation function already uses the per-player seed pattern: `random.Random(f"{G.seed}:{G.round}:{player_id}:hint")` — this ADR applies the same convention consistently.

### Negative

- `NightActions.puzzle_state` field removal is a breaking schema change. Any client or test code that accesses `state.night_actions.puzzle_state` directly will receive `None` or a key error. All such sites must be updated atomically with the backend deploy.
- The NIGHT transition loop is slightly more verbose. With a maximum of 18 players and typically 3–6 Villagers per game, the loop cost is negligible.
