# PRD-015: Wolf Charge Attack & Villager Defend

**Status:** Implemented  
**Author:** bethCoderNewbie  
**Date:** 2026-04-15  
**Related:** RFC-002, ADR-026, PRD-013 (Night Grid)

---

## 1. Context & Problem

PRD-013 introduced the Night Grid system: villagers solve data-node puzzles to earn hints while wolves use Sonar Pings to observe activity. However, wolves had no real-time way to interrupt that puzzle work — they could only observe and vote to kill at night's end.

This PRD adds a second wolf-team kill path: a cooperative **charge attack** where wolves hold down on a quadrant for a combined 5000 ms to instantly disrupt all active solvers in that quadrant and mark one for elimination at night resolution. One wolf kill per night is enforced: if the charge fires, it takes priority over the traditional kill vote.

---

## 2. Rules Execution

### §2.1 Charge Mechanic — Pool-Based Auto-Fire

Each wolf sends periodic `wolf_charge_update` intents reporting their `accumulated_ms` for a quadrant. The server stores these in `NightActions.wolf_charges[wolf_pid][quadrant]`.

**Auto-fire condition:**
```
pack_total(quadrant) = sum(wolf_charges[pid][quadrant] for all alive wolves)
When pack_total >= CHARGE_THRESHOLD_MS (5000 ms):
  → _apply_charge_fire() runs:
     1. charge_kill_target_id = first active solver in that quadrant (if any)
     2. All active solvers' grid puzzles are disrupted (active=False, solved=False)
     3. All wolves' accumulated_ms for that quadrant reset to 0
```

There is no `wolf_charge_fire` client intent — the server determines fire timing authoritatively. Clients track local progress for UI only.

### §2.2 Single Wolf vs. Multiple Wolves

| Configuration | Threshold per wolf | Cooperation |
|---|---|---|
| 1 wolf | 5000 ms alone | — |
| 2 wolves | ~2500 ms each (combined 5000 ms) | Both must focus the same quadrant |
| 3+ wolves | ~1667 ms each (combined 5000 ms) | Faster; 1 wolf can charge while others vote |

**Key risk for 2 wolves (strict majority = 2 votes required):**
- If 1 wolf charges and 1 wolf votes → 1 vote ≤ 50% = no vote kill AND the charge needs 5000 ms alone
- Both wolves must coordinate: both vote, or both charge the same quadrant

### §2.3 One-Kill-Per-Night Rule

`charge_kill_target_id` takes priority over `wolf_votes` at night resolution (`_step7_wolf_kill_or_infect`):

1. If `charge_kill_target_id` is set → charge kill runs first (with full protection checks); vote kill is skipped
2. If `charge_kill_target_id` is `None` → standard vote kill proceeds

This ensures at most one wolf-team kill per night regardless of which path fires.

### §2.4 Villager Defend

A villager with `under_attack = True` may press Defend:

- Clears `under_attack` for that player
- Resets **all wolves'** `accumulated_ms` for the defender's quadrant to 0
- The entire pack must restart from zero — one villager's action breaks collective wolf effort

`under_attack` is set `True` when any wolf sends `is_active=True` for the villager's quadrant, and cleared when the wolf releases (`is_active=False`), the charge fires, or the villager defends.

### §2.5 Protection Rules

Charge kill runs through the same protection sequence as vote kill:

1. **Wise shield** — one-use deflection (disabled if `village_powers_cursed`)
2. **Doctor protection** — `is_protected = True` from this night's Doctor action
3. **Bodyguard 50/50** — if Bodyguard is guarding the charge target: 50% attacker dies / 50% Bodyguard dies; target always survives
4. **Serial Killer immunity** — SK cannot be killed by wolf-team attacks

If the target is protected, `charge_kill_target_id` is consumed (cleared) but no kill is logged.

---

## 3. Payload Schemas

### `wolf_charge_update` intent (client → server)
```json
{
  "type": "wolf_charge_update",
  "player_id": "<wolf_pid>",
  "quadrant": "top_left" | "top_right" | "bottom_left" | "bottom_right",
  "accumulated_ms": 2500,
  "is_active": true
}
```
`accumulated_ms` is this wolf's cumulative hold time (client-tracked). `is_active` distinguishes active hold (sets `under_attack`) from a pause/release (clears `under_attack`).

### `grid_defend` intent (client → server)
```json
{
  "type": "grid_defend",
  "player_id": "<villager_pid>"
}
```
No parameters beyond player identity. Server determines which quadrant to defend from `grid_node_row`/`grid_node_col`.

---

## 4. Client–Server Specifications

| Responsibility | Server | Mobile Client |
|---|---|---|
| Fire timing | Authoritative — fires when `pack_total >= 5000 ms` | Tracks local progress for visual UI only |
| `under_attack` | Sets/clears on each `wolf_charge_update`; never sent to wolves | Displays `AttackWarningOverlay` when own player's `under_attack == True` |
| Puzzle disruption | Immediate on fire — `grid_puzzle_state.active = False` | Clears active puzzle UI |
| Kill resolution | `charge_kill_target_id` consumed by `resolve_night()` at night end | No special handling — standard elimination broadcast |

---

## 5. Phase-Gate Plan

| Phase | Deliverable | Status |
|---|---|---|
| 1 | `EliminationCause.GRID_CHARGE_KILL`, `NightActions.charge_kill_target_id`, stripper update | ✅ |
| 2 | `handle_wolf_charge_update` auto-fire via `_apply_charge_fire()` | ✅ |
| 3 | `handle_grid_defend` resets all wolves' charges for quadrant | ✅ |
| 4 | `_step7_wolf_kill_or_infect` charge kill priority + `_apply_wolf_kill` helper | ✅ |
| 5 | Remove `wolf_charge_fire` from dispatch | ✅ |
| 6 | `TestWolfChargeKill` (7 tests) | ✅ |

---

## 6. User Stories

| As a | I want to | So that |
|---|---|---|
| Mobile Player (Wolf) | hold my finger on a quadrant and see a charge meter fill | I can kill a villager without needing my packmates to vote |
| Mobile Player (Wolf) | cooperate with another wolf to fill the charge meter faster | I can kill in fewer seconds if we coordinate |
| Mobile Player (Villager) | see an attack warning when wolves are charging my quadrant | I know to press Defend before the charge fires |
| Mobile Player (Villager) | press Defend to break the wolves' charge | I can neutralize an attack in progress and buy my team more puzzle time |
| Game Server | enforce one wolf-team kill per night | charge and vote paths cannot stack kills in the same round |

---

## 7. Open Questions

1. Should the Tracker track a wolf who fired a charge (analogous to tracking a wolf who voted)? Currently charge attacks do not register in `wolf_visits` for Tracker purposes.
2. Should the `non_wolf_kill` hint fire if the charge kill target was protected by the Doctor? Currently: no kill → no hint either way.
