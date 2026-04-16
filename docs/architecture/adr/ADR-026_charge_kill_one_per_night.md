# ADR-026: One Kill Per Night — Charge vs Vote Priority

**Status:** Accepted  
**Date:** 2026-04-15  
**Author:** bethCoderNewbie  
**Related:** PRD-015, RFC-002, ADR-020 (wolf pack kill majority vote)

---

## Context

PRD-015 introduces a second wolf-team kill path: a cooperative charge attack. The charge fires when the pack's combined `accumulated_ms` for a quadrant reaches 5000 ms, immediately disrupting active villager solvers and recording a kill target for night resolution.

Two kill paths now exist:
1. **Vote kill** — `wolf_votes` strict majority → `resolve_night()` step 7
2. **Charge kill** — `charge_kill_target_id` set by `_apply_charge_fire()` → consumed at step 7

Without a priority rule, both could fire in the same night (e.g., charge fires mid-night, wolves also reach vote majority at timer expiry). Two wolf kills per night would break game balance.

Three resolution strategies were considered:

**Option A: First-fires-wins** — whichever path fires first wins; the other is discarded.  
**Option B: Vote wins** — if votes reach majority before night end, vote kill proceeds; charge disrupts but does not kill.  
**Option C: Charge wins** — if charge fires during the night, it takes priority at resolution; vote kill is discarded.

---

## Decision

**Option C: Charge kill takes priority over vote kill.**

`_step7_wolf_kill_or_infect` checks `charge_kill_target_id` first. If set, charge kill runs (with full protection checks) and the function returns early — `wolf_votes` are not tallied. If `charge_kill_target_id` is `None`, vote kill proceeds as before.

---

## Consequences

**Why charge priority (not vote priority):**
- The charge is a higher-risk play: wolves must cooperate on a real-time physical gesture while sacrificing the predictability of the vote. Priority reward is appropriate.
- Wolves cannot gain extra kills: charge fires at most once per night (subsequent fires on the same target are no-ops via `if G.night_actions.charge_kill_target_id is None`).
- Vote kill path is unchanged for nights where no charge fires — zero regression risk to existing majority-vote logic.

**Why no auto-submit on charge fire:**
An earlier design considered auto-submitting wolf `submit_night_action` when a charge fires, allowing the night to auto-advance without waiting for the timer. This was rejected:
- `DUPLICATE_ACTION` guard prevents wolves from submitting twice.
- Auto-advance on all actions submitted is intentionally disabled so players cannot infer submission timing from phase transitions.
- Wolves who charged still need to wait for the night timer.

**Why pool-based (not first-wolf-fires):**
Cooperative model (sum of all wolves' `accumulated_ms`) is more balanced than a solo threshold:
- 1 wolf must hold 5 s alone — meaningful risk.
- 2 wolves coordinate 2.5 s each — incentivizes teamwork.
- A single wolf cannot cheaply fire on behalf of the pack without effort.

**Protection parity:**
`_apply_wolf_kill(G, target_id, cause, attacker_pid)` extracts the shared Wise shield / Doctor / Bodyguard 50/50 / SK immunity logic. Both charge kill and vote kill pass through identical protection checks. This eliminates code duplication and ensures no protection mechanism can be bypassed by using one kill path over the other.

**Bodyguard attacker identity:**
For the vote kill path, the "attacker" for the Bodyguard's 50% attacker-dies coin flip is the first wolf who voted for the kill target. For the charge kill path, there is no single voter — the attacker is set to the first alive wolf in the game state. This is a minor inconsistency but acceptable: the Bodyguard mechanic's primary effect (protecting the target) is identical in both paths.
