# PRD-013: Werewolf — Night Grid & Wolf Radar System

## §1. Context & Purpose

**Feature:** Night Grid + Wolf Radar
**Depends on:** PRD-001 §2 (Archive puzzle system), PRD-007 (night phase UX), PRD-010 (hint enhancement), ADR-008 (per-player puzzle generation), ADR-012 (puzzle bank category enrichment)

The current night phase has two problems:

1. **Villager passivity.** wakeOrder==0 players receive exactly one Archive puzzle per night and then wait. After ~30 seconds their screen goes idle. There is no spatial, exploratory mechanic — each night is identical in structure.

2. **Wolf information vacuum.** Wolves select a kill target and see nothing else. The wolf night screen is a blank dark panel. There is no asymmetric information advantage to being a wolf during the night phase itself — all the asymmetry lives in the day phase.

This PRD introduces two complementary mechanics that **coexist** with the existing Archive puzzle:

- A **5×5 Data Node grid** villagers can navigate to solve additional puzzles, with three tiers of hint value calibrated to puzzle difficulty.
- A **Wolf Radar screen** where wolves observe anonymized villager grid activity via Sonar Pings, creating a real-time spatial tension: the harder the hint, the louder the signal.

---

## §2. Mechanic Specification

### §2.1 The Data Node Grid (Villager View)

A 5×5 grid of 25 nodes is generated fresh each night, seeded by `f"{G.seed}:{G.round}:grid_layout"` (deterministic per round). Each cell has a tier:

| Color | Tier | Time Limit | Hint Quality | Grid Count |
|-------|------|-----------|--------------|------------|
| Green | 1 | 5 seconds | Composition + existing Archive categories | 18 |
| Yellow | 2 | 10 seconds | Relational logic (alignment links, player groups) | 6 |
| Red | 3 | 20 seconds | Specific intelligence (innocent clears, action logs) | 1 |

**Node interaction flow:**
1. Villager taps a node → sends `select_grid_node {row, col}` → backend assigns a tiered puzzle to `player.grid_puzzle_state`
2. Timer starts; player solves the puzzle (same format as Archive: logic / math)
3. Correct answer → tier-appropriate hint unicasted; node marked completed (greys out); player can navigate to next node
4. Wrong answer → no hint; node clears; player can try a different node

**Coexistence with Archive:** The Archive puzzle (`player.puzzle_state`) runs in parallel on the ARCHIVE tab. Players toggle between ARCHIVE tab (existing system, unchanged) and GRID tab (this feature) on their mobile night screen.

**Completed node tracking:** `grid_activity` in `NightActions` stores an anonymized record for each completed node: `{row, col, quadrant, sequence_idx}`. No player IDs are included — this is the data source for Wolf Radar. Villagers do not see `grid_activity`.

### §2.2 Hint Tiers

#### Tier 1 — Composition + Recap (green nodes, 5s)
All existing Archive hint categories plus three new ones:

| Category | Text (round 3+) | Notes |
|----------|-----------------|-------|
| `wolf_count` | "There are N Wolves total in this game." | Existing |
| `no_role_present` | "There is NO [Role] in this game." | Existing |
| `role_present` | "There IS a [Role] in this game." | Existing |
| `neutral_exists` | "At least one Neutral player is alive." | Existing |
| `non_wolf_kill` | "The last night's death was not the wolves' doing." | Existing |
| `lovers_exist` | "Two players are bound together — if one falls, the other follows." | Existing |
| `alive_count` | "There are currently N Wolves and M Villagers alive." | **New** |
| `role_alive_check` | "The [Role] is still alive." / "There is no [Role] in this match." | **New** — uses _HIGH_IMPACT_ABSENT_ROLES |
| `night_recap` | "The Wolves have used N Sonar Pings tonight." | **New** — exposes wolf radar activity |

Round-gated vagueness (rounds 1–2) applies to all Tier 1 categories that have vague forms, consistent with ADR-018.

#### Tier 2 — Relational Logic (yellow nodes, 10s)

| Category | Text | Risk Level |
|----------|------|-----------|
| `one_of_three` | "At least one Wolf is among [A], [B], and [C]." | High — guaranteed wolf in the named group |
| `same_alignment` | "[A] and [B] share the same alignment." | Medium — binary claim |
| `diff_alignment` | "[A] and [B] are NOT on the same team." | Medium — binary claim |
| `positional_clue` | "High activity was detected in the [quadrant] tonight." | Low — spatial only, no player names |

