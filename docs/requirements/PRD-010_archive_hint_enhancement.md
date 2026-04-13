# PRD-010: Werewolf — Archive Hint Enhancement (Round-Gated Vagueness + New Categories)

## §1. Context & Purpose

**Feature:** Archive Hint Enhancement
**Depends on:** PRD-001 §2 (Archive puzzle system), `roles.json` `archivePuzzleSystem`, `data_dictionary.md` `HintPayload`, ADR-008 (per-player puzzle generation)

The Archive puzzle system delivers a `HintPayload` to `wakeOrder==0` players who solve their night puzzle. The original hint system generates four static categories — `wolf_count`, `no_role_present`, `role_present`, `neutral_exists` — with no progression over the course of the game. Every hint is equally precise whether it is round 1 or round 5.

This PRD extends the hint system in two directions:

1. **Round-gated vagueness.** Hints in the first two rounds are deliberately imprecise — they reveal *direction* without naming specifics. From round 3 onward, hints become concrete. This creates a natural intelligence arc: the village must act on partial information early and refine their understanding as the game progresses.

2. **Two new hint categories.** `non_wolf_kill` surfaces behavioral evidence of non-wolf threats active the previous night. `lovers_exist` reveals the presence of Cupid-linked players without naming them. Both categories add signal that is currently invisible to the village even when directly relevant.

**No frontend changes required.** The `HintPayload.text` field is pre-formatted server-side and rendered verbatim in `VillagerDecoyUI.tsx:262`. The schema is unchanged.

---

## §2. Mechanic Specification

### §2.1 Round-Gated Vagueness

A single threshold divides hint precision:

| Round | Mode | Description |
|-------|------|-------------|
| 1–2 | **Vague** | Hints reveal category direction without naming specifics. No role names, no exact counts. |
| 3+ | **Specific** | Hints are exact. Role names, precise counts, direct statements. |

The threshold is `_VAGUE_ROUND_THRESHOLD = 3` in `engine/puzzle_bank.py`.

#### §2.1.1 Per-Category Vague Text

| Category | Vague (rounds 1–2) | Specific (rounds 3+) |
|---|---|---|
| `wolf_count` | `"The Archives suggest between {N-1} and {N+1} Wolves are present in this game."` (N = actual count; floor at 1) | `"There are {N} Wolves total in this game."` |
| `no_role_present` | `"The Archives hint that a certain powerful role is absent from this game."` | `"There is NO {Role Name} in this game."` |
| `role_present` | `"The Archives suggest at least one special role is in play beyond the basics."` | `"There IS a {Role Name} in this game."` |
| `neutral_exists` | *(unchanged — behavioral, already approximate)* | *(unchanged)* |
| `non_wolf_kill` | *(behavioral — always specific, expiry is the limiting factor)* | *(same)* |
| `lovers_exist` | `"Two souls in this village share an unbreakable bond."` | `"Two players are bound together — if one falls, the other follows."` |

**RNG consistency:** When a hint is vague, the role-name selection (`rng.choice(absent)` / `rng.choice(present_special)`) still executes to advance the seeded RNG state. The selected name is simply not embedded in the vague text. This preserves determinism — a given `(seed, round, player_id)` triple always maps to the same underlying pool and selection, regardless of whether the round is vague or specific.

#### §2.1.2 Strategic Rationale

Early-round vagueness means:
- The village cannot pinpoint a missing role from a single round-1 hint and immediately dismiss it.
- Wolf count ranges leave room for doubt — "somewhere between 1 and 3" is less actionable than "exactly 2."
- Villagers are rewarded for solving puzzles across multiple rounds: the same composition hint becomes more precise as the game deepens.

The Framer's false hint categories (`wolf_count`, `no_role_present`, `role_present`) are also subject to round-gated vagueness when real hints are generated. However, **Framer-crafted false hints bypass `generate_hint()` entirely** — they are pre-formatted text strings submitted directly in the `hack_archives` intent. False hints are always delivered verbatim regardless of round, which means a Framer may inject a specific false hint in round 1 when real hints are still vague. This is intentional: it creates a subtle tell for attentive players and a risk for wolves choosing to hack early.

---

### §2.2 New Category: `non_wolf_kill`

**Trigger:** At the start of round N (N ≥ 2), if any `EliminationEvent` in `G.elimination_log` has:
- `round == N - 1`
- `phase == "night"`
- `cause` ∈ `{arsonist_ignite, serial_killer_kill, broken_heart, hunter_revenge}`

**Text:** `"The last night's death was not the wolves' doing."`

**Expiry:** `expires_after_round = G.round + 1` — stale after one round.

**Not round-gated:** This hint is behavioral (references a specific past event). There is no vague form; the fact of a non-wolf kill is either known or it is not.

**Strategic value:** Alerts the village that a second threat is active. When the wolf team did not kill last night, this hint surfaces the reason. A village that might otherwise assume "wolves missed" or "doctor saved" can now recalibrate: the Serial Killer, Arsonist, or a broken-heart cascade is responsible.

**Eligibility guard:** Only enters the hint pool in rounds ≥ 2. No behavioral data exists for round 1 (no previous night has occurred).

**Framer forbids fabrication:** `non_wolf_kill` is a behavioral category and cannot be fabricated by the Framer (PRD-004 §2.2). It joins `neutral_exists` and `seer_blocked_last_night` on the `forbiddenFalseCategories` list.

---

### §2.3 New Category: `lovers_exist`

**Trigger:** `G.lovers_pair is not None` — Cupid linked two players during round 1.

**Text:**
- Rounds 1–2: `"Two souls in this village share an unbreakable bond."`
- Round 3+: `"Two players are bound together — if one falls, the other follows."`

