# ADR-018: Werewolf — Hint Round-Gated Specificity

## Status
Accepted

## Date
2026-04-13

## Context

The Archive hint system (`engine/puzzle_bank.py`) generates a `HintPayload` for `wakeOrder==0` players who correctly solve their night puzzle. Prior to this ADR, all hints were equally specific regardless of the round number — a round-1 hint naming "There is NO Alpha Wolf in this game" had the same precision as an identical round-5 hint.

This uniformity created two balance problems:

1. **Early-game over-precision.** A single round-1 puzzle solve could immediately eliminate a high-value role from suspicion (e.g., confirming the Framer is absent). The village gained full intelligence on first opportunity with no progression dynamic.

2. **No engagement curve.** Every hint was functionally identical across all rounds. There was no incentive to interpret hints across multiple rounds or weight later hints more heavily. The system had no narrative arc.

Additionally, two data sources available on `MasterGameState` had no corresponding hint categories:
- `G.elimination_log` — records past kills and their causes (wolf, SK, arsonist, broken heart, hunter)
- `G.lovers_pair` — records Cupid-linked players (set in round 1)

Both are meaningful for village decision-making and previously surfaced no signal through the hint system.

---

## Decision

### 1. Round threshold constant

A single module-level constant controls the precision cutoff:

```python
_VAGUE_ROUND_THRESHOLD = 3  # rounds 1–2 vague; round 3+ specific
```

Inside `generate_hint()`:
```python
is_vague = G.round < _VAGUE_ROUND_THRESHOLD
```

Threshold 3 was chosen because:
- A typical 8–10 player game runs 4–6 rounds. Vagueness in rounds 1–2 spans the setup phase; specificity arrives once eliminations have begun and the village has day-vote data to cross-reference.
- Round 3 is the first night where last-round behavioral hints (`non_wolf_kill`) can meaningfully fire, making it a natural transition point.
- Setting threshold at 2 (only round 1 vague) produces too brief a vague window; threshold 4 delays specificity past the midgame.

### 2. Vague text design per category

Vague text must provide *directional signal* without *actionable specifics*:

| Category | Vague approach |
|---|---|
| `wolf_count` | Range ± 1 from actual count (floor 1): "between N-1 and N+1 Wolves" |
| `no_role_present` | Category-level signal only: "a certain powerful role is absent" |
| `role_present` | Category-level signal only: "at least one special role is in play" |
| `lovers_exist` | Existence without mechanical consequence: "share an unbreakable bond" (vs. the co-death implication in specific text) |

`neutral_exists` and `non_wolf_kill` are behavioral hints and have no vague form — behavioral facts are either confirmed or withheld, not approximated.

### 3. RNG sequence preservation in vague rounds

For `no_role_present` and `role_present`, `rng.choice()` is still called on the role-candidate list even when the round is vague and the selected name is not used in the text:

```python
absent = [r for r in _HIGH_IMPACT_ABSENT_ROLES if r not in composition]
if absent:
    role_name = rng.choice(absent)          # advances RNG even in vague rounds
    if is_vague:
        text = "The Archives hint that a certain powerful role is absent from this game."
    else:
        text = f"There is NO {role_name.replace('_', ' ').title()} in this game."
```

**Why:** `generate_hint()` is seeded by `f"{G.seed}:{G.round}:{player_id}:hint"`. The final `rng.choice(pool)` — which selects from the full hint pool — must receive the same RNG state regardless of round number. If `rng.choice(absent)` were skipped in vague rounds, the final pool selection would produce different results than in specific rounds for the same `(seed, round, player_id)` triple. Skipping is therefore incorrect even though the return value is unused.

This is a subtle invariant: **the RNG call pattern must be identical across all rounds**. Any future change that adds a conditional `rng.choice()` call must apply the same pattern.

### 4. New category: `non_wolf_kill`

Source: `G.elimination_log` (filtered to previous night, cause ∈ non-wolf causes).

Added to module level to avoid per-call set construction:
```python
_NON_WOLF_CAUSES = {"arsonist_ignite", "serial_killer_kill", "broken_heart", "hunter_revenge"}
```

Round guard (`G.round >= 2`) prevents access before the first night's events exist in `elimination_log`. The hint expires next round (`expires_after_round = G.round + 1`) because the information is only relevant for the current day vote.

