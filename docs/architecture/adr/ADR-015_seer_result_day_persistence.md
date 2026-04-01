# ADR-015: Surface Seer Result in Day Discussion Screen

## Status
Accepted

## Date
2026-03-29

## Context

The Seer submits an investigation target during the NIGHT phase. The backend resolves the result in `_step6_seer` (resolver/night.py) and sets two fields on the seer's stripped state:

- `night_actions.seer_result` — the current-round result (`"village"` | `"wolf"` | `"neutral"`)
- `night_actions.seer_target_id` — who was investigated
- `seer_knowledge` — cumulative map of all prior investigations (persists through end of game)

The auto-advance path in `handlers.py:257-265` sends **two consecutive WebSocket broadcasts**:

1. Intermediate NIGHT broadcast (`phase=night`, `seer_result` set) — fires immediately after `resolve_night()`
2. DAY broadcast (`phase=day`, `seer_result` still set) — fires after `transition_phase(Phase.DAY)` within the same game queue task

Both broadcasts carry `seer_result` in the seer's stripped state (confirmed by integration test `test_seer_result_in_seer_ws_view`). The field is **not cleared** when transitioning from NIGHT to DAY — `night_actions` is only reset on the next NIGHT entry.

**The bug:** `App.tsx` routes `phase=night` → `NightActionShell` and `phase=day` → `DayDiscussionScreen`. `SeerPeekUI` (inside `NightActionShell`) renders the result only while mounted. `DayDiscussionScreen` did not render the seer's investigation result at all. The seer had no persistent display of their intel during the day discussion phase, which is the exact moment the intel has strategic value.

The intermediate NIGHT render lasts approximately one React render cycle (~16ms) before the DAY broadcast arrives and unmounts `SeerPeekUI`. On slower devices or under load this window may be imperceptibly brief, making the result effectively invisible.

### Alternatives Considered

**A — Rely on intermediate NIGHT broadcast only (status quo)**

The result is technically delivered. However, the display window is too brief to be actionable and is not guaranteed to render at all on slower clients. Rejected.

**B — Add a cross-phase `lastSeerResult` state in `App.tsx`, passed to `DayDiscussionScreen`**

Captures the result during the NIGHT render and passes it across the phase transition. Works, but requires App.tsx to manage per-role state that belongs at the display layer, and introduces a separate state variable that must be cleared at the right time. Rejected.

**C — Read from `seer_knowledge` in `DayDiscussionScreen` (selected)**

`seer_knowledge` is already present in the seer's stripped DAY state and contains the full cumulative record. No intermediate state needed. The DAY screen reads directly from the authoritative server field. Simple, correct, and no new state management required.

---

## Decision

`DayDiscussionScreen` was updated to render a `SeerIntelPanel` component when `myPlayer.role === 'seer'`. The panel reads from `gameState.seer_knowledge` — the cumulative map of all investigations — and renders each entry color-coded by result type. The panel is only mounted when `seer_knowledge` has entries or `gameState.night_actions.seer_result` is set, so it does not appear for seers who have not yet investigated anyone.

**Files changed:**
- `frontend-mobile/src/components/DayDiscussionScreen/DayDiscussionScreen.tsx` — added `isSeer` detection and `SeerIntelPanel` component
- `frontend-mobile/src/components/DayDiscussionScreen/DayDiscussionScreen.css` — added seer panel styles

No backend changes were required. The server already sends the correct data.

---

## Consequences

**Positive:**
- Seer can see all investigation results accumulated to date during the day discussion, where the intel is most useful for coordinating a vote.
- Reading from `seer_knowledge` (not a local copy) means the display is always consistent with the server's authoritative state — no risk of showing a stale result from a previous round.
- No new WebSocket messages, no new state fields, no new backend logic.

**Negative:**
- `DayDiscussionScreen` now has role-aware branching. The seer panel is conditional; non-seer players see no difference.
- The intermediate NIGHT broadcast still delivers `seer_result` to `SeerPeekUI` for the brief window it is mounted. Both paths are now functionally redundant for the DAY phase — `SeerPeekUI` for in-night feedback, `SeerIntelPanel` for the day discussion. This duplication is intentional and acceptable.

---

## Related

- ADR-003: Client-Side Storage Strategy (sessionStorage for seer history in `SeerPeekUI`)
- PRD-007: Night Phase UX (seer result delivery + villager puzzle feedback)
- `backend-engine/engine/resolver/night.py` — `_step6_seer` sets `seer_result` and appends to `seer_knowledge`
- `backend-engine/engine/stripper.py:172-184` — `_seer_view` injects `seer_result` into night_actions
- `backend-engine/tests/engine/test_seer_result_in_seer_ws_view` — integration test confirming DAY-phase delivery