**Expiry:** `null` — permanent composition hint. The lovers_pair never changes after round 1.

**Strategic value:** Informs the village that a mutual-death mechanic is in play without naming who the lovers are. In round 3+, the mechanical consequence (co-death) is spelled out explicitly, giving the village actionable context: voting out a player carries hidden collateral risk.

**Only available when Cupid is in the game.** If no `cupid` role is in the composition, `G.lovers_pair` remains `None` throughout the game and this category never enters the hint pool.

**Framer forbids fabrication:** `lovers_exist` is effectively a composition hint, but the Framer has no mechanism to set or observe `G.lovers_pair`. It is excluded from `allowedFalseCategories` to prevent incoherent injection (claiming lovers exist when Cupid is not in the game).

---

## §3. Resolution and Delivery — No Change

The hint delivery pipeline (PRD-004 §2.3) is unchanged:
- Hint generation fires in `handle_submit_puzzle_answer` (handlers.py:339–351) immediately after a correct solve.
- False hint check (`false_hint_queued`) takes precedence over `generate_hint()` — unchanged.
- The `HintPayload` schema is unchanged: `type`, `hint_id`, `category`, `text`, `round`, `expires_after_round`.
- `is_fabricated` stripping for false hints is unchanged.

---

## §4. Server State Examples

### §4.1 Round 1 — Vague Hint (3 wolves, no Framer hack)

```jsonc
// Round 1, night. p6 (Villager) solves puzzle.
// Actual composition: 3 werewolves, 1 alpha_wolf, 1 seer, 1 doctor, 2 villagers
// generate_hint selects wolf_count (vague). Range: max(1, 3-1)=2 to 3+1=4.
{
  "_hint_unicast_to_p6": {
    "type": "hint_reward",
    "hint_id": "Xe2mK1pQzN-v",
    "category": "wolf_count",
    "text": "The Archives suggest between 2 and 4 Wolves are present in this game.",
    "round": 1,
    "expires_after_round": null
  }
}
```

### §4.2 Round 3 — Specific Hint

```jsonc
// Round 3. p6 solves puzzle.
// Same game: 3 wolves, alpha_wolf present.
// generate_hint selects wolf_count (specific).
{
  "_hint_unicast_to_p6": {
    "type": "hint_reward",
    "hint_id": "Wq9nR4bYjL-k",
    "category": "wolf_count",
    "text": "There are 3 Wolves total in this game.",
    "round": 3,
    "expires_after_round": null
  }
}
```

### §4.3 Round 3 — `non_wolf_kill` (Serial Killer active last night)

```jsonc
// Round 3. Serial Killer killed p4 in round 2 night.
// non_wolf_kill enters hint pool.
{
  "_hint_unicast_to_p6": {
    "type": "hint_reward",
    "hint_id": "Mn3tF8xCpH-q",
    "category": "non_wolf_kill",
    "text": "The last night's death was not the wolves' doing.",
    "round": 3,
    "expires_after_round": 4
  }
}
```

### §4.4 Round 2 — `lovers_exist` (Cupid game, vague)

```jsonc
// Round 2. Cupid linked p3 and p7 in round 1.
// lovers_exist enters pool. Round 2 < 3 → vague text.
{
  "_hint_unicast_to_p6": {
    "type": "hint_reward",
    "hint_id": "Jk7vP2aCwG-r",
    "category": "lovers_exist",
    "text": "Two souls in this village share an unbreakable bond.",
    "round": 2,
    "expires_after_round": null
  }
}
```

---

## §5. Framer Interaction Summary

| Category | Framer can fabricate? | Reason |
|---|---|---|
| `wolf_count` | Yes (existing) | Composition-based; wolf count is knowable to wolves |
| `no_role_present` | Yes (existing) | Composition-based; wolves know their own team |
| `role_present` | Yes (existing) | Composition-based |
| `neutral_exists` | No (existing) | Behavioral; wolves cannot observe neutral alive-state at hack time |
| `seer_blocked_last_night` | No (existing) | Behavioral; roleblock occurs after puzzle delivery |
| `non_wolf_kill` | No (new) | Behavioral; Framer cannot control or predict non-wolf kills |
| `lovers_exist` | No (new) | Composition, but `G.lovers_pair` is not observable by wolves and Cupid's link target is unknown to the wolf team |

---

## §6. User Stories

| As a | I want to | So that |
|------|-----------|---------|
| Mobile Player (Villager, round 1) | receive a hint that hints at direction without naming specifics | I cannot immediately eliminate roles or lock in wolf counts from a single early-game solve |
| Mobile Player (Villager, round 3+) | receive a precise hint with exact counts and role names | I can act on definitive intelligence during the late-game decision phase |
| Mobile Player (Villager) | learn that last night's death was not caused by wolves | I know a secondary threat is active and can factor it into my day vote |
| Mobile Player (Villager, Cupid game) | learn that two players share a death-link | I can account for collateral damage before voting |
| Game Server | apply the same `generate_hint()` code path for both vague and specific rounds | Round-gated text is determined at generation time with no client-side changes |

---

## §7. Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | Should `non_wolf_kill` distinguish *who* caused the kill (e.g., "An Arsonist struck" vs. "The Serial Killer struck")? | Open — current spec is a single undifferentiated text. Specificity would help the village but reduces ambiguity tension. |
| 2 | Should the vague threshold (round 3) be game-size configurable (e.g., earlier specificity for small games)? | Open — current spec is a fixed constant `_VAGUE_ROUND_THRESHOLD = 3`. |
| 3 | Should `lovers_exist` hint evolve further to indicate if one lover has already died (triggering co-death confirmation)? | Open — current spec is static permanent composition hint. |
