# PRD-014: Werewolf — Host Authoritative Game Control (Timer Pause · Phase Skip · Force Next)

## §1. Context & Problem

**REQ — Host Runtime Authority:**
The host is the game master. Today their in-game power is limited to a single intent: `advance_phase` (DAY → DAY_VOTE only, `handlers.py:434–448`). Every other timer — NIGHT, ROLE_DEAL, DAY_VOTE, and HUNTER_PENDING — runs autonomously with no escape hatch. This creates two failure modes:

1. **Stuck phases.** A player disconnects mid-NIGHT or mid-VOTE; the timer must expire naturally even though the game is broken.
2. **Pacing problems.** Players resolve a NIGHT discussion in 20 seconds but must wait 40 more. Or a conversation runs long and the host can't grant extra time.

**Current state (verified by research, 2026-04-15):**
- `advance_phase` → host-only, DAY phase only, hard-gated by `_require_phase(G, Phase.DAY)` at `handlers.py:437`.
- No `pause_timer`, `resume_timer`, `extend_timer`, or `force_next` intent exists.
- `cancel_phase_timer()` (`timer_tasks.py:53–58`) exists internally but is never callable by a client.
- Timer config (`PATCH /api/games/{id}/config`) is LOBBY-only; it cannot override a live countdown.
- No host control UI exists in either frontend during active gameplay.

**Desired end state:**
The host (Display client holding `host_secret`) can, at any point during an active game:
- **Pause** the running phase timer (freezes countdown).
- **Resume** a paused timer (restarts countdown from remaining time).
- **Extend** the current phase by a fixed increment (+30 s) without leaving the phase.
- **Force-next** — immediately end any phase and advance, equivalent to "timer expired now". Works for NIGHT, DAY, DAY_VOTE, and HUNTER_PENDING (the four phases currently unreachable by the host).

All four actions require the player to be the host. All four are no-ops if the game is not in an active phase (i.e. LOBBY, GAME_OVER).

---

## §2. Rules Execution

### §2.1 Intent Definitions and Phase Gates

| Intent | Allowed Phases | Effect | Timer After |
|---|---|---|---|
| `pause_timer` | NIGHT, ROLE_DEAL, DAY, DAY_VOTE, HUNTER_PENDING | Freeze timer; store remaining seconds in state | Cancelled (no active task) |
| `resume_timer` | Same as above — only if currently paused | Restart countdown from remaining seconds | New task for `remaining_seconds` |
| `extend_timer` | Same as above | Add `EXTEND_INCREMENT` (30 s) to deadline; or to remaining if paused | Updated; re-starts if was paused |
| `force_next` | NIGHT, ROLE_DEAL, DAY_VOTE, HUNTER_PENDING | Immediately invoke the phase_timeout resolution path | Cancelled |

**`advance_phase` (existing, DAY only)** is NOT replaced — it stays as-is. `force_next` covers the other four phases.

**Pause/resume are mutually exclusive:** sending `pause_timer` while already paused returns `ALREADY_PAUSED`. Sending `resume_timer` while not paused returns `NOT_PAUSED`.

**Extend while paused:** adds 30 s to `remaining_seconds` in state (no active timer to touch). The next `resume_timer` starts from the new extended remaining.

**`force_next` in DAY phase:** not needed — `advance_phase` already handles DAY → DAY_VOTE. `force_next` in DAY is rejected with `USE_ADVANCE_PHASE`.

---

### §2.2 State Changes

Add two fields to `MasterGameState` (`engine/state/models.py`):

| Field | Type | Description |
|---|---|---|
| `timer_paused` | `bool` | `True` when the host has paused the current phase timer. Default `False`. |
| `timer_remaining_seconds` | `int \| None` | Seconds remaining at pause time. `None` when not paused. |

Both fields reset to `False` / `None` on every phase transition (inside `transition_phase()`, `machine.py`).

---

### §2.3 Resolution Path for `force_next`

`force_next` does not re-implement phase logic. It calls `cancel_phase_timer()` then enqueues a synthetic `phase_timeout` intent directly into the game queue (same path as the real timer task, `timer_tasks.py:41`). This guarantees a single code path for phase resolution regardless of whether the timer expired naturally or was forced.

---

### §2.4 Visibility

| State field | Display (host) | Display (spectator) | Mobile |
|---|---|---|---|
| `timer_paused` | Shows "PAUSED" overlay on countdown | Shows "PAUSED" overlay | Shows "PAUSED" badge on timer |
| `timer_remaining_seconds` | Countdown freezes at remaining value | Frozen | Frozen |
| Host control buttons | Visible (pause/resume/extend/force-next) | Hidden | Hidden |

`timer_paused` and `timer_remaining_seconds` are **not** stripped by the state stripper — they are public game state, safe for all clients.

---

## §3. Payload Schema

### §3.1 New WebSocket Intents (client → server)