**`one_of_three` generation:** Pick 1 alive wolf + 2 alive non-wolves → shuffle → name all three. Guaranteed to contain exactly one wolf. If < 1 wolf or < 2 non-wolves alive: fall back to `same_alignment`.

**Volatility note:** If wolves intercept Tier 2 hints (via the Framer's `hack_archives` on the Archive system), they can contradict alignment links during the day phase. This is an intended asymmetry — the Framer's usefulness peaks when the village starts receiving relational hints.

No round-gating for Tier 2: relational hints are always specific (they must name players to have value).

#### Tier 3 — Specific Intelligence (red node, 20s)

| Category | Text | Notes |
|----------|------|-------|
| `innocent_clear` | "The Archives confirm: [Player H] is NOT a Wolf." | Pick 1 alive non-wolf at random |
| `action_log` | "A player in this game changed their mind N times during the night phase." | Highest-changed player from `night_action_change_count`; no name revealed |

**Wolf detection cost for Tier 3:** The single red node takes 20 seconds. The wolf radar will show high-tier activity in that quadrant, and any sonar ping scanning that quadrant will reveal `tier_counts: {"3": 1}`. Wolves know a Tier 3 node is being solved and can infer someone in that quadrant just received an innocent clear. This creates the intended trade-off: the highest-value hint is the loudest.

**`action_log` tracking:** `night_action_change_count[player_id]` increments on every intent submission during the night phase (applies to all roles: wolf vote changes, grid node selections, sonar pings, Archive answers). The hint text reveals the maximum count without naming the player.

### §2.3 Wolf Radar Screen

Wolves gain a new RADAR tab alongside their existing kill-vote UI (WolfVoteUI).

**Radar display:**
- Dark circular radar divided into 4 quadrants (top-left, top-right, bottom-left, bottom-right)
- Per-quadrant glow intensity proportional to completed nodes in that quadrant (0 nodes = dark, 5+ = bright)
- Glow color reflects highest tier completed in that quadrant (green/yellow/red)

**Sonar Ping mechanic:**
- Wolf sends `sonar_ping {quadrant}` intent
- Server returns: `{quadrant, heat: N, tier_counts: {"1": N, "2": N, "3": N}}`
- Result stored in `sonar_ping_results`; `sonar_pings_used` increments
- No limit on pings per night (but `night_recap` Tier 1 hint exposes the total count to villagers)

**Grid ripple animation:**
- When any villager completes a grid node, server broadcasts `grid_ripple {quadrant, tier}` side-channel event (does not wait for state update)
- Wolf clients receiving `grid_ripple` immediately animate an expanding ring in the matching quadrant, colored by tier
- This gives real-time feedback before the full state update arrives

**What wolves do NOT see:**
- Which specific player solved the node (no player IDs in `grid_activity`)
- The `grid_layout` tier map (wolves cannot know which cells are red before pinging)
- Archive puzzle results (those are a separate system)

---

## §3. WebSocket Payload Schema

### §3.1 Client → Server Intents

```jsonc
// Villager selects a grid node
{ "type": "select_grid_node", "row": 2, "col": 4 }

// Villager submits answer for their active grid node puzzle
{ "type": "submit_grid_answer", "answer_index": 2 }

// Wolf fires a sonar ping at a quadrant
{ "type": "sonar_ping", "quadrant": "top_right" }
```

### §3.2 Server → Client Events

```jsonc
// Side-channel: fires immediately when a node is completed (wolf radar animation)
{ "type": "grid_ripple", "quadrant": "bottom_left", "tier": 2 }

// Hint unicast (existing hint_reward type, new grid categories)
{
  "type": "hint_reward",
  "hint_id": "aB3xK9pQ2w-m",
  "category": "one_of_three",
  "text": "At least one Wolf is among Alice, Bob, and Carol.",
  "round": 2,
  "expires_after_round": null
}
```

### §3.3 State Fields per View

| Field | Display | Wolf | Villager | Dead |
|-------|---------|------|----------|------|
| `night_actions.grid_layout` | ✓ | ✓ | ✓ | — |
| `night_actions.grid_activity` | — | ✓ | — | — |
| `night_actions.sonar_pings_used` | ✓ | ✓ | ✓ | — |
| `night_actions.sonar_ping_results` | — | ✓ | — | — |
| `night_actions.night_action_change_count` | — | — | — | — |
| `player.grid_puzzle_state` (own) | — | — | ✓ | — |
| `player.grid_node_row/col` | — | — | — | — |

---

## §4. Client-Server Specifications

### §4.1 Guard Conditions

| Intent | Guards |
|--------|--------|
| `select_grid_node` | phase==NIGHT, player alive, wakeOrder==0, no active `grid_puzzle_state`, row/col in [0,4], node not in `grid_activity` |
| `submit_grid_answer` | phase==NIGHT, player alive, `grid_puzzle_state` exists and `active==True` |
| `sonar_ping` | phase==NIGHT, player alive, team==werewolf, quadrant in valid set |

### §4.2 Error Responses (existing error format)

| Code | Condition |
|------|-----------|
| `WRONG_PHASE` | Intent sent outside NIGHT |
| `NODE_OCCUPIED` | Attempting to select a node already in `grid_activity` |
| `NO_ACTIVE_PUZZLE` | Submitting answer when no grid puzzle is active |
| `INVALID_QUADRANT` | Sonar ping quadrant not in valid set |

---

## §5. Phase-Gate Plan

| Gate | Criterion | Verify |
|------|-----------|--------|
| G1 | Backend data model + machine.py init | `pytest tests/engine/test_grid_system.py::test_grid_layout_generation` |
| G2 | Stripper isolation | `pytest tests/engine/test_grid_system.py::test_stripper_grid_fields` — assert wolves see `grid_activity`, villagers don't |
| G3 | Intent handlers | `pytest tests/engine/test_grid_system.py::test_select_grid_node` etc. |
| G4 | Hint tier generation | `pytest tests/engine/test_grid_system.py::test_tier2_one_of_three` etc. |
| G5 | Frontend grid renders | Dev server: villager night screen shows 5×5 grid with correct tier colors |
| G6 | Wolf radar animates | Dev server: solve a node → wolf screen ripples in correct quadrant |
| G7 | Regression | `pytest tests/ -v` — all 236+ existing tests pass |

---

## §6. User Stories

| As a | I want to | So that |
|------|-----------|---------|
| Mobile Player (Villager) | see a 5×5 grid of colored nodes on the GRID tab during night phase | I have an interactive alternative to waiting after the Archive puzzle |
| Mobile Player (Villager) | tap a green node and receive a 5-second puzzle for a Tier 1 hint | I can quickly harvest composition hints at low risk |
| Mobile Player (Villager) | tap the red node and receive a 20-second puzzle for a Tier 3 innocent clear | I can take a high-risk, high-reward gamble on definitive intelligence |
| Mobile Player (Wolf) | see a radar screen showing quadrant ripple animations during night phase | I gain spatial awareness of where villagers are concentrating their efforts |
| Mobile Player (Wolf) | fire Sonar Pings at specific quadrants to see heat levels and tier breakdowns | I can identify which quadrants are generating high-value hints and adjust my day-phase strategy |
| Game Server | broadcast `grid_ripple` side-channel events immediately on node completion | Wolf clients receive real-time animation triggers before the full state update arrives |
| Game Server | never include player IDs in `grid_activity` | Wolves cannot identify which specific player solved a node |
| Mobile Player (Villager) | see on the night recap that wolves used N Sonar Pings | I know whether the wolves were actively watching the grid this round |

---

## §7. Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | Should there be a limit on Sonar Pings per night, or is unlimited pings balanced given the `night_recap` counter hint? | Open — current spec: unlimited, counter exposed to villagers |
| 2 | Should `grid_layout` be regenerated mid-night (e.g., after each node completion) or fixed for the entire night? | Decided: fixed per night (seeded at transition) |
| 3 | Should the Framer be able to hack grid hints as well as Archive hints? | Open — current spec: Framer only targets Archive (`puzzle_state`), not `grid_puzzle_state` |
| 4 | Should dead players (spectators) see an anonymized version of the grid on the Display screen? | Open — current spec: Display shows only `sonar_pings_used` aggregate |
