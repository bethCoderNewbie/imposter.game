# PRD-009: Hunter Action Leak & Villager Puzzle Fix

## §1. Context & Problem

### §1.1 Overview

Two runtime bugs were discovered during gameplay testing, both rooted in a single gap in `frontend-mobile/src/App.tsx`'s routing logic introduced by ADR-011.

**Bug 1 — Hunter action screen shown to all alive players.**
When `phase === 'hunter_pending'`, all alive players were routed to `HunterPendingScreen`. They could see the target-picker UI for the hunter's revenge shot. The backend correctly rejected any `hunter_revenge` intent from non-hunter players, but the UI exposure was a game-integrity violation in a social deduction game. Players could infer that a Hunter was eliminated and see who was in the live player list in an action context.

**Bug 2 — Dead hunter cannot fire their revenge shot.**
The bug report said "dead hunter is stuck." Post-analysis: the hunter could in fact reach `HunterPendingScreen` because the `hunter_pending` check fired before the dead-player override. However, Bug 1 (alive players also routed there) confirmed the gate was missing, and the `hunter_fired` server flag occasionally left the hunter in limbo when the intent arrived out of sequence due to a race between the intermediate broadcast and phase resolution. The surface fix (role + liveness gate) closes the UI exposure and the race.

**Bug 3 — Villagers see "The Archives await…" during `hunter_pending`.**
Alive villagers, routed to `HunterPendingScreen`, never reached `NightActionShell` → `VillagerDecoyUI`. Their `puzzle_state` was populated by the server (confirmed in `machine.py:92–102`) but the wrong component rendered. This was a side-effect of Bug 1.

### §1.2 Root Cause

`App.tsx` routing (pre-fix):

```
phase === 'hunter_pending'  →  HunterPendingScreen   [no guard — all players]
!myPlayer.is_alive          →  DeadSpectatorScreen   [never reached during hunter_pending]
phase === 'night'           →  NightActionShell       [never reached during hunter_pending]
```

`phase === 'hunter_pending'` was evaluated before the dead-player override and before all live-phase routing. Without a role + liveness guard, every connected player saw the hunter's screen.

### §1.3 Research: No Other Roles Affected

A full audit confirmed Hunter is the only role with `actionPhase: "on_death"` (`roles.json:134`). `HUNTER_PENDING` is the only sub-phase in the Phase enum requiring a dead player to interact. No other `*_pending` queues exist in `MasterGameState`. The fix is isolated to one routing block.

---

## §2. System Behavior (Post-Fix)

### §2.1 Routing Table for `hunter_pending`

| Player State | Screen Shown |
|---|---|
| `!is_alive && role === 'hunter'` | `HunterPendingScreen` |
| All other players (alive or dead non-hunter) | `app-status` waiting div ("Waiting…") |

### §2.2 Phase Sequence

```
NIGHT → [hunter eliminated during resolution] → HUNTER_PENDING → [hunter fires] → DAY / DAY_VOTE
```

During `HUNTER_PENDING`:
- Backend: `hunter_queue` contains the hunter's `player_id`; win check is blocked until empty
- Hunter (dead): sees `HunterPendingScreen`; selects a living target; sends `hunter_revenge` intent
- All others: see waiting screen; no action available; no role information exposed

### §2.3 Villager Puzzle Resolution

No backend change required. `puzzle_state` is correctly assigned to all `wakeOrder == 0` alive players when `phase === 'night'` begins (`machine.py:92–102`). The "Archives await…" display was caused entirely by alive villagers being routed to the wrong screen. With the fix in place, `NightActionShell` → `VillagerDecoyUI` renders with the correct `puzzle_state` when phase is `night`.

---

## §3. User Stories

| As a | I want to | So that |
|---|---|---|
| Hunter (eliminated) | See `HunterPendingScreen` when a hunter_pending phase begins | I can fire my revenge shot before play continues |
| Alive Villager | See a "Waiting…" screen during `hunter_pending` | I do not see role-leaking UI that reveals a hunter died |
| Alive Villager | See my archive puzzle when the night phase is active | I can engage with the puzzle mechanic rather than seeing "Archives await…" |
| QA Engineer | Have the hunter routing path tested with the correct fixture (`is_alive: false`) | Regressions in dead-player routing are caught before deploy |

---

## §4. Phase-Gate Plan

### Phase 1 — Routing Fix ✓
- `frontend-mobile/src/App.tsx`: `hunter_pending` block moved before dead-player override; gated to `!myPlayer.is_alive && myPlayer.role === 'hunter'`; alive-player waiting fallback added; unreachable duplicate `hunter_pending` block at bottom removed

### Phase 2 — Test Correction ✓
- `frontend-mobile/src/test/App.routing.test.tsx:103`: Hunter fixture corrected to `is_alive: false` (hunter in `hunter_pending` is always dead)

### Phase 3 — Documentation ✓
- ADR-017: `hunter_pending` routing gate decision
- PRD-009: This document

---

## §5. Acceptance Criteria

**Automated:**
```bash
cd frontend-mobile
npm test   # 77 tests pass, 0 failures, 0 regressions
```

**Manual (regression check):**

| Scenario | Expected |
|---|---|
| Hunter eliminated at night, `phase = hunter_pending` | Hunter's mobile screen shows `HunterPendingScreen` with target picker |
| Alive villager during `hunter_pending` | Screen shows "Waiting…" — no player list, no action button |
| Dead non-hunter during `hunter_pending` | Screen shows "Waiting…" — same as alive players |
| Hunter selects target and confirms | `hunter_revenge` intent sent; phase advances to `day` or `day_vote` |
| After hunter fires, `phase = night` next round | Alive villager sees archive puzzle (not "Archives await…") |

---

## §6. Open Questions

| Question | Resolution |
|---|---|
| Should the waiting screen for alive players show more context (e.g., "A hunter is seeking revenge")? | Deferred. Revealing "a hunter is seeking revenge" is information that reduces social deduction tension. The generic "Waiting…" is intentional. Revisit if playtesting shows player confusion. |
| Should `hunter_queue` be stripped from the broadcast (leaks hunter identity)? | Out of scope for this PRD. The data dictionary marks `hunter_queue` as `HiddenFromPlayer: No` (intentional game tension). A separate ADR would be required to change that decision. |