All four intents share the same shape. `state_id` is required (state_id fence is enforced):

```json
{ "type": "pause_timer",  "player_id": "<uuid>", "state_id": 42 }
{ "type": "resume_timer", "player_id": "<uuid>", "state_id": 43 }
{ "type": "extend_timer", "player_id": "<uuid>", "state_id": 44 }
{ "type": "force_next",   "player_id": "<uuid>", "state_id": 45 }
```

### §3.2 Error Codes

| Code | Trigger |
|---|---|
| `NOT_HOST` | Sending player is not `G.host_player_id` |
| `WRONG_PHASE` | Intent not valid in current phase |
| `ALREADY_PAUSED` | `pause_timer` sent while `G.timer_paused == True` |
| `NOT_PAUSED` | `resume_timer` sent while `G.timer_paused == False` |
| `USE_ADVANCE_PHASE` | `force_next` sent during DAY phase |

### §3.3 MasterGameState Delta (broadcast on every host action)

```json
{
  "type": "update",
  "state_id": 43,
  "state": {
    "phase": "night",
    "timer_ends_at": null,
    "timer_paused": true,
    "timer_remaining_seconds": 38,
    ...
  }
}
```

`timer_ends_at` is set to `null` while paused. On resume it is recalculated as `now + timer_remaining_seconds`.

---

## §4. Client-Server Specifications

### §4.1 Backend Changes

| File | Change |
|---|---|
| `engine/state/models.py` | Add `timer_paused: bool = False` and `timer_remaining_seconds: int \| None = None` to `MasterGameState` |
| `engine/phases/machine.py` | Reset both fields in `transition_phase()` |
| `api/intents/handlers.py` | Add `handle_pause_timer`, `handle_resume_timer`, `handle_extend_timer`, `handle_force_next` |
| `api/intents/dispatch.py` | Register four new intent type → handler mappings |
| `api/timer_tasks.py` | No changes — existing `cancel_phase_timer()` and `start_phase_timer()` are reused as-is |

**`EXTEND_INCREMENT`** constant: `30` seconds, defined at top of `handlers.py`.

### §4.2 Display Frontend Changes

| File | Change |
|---|---|
| `frontend-display/src/components/PhaseTimer/PhaseTimer.tsx` | Add "PAUSED" overlay when `state.timer_paused == true`; freeze displayed time at `timer_remaining_seconds` |
| `frontend-display/src/components/HostControls/` | New component: host-only control bar rendered during active phases |
| `frontend-display/src/hooks/useGameState.ts` | No changes — `timer_paused` and `timer_remaining_seconds` arrive in state already |

**`HostControls` component renders (host only, active phases only):**
- Pause / Resume button (toggles based on `state.timer_paused`)
- +30s Extend button
- Force Next button (hidden in DAY phase — `advance_phase` button handles that)

All buttons send the corresponding WebSocket intent with current `state_id`.

### §4.3 Mobile Frontend Changes

| File | Change |
|---|---|
| `frontend-mobile/src/components/*/` | Add "PAUSED" badge to any visible timer display |

No action buttons on mobile — host controls are display-only.

---

## §5. Phase-Gate Plan

| Phase | Deliverable | Acceptance |
|---|---|---|
| **P0** | Backend: state fields + 4 handlers + dispatch wiring | `pytest tests/api/test_host_controls.py` passes |
| **P1** | Display: HostControls component + paused overlay on PhaseTimer | Manual: pause → countdown freezes on all clients |
| **P2** | Mobile: PAUSED badge on timer | Manual: paused state visible on player phones |

---

## §6. User Stories

| As a | I want to | So that |
|---|---|---|
| `Host` | Pause the night timer | I can address a disconnected player without the wolf kill auto-resolving |
| `Host` | Resume the night timer after pausing | The game continues from where it left off |
| `Host` | Extend the current phase by 30 seconds | Players who need more time get it without leaving the phase |
| `Host` | Force the current phase to end immediately | I can unstick a phase where all players are ready but the timer hasn't expired |
| `Display Client` | See a "PAUSED" overlay on the countdown | The room knows the game is intentionally frozen |
| `Mobile Player` | See a "PAUSED" badge on my timer | I know the host paused, not that I lost connection |

---

## §7. Open Questions

1. **Pause in ROLE_DEAL?** Players individually confirm; the phase auto-advances when all confirm. A pause would still allow confirmations to come in. Should `pause_timer` block the auto-advance as well, or only freeze the countdown?
2. **Force-next in HUNTER_PENDING?** If the hunter hasn't fired and the host force-nexts, does the hunter's revenge simply not fire (hunter dies without a kill), or should it be disallowed?
3. **Extend cap?** Is there a maximum number of extend actions per phase, or is it unlimited?
4. **Paused state persistence across disconnect?** If the host disconnects while timer is paused, does the pause hold until they reconnect, or does resume fire automatically after a grace period?
