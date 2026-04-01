# PRD-007: Night Phase UX — Seer Result Delivery & Villager Puzzle Feedback

## §1. Context & Problem

### §1.1 Overview

Two related UX failures were identified in the night phase:

1. **Seer result delivery** — The seer submits an investigation, the backend resolves it correctly, but the result is not reliably visible during the day discussion phase where it has the most strategic value.
2. **Villager puzzle interaction** — Villagers (and Mayor/Jester) who solve Archive puzzles to earn clues received no visual feedback after tapping an answer. Buttons remained enabled after submission, and any server-side rejection (WRONG_PHASE, PUZZLE_NOT_ACTIVE) was silently discarded.

Both bugs were confirmed in production-equivalent integration testing. All 265 existing unit tests passed — these are runtime/integration-layer failures not covered by the existing test suite.

### §1.2 Bug 1: Seer Result Not Visible During Day Discussion

**Observed behavior:** Seer investigates a player during night. All required roles submit → auto-advance fires. Seer sees the result briefly in `SeerPeekUI` (mounted during NIGHT phase), then the screen transitions to day discussion. No result is shown during the discussion phase.

**Root cause:** `App.tsx` routes `phase=night` → `NightActionShell` (which contains `SeerPeekUI`) and `phase=day` → `DayDiscussionScreen`. The auto-advance path in `handlers.py:257-265` sends two consecutive WebSocket broadcasts within the same game queue task:

```
resolve_night()          → seer_result set
broadcast(G)             → intermediate NIGHT broadcast (~16ms render window)
transition_phase(DAY)    → seer_result still present in stripped state
broadcast(G)             → DAY broadcast (confirmed by test_seer_result_in_seer_ws_view)
```

`SeerPeekUI` is unmounted when the DAY broadcast arrives. `DayDiscussionScreen` did not display the result. The seer had no reference to their intel during the exact phase where they need to act on it.

**Backend status:** Correct. `seer_result` and `seer_knowledge` are present in the seer's stripped DAY state. No backend changes required.

### §1.3 Bug 2: Villager Puzzle Provides No Feedback

**Observed behavior:** Villager sees an Archive puzzle (math or sequence type). Taps an answer. Nothing visually changes. Puzzle panel stays in its active state indefinitely or until night ends.

**Root causes (three compounding):**

| # | Cause | Location |
|---|-------|----------|
| A | Silent error handling — all server errors logged only to `console.warn` | `useGameState.ts:38-40` |
| B | WRONG_PHASE race condition — if the last required role submits just before the villager, night ends while the villager's intent is queued | `handlers.py:325` `_require_phase(G, Phase.NIGHT)` |
| C | No `disabled` attribute on puzzle buttons — double-taps or post-submit taps send duplicate intents | `VillagerDecoyUI.tsx:124-133` |

**Backend status:** Correct. `handle_submit_puzzle_answer` validates phase, calls `resolve_puzzle_answer`, delivers hint unicast. `player_id` is injected by the WS endpoint so client omission is not a factor.

---

## §2. System Behavior

### §2.1 Seer Result Delivery — Data Flow

```
NIGHT phase:
  Seer submits intent → submit_night_action (seer_target_id)
  resolve_night() → seer_result set, seer_knowledge updated
  broadcast(G, phase=night) → SeerPeekUI renders result (brief window)
  transition_phase(DAY)
  broadcast(G, phase=day)  → DayDiscussionScreen mounts

Seer's stripped DAY state (authoritative fields):
  gameState.night_actions.seer_result     = "wolf" | "village" | "neutral"
  gameState.night_actions.seer_target_id  = "<player_id>"
  gameState.seer_knowledge                = { "<player_id>": "wolf" | "village" | "neutral", ... }
```

`seer_knowledge` accumulates across all rounds and is never cleared until game over. It is the persistent record of all investigations.

### §2.2 Puzzle System — Data Flow

