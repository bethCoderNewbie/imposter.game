# ADR-020: Wolf Pack Kill — Strict-Majority Vote with Auto-Advance

## Status
Accepted

## Date
2026-04-13

## Context

### Problem

When a game contains more than one wolf-faction player, the server needs a deterministic rule to decide:

1. **Which villager is eliminated** when wolves disagree on the target.
2. **When the night phase resolves** — immediately after wolves submit, or only when *all* night-role players have submitted.

Without a clear documented rule, game-balance and UX issues arise:
- A tie between two targets should not silently kill either player.
- The night phase must not advance the moment the last wolf votes, because other night roles (Seer, Doctor, Tracker, etc.) may still be acting.

---

## Decision

### 1. Wolf Kill Requires Strict Majority (> 50 %)

**File:** `backend-engine/engine/resolver/night.py` — `_step7_wolf_kill_or_infect`

Each wolf-faction player submits their kill vote independently via the `submit_night_action` intent. Votes are stored in `G.night_actions.wolf_votes: dict[str, str]` (wolf_player_id → target_player_id).

At resolution the server counts votes and applies the following rule:

```python
total_wolves = len(wolf_votes)
vote_counts = Counter(wolf_votes.values())
kill_target  = max(vote_counts, key=vote_counts.get)

if vote_counts[kill_target] <= total_wolves / 2:
    return  # tie or plurality — no kill this night
```

**Threshold:** the top target must receive **strictly more than half** of all wolf votes.

| Wolf count | Votes needed to kill |
|------------|----------------------|
| 1          | 1 (always kills)     |
| 2          | 2 (must be unanimous) |
| 3          | 2                    |
| 4          | 3                    |
| N          | ⌊N/2⌋ + 1           |

**Tie = no kill.** Two wolves splitting their votes 1–1 produce no elimination. This is intentional — wolves who cannot coordinate lose their kill for the night.

### 2. How Each Role Casts Its Kill Vote

Wolf-faction roles submit their vote through different intent fields:

| Role | Kill vote field | Notes |
|------|----------------|-------|
| `werewolf` | `target_id` | Required |
| `alpha_wolf` | `target_id` | Required |
| `wolf_shaman` | `secondary_target_id` | Primary `target_id` is the roleblock target |
| `framer` | `wolf_vote_target_id` | Optional — framer may abstain |
| `infector` | `wolf_vote_target_id` | Optional — infector may choose to infect instead |

**Handler file:** `backend-engine/api/intents/handlers.py` — `handle_submit_night_action`

If an infector uses their once-per-game infect ability (`target_id` set, `wolf_vote_target_id` absent), they do not contribute a wolf kill vote. The infect resolves in a separate step before the kill.

### 3. Night Phase Auto-Advances When All Night-Role Players Have Submitted

**File:** `backend-engine/engine/phases/machine.py` — `should_auto_advance`

The night phase ends via **either** of two triggers, whichever fires first:

| Trigger | Condition |
|---------|-----------|
| **Auto-advance** | `actions_submitted_count >= actions_required_count` (all active night-role players have submitted) |
| **Timer expiry** | `night_timer_seconds` elapses with no auto-advance |

`actions_required_count` is computed at night-entry and counts every living player whose role has `wakeOrder > 0`. Villagers (`wakeOrder == 0`) are excluded — they solve decoy puzzles but do not block phase advancement.

**Wolves are not a special gate.** The last wolf submitting does not advance the phase if other night roles (Seer, Doctor, Tracker, etc.) have not yet submitted.

---

## Consequences

**Positive:**
- Coordinating wolves is a meaningful social challenge. A pack that cannot agree loses their kill — consistent with Werewolf lore.
- No special "wolf-only" auto-advance path simplifies the resolver; a single `should_auto_advance` predicate handles all roles uniformly.
- Timer as a fallback ensures the game progresses even if a player is AFK.

**Negative / Trade-offs:**
- With 2 wolves and a split vote, no kill lands. Some players may perceive this as a "wasted" night rather than a consequence of poor coordination. This is by design.
- The strict majority threshold means a 3-wolf game where votes split 1-1-1 also produces no kill. Edge case, but possible late-game.

---

## Related

- `backend-engine/engine/resolver/night.py` — full 13-step night resolution pipeline
- `backend-engine/engine/phases/machine.py` — `should_auto_advance`, `compute_actions_required`
- `backend-engine/api/intents/handlers.py` — per-role night action submission logic
- ADR-002: Framer dual-target architecture (framer's two independent night actions)