**Option considered and rejected:** Include `wolf_kill` as a separate category ("a wolf kill occurred last night"). Rejected because this is baseline expected behavior that adds no signal — the village already assumes wolves killed unless told otherwise.

### 5. New category: `lovers_exist`

Source: `G.lovers_pair is not None`.

`G.lovers_pair` is a list of two `player_id` strings set by Cupid during night 1 resolution. It persists unchanged for the game's duration. The hint is treated as a permanent composition hint (`expires_after_round = None`).

The hint does not reveal *who* the lovers are — only that a pair exists. Naming the lovers would be an information leak of a different magnitude; the current text is directional, not identifying.

Vague/specific branching applies because:
- Round 1–2 text ("unbreakable bond") establishes existence only.
- Round 3+ text explicitly states the mechanical consequence ("if one falls, the other follows"), which is the strategically relevant fact for day voting.

### 6. Option considered: client-side round gating

An alternative was to send both `vague_text` and `specific_text` fields in the payload and let the client select based on `round`. This was rejected:
- It doubles the payload size for no benefit.
- It would require schema changes and frontend updates.
- It exposes both versions to the client, allowing a motivated player to inspect WebSocket traffic and read the specific text even in early rounds.
- Server-side generation keeps precision entirely under server control.

---

## Implementation

### File: `backend-engine/engine/puzzle_bank.py`

- Add `_VAGUE_ROUND_THRESHOLD = 3` and `_NON_WOLF_CAUSES` constants at module level (after `_BASELINE_ROLES`, ~line 58)
- In `generate_hint()`: add `is_vague = G.round < _VAGUE_ROUND_THRESHOLD` after `rng` init
- Rewrite `wolf_count`, `no_role_present`, `role_present` pool entries to branch on `is_vague`
- Add `non_wolf_kill` pool entry after `neutral_exists` block (round guard: `G.round >= 2`)
- Add `lovers_exist` pool entry after `non_wolf_kill` block (guard: `G.lovers_pair`)

### File: `backend-engine/tests/engine/test_puzzle_bank.py` (new)

28 unit tests covering:
- Vague text in rounds 1–2 and specific text in round 3+ for all affected categories
- `non_wolf_kill` appearing/absent based on `elimination_log` content and round number
- `lovers_exist` appearing/absent based on `G.lovers_pair`
- Vague/specific text content for `lovers_exist`
- Payload structure invariants (`type`, `hint_id`, `round`, `expires_after_round`)

### No other file changes required

| File | Change |
|---|---|
| `puzzle_bank.py` | `generate_hint()` only |
| `engine/state/models.py` | None — `HintPayload` schema unchanged |
| `engine/stripper.py` | None — hint delivery path unchanged |
| `api/intents/handlers.py` | None — `generate_hint()` call site unchanged |
| `frontend-mobile/` | None — `latestHint.text` rendered verbatim |
| `frontend-display/` | None — display never receives hint content |

---

## Consequences

### Positive

- **Engagement arc.** Villagers are rewarded for earning multiple hints across rounds — early hints are directional, later hints are decisive.
- **Framer early-hack advantage.** A Framer who hacks in round 1 with a specific false hint creates a timing discrepancy (specific claim before real hints are specific). Attentive players who track hint precision over rounds could detect this as a tell.
- **Two new data surfaces.** `non_wolf_kill` and `lovers_exist` make previously invisible game state (non-wolf threats, Cupid mechanics) legible through the hint system without naming specific players.
- **Schema unchanged.** Zero frontend or network protocol changes.

### Negative / Trade-offs

- **Framer false hints bypass vagueness.** Wolves who hack Archives in round 1 can inject specific-sounding false intel before real hints are specific. This is a mild power advantage for the wolf team in early rounds with an active Framer. Considered acceptable — it introduces a subtle detection vector for village players.
- **`_VAGUE_ROUND_THRESHOLD` is a magic constant.** It is not configurable per game size. A 5-player game and a 12-player game use the same threshold. This may need revisiting if game balance data shows early-game is too constrained or too open for small/large player counts (see PRD-010 §7 Q2).
- **RNG call pattern is load-bearing.** Future contributors adding conditional `rng` calls in `generate_hint()` must maintain the invariant of always calling `rng.choice()` even when the result is unused. A comment documents this; no structural enforcement exists.