```
NIGHT phase (wakeOrder==0 players only):
  machine.py:92-102 → generate_night_puzzle(G, pid) for each alive wakeOrder==0 player
  puzzle_state set on PlayerState (not NightActions)
  stripper.py:317-346 → _strip_puzzle_for_player strips correct_index, sends to client

Client submits answer:
  sendIntent({ type: 'submit_puzzle_answer', answer_index: N })
  OR
  sendIntent({ type: 'submit_puzzle_answer', answer_sequence: [...] })

Server:
  dispatch.py → handle_submit_puzzle_answer
  validates phase=NIGHT, validates puzzle.active, calls resolve_puzzle_answer
  delivers hint unicast (individual player only) before state broadcast
  puzzle_state.active = false, puzzle_state.solved = true/false
```

### §2.3 Puzzle Types

| Type | `puzzle_type` value | Answer field | Data shape |
|------|--------------------|--------------|----|
| Multiple choice (logic/math) | `"choice"` | `answer_index: number` | `{ question?: string, expression?: string, answer_options: string[] }` |
| Simon Says (sequence) | `"sequence"` | `answer_sequence: string[]` | `{ sequence: string[] }` — colors: `"red"` \| `"blue"` \| `"green"` \| `"yellow"` |

---

## §3. Client-Server Contract

### §3.1 Intent Payloads

```json
// Multiple-choice answer
{ "type": "submit_puzzle_answer", "answer_index": 2 }

// Sequence answer
{ "type": "submit_puzzle_answer", "answer_sequence": ["red", "blue", "green"] }
```

`player_id` is injected by the WS endpoint (`endpoint.py:136-137`) and must not be included by the client.

### §3.2 Server Error Codes (puzzle)

| Code | Trigger | Client behavior |
|------|---------|-----------------|
| `WRONG_PHASE` | Intent received after night ended (race) | Unlock buttons; show "Night ended — no clue" |
| `PUZZLE_NOT_ACTIVE` | Answer submitted after puzzle already resolved | Unlock buttons silently |
| `NO_PUZZLE_ACTIVE` | Player has no puzzle (should not occur for wakeOrder==0) | Unlock buttons |
| `PUZZLE_DATA_ERROR` | Server-side puzzle generation failure | Unlock buttons; show generic error |

### §3.3 Hint Delivery

The hint is delivered as a unicast message to the puzzle solver before the full state broadcast. The `latestHint` prop in `NightActionShell` carries the most recently received hint payload. `VillagerDecoyUI` reads `latestHint` to display the clue in the `ResolvedPuzzle` view.

---

## §4. Requirements

### §4.1 Seer Result — Functional Requirements

| ID | Requirement |
|----|-------------|
| F-1 | During the DAY discussion phase, the seer sees all investigation results accumulated to date (current round + all prior rounds). |
| F-2 | Results are shown color-coded: wolf = red, not wolf = green, neutral = amber. |
| F-3 | The panel is only visible to the seer; all other roles see no difference in `DayDiscussionScreen`. |
| F-4 | The panel reads from `gameState.seer_knowledge` (server-authoritative, persists through DAY phase). It does not depend on the brief intermediate NIGHT broadcast. |

### §4.2 Villager Puzzle — Functional Requirements

| ID | Requirement |
|----|-------------|
| F-5 | After tapping a choice answer or completing a sequence, all puzzle interaction elements are immediately disabled. The player receives visual confirmation that their answer was registered. |
| F-6 | If the server rejects the answer (WRONG_PHASE, PUZZLE_NOT_ACTIVE, timeout), buttons re-enable after a 4-second fallback window so the player can retry. |
| F-7 | The existing `ResolvedPuzzle` view (showing the hint or "No clue this round") is reached normally when `puzzle_state.active` becomes false via the state broadcast. |
| F-8 | The sequence puzzle disables tiles while the flash sequence is playing (`showing=true`) and after the player completes input (`locked=true`). |

### §4.3 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NF-1 | No backend changes. Both fixes are frontend-only. |
| NF-2 | No new WebSocket message types. |
| NF-3 | The `locked` / `disabled` state in puzzle components must not persist across puzzle re-renders triggered by new `puzzle_state` from the server. |

### §4.4 Anti-Scope

- Not implementing a full toast/notification system for WS errors — the fallback unlock after 4s is sufficient for the WRONG_PHASE race condition.
- Not showing the seer result during the NIGHT phase in a new location — `SeerPeekUI` already handles this.
- Not changing `seer_knowledge` retention behavior — server controls this.
- Not adding error boundaries around puzzle components.

---

## §5. User Stories

| As a | I want to | So that |
|------|-----------|---------|
| Mobile Player (Seer) | see my investigation result clearly during the day discussion phase | I can tell my team who to vote for without having to recall a flash of text from the night transition |
| Mobile Player (Seer) | see all investigation results from previous rounds in one panel | I can reference my accumulated intel without relying on memory |
| Mobile Player (Villager / Mayor / Jester) | have puzzle answer buttons disable immediately after I tap one | I know my answer was registered and I won't accidentally submit twice |
| Mobile Player (Villager / Mayor / Jester) | see the buttons re-enable if the server didn't accept my answer | I can retry without refreshing the page |
| Mobile Player (Villager / Mayor / Jester) | see the sequence puzzle tiles disabled while the flash is playing | I cannot accidentally start inputting before I've seen the full sequence |

---

## §6. Acceptance Criteria

```gherkin
Feature: Seer result visible in day discussion

  Scenario: Seer investigates wolf during night, result shown in day
    Given a 5-player game with seer, wolf, doctor, and 2 villagers
    And the seer submits an investigation targeting the wolf
    And all required roles (wolf, doctor) submit their night actions
    When the night auto-advances to day
    Then DayDiscussionScreen shows a panel labeled "Your Intel"
    And the panel contains "[Wolf player name] — WOLF" in red
    And the panel is not visible to any non-seer player

  Scenario: Seer sees cumulative history across rounds
    Given the seer investigated "Alice" (village) in round 1
    And the seer investigated "Bob" (wolf) in round 2
    When the day discussion screen loads in round 2
    Then the Intel panel shows both entries
    And "Alice" is shown in green ("Not Wolf")
    And "Bob" is shown in red ("WOLF")

Feature: Villager puzzle button locking

  Scenario: Choice puzzle — button disables after tap
    Given a villager is presented with a multiple-choice Archive puzzle
    When the villager taps answer option B
    Then all four answer buttons are immediately disabled
    And no second submit_puzzle_answer intent is sent on further taps

  Scenario: Choice puzzle — button re-enables after timeout (WRONG_PHASE race)
    Given a villager taps an answer at the same moment night ends
    And the server returns WRONG_PHASE
    When 4 seconds elapse
    Then the answer buttons are re-enabled

  Scenario: Sequence puzzle — tiles disabled during flash
    Given a villager's sequence puzzle is in the "showing" state
    Then all sequence tiles are disabled
    When the flash sequence completes
    Then the tiles become enabled for player input

  Scenario: Sequence puzzle — locks after full sequence input
    Given a villager completes the full tile sequence
    Then all tiles are immediately disabled
    And the submit_puzzle_answer intent is sent with the full sequence
```

---

## §7. Phase-Gate Plan

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 1 — Seer result in day | Add `SeerIntelPanel` to `DayDiscussionScreen`; read from `seer_knowledge` | **Done** (2026-03-29) |
| 2 — Puzzle button locking | Add `locked` state + 4s fallback to `ChoicePuzzle` and `SequencePuzzle` in `VillagerDecoyUI` | **Done** (2026-03-29) |
| 3 — Documentation | ADR-015, PRD-007, data dictionary update | **Done** (2026-03-29) |

---

## §8. Open Questions

| # | Question | Owner |
|---|----------|-------|
| 1 | Should the seer panel in `DayDiscussionScreen` also include the current-round target name (from `night_actions.seer_target_id`), or is `seer_knowledge` sufficient? Currently `seer_knowledge` is used; `seer_target_id` is available if a "Round N: ..." label is desired. | Engineering |
| 2 | Should WS error codes be surfaced as visible toast messages (not just console.warn)? The 4s fallback covers the most common case (WRONG_PHASE), but PUZZLE_DATA_ERROR gives no visible feedback. | Engineering |

---

## §9. Related

- ADR-015: Seer Result Day Persistence (decision record for this fix)
- ADR-003: Client-Side Storage Strategy (§9 — seer peek history in sessionStorage)
- ADR-008: Archive Puzzle System (puzzle_state on PlayerState, puzzle types)
- `docs/architecture/data_dictionary.md` — `seer_result`, `seer_knowledge`, `puzzle_state` field definitions
