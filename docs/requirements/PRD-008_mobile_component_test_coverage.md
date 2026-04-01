# PRD-008: Mobile Component Test Coverage — PlayerAvatar, DayDiscussionScreen, VillagerDecoyUI

## §1. Context & Problem

### §1.1 Overview

A component audit of `frontend-mobile/src/components/` revealed that 12 of 18 components have zero automated test coverage. Three components were identified as highest-priority based on two criteria:

1. **Blast radius** — `PlayerAvatar` is the most-used UI primitive (rendered in all 14 screen components). Regressions in sizing, color mapping, or accessible labeling affect every screen.
2. **Recent modification** — `DayDiscussionScreen` and `VillagerDecoyUI` were both modified as part of PRD-007 (night phase UX fixes). Untested recently-changed code is a reliability liability.

Additionally, the audit surfaced a dead prop in `VillagerDecoyUI` (`gameState` declared in the `Props` interface but never destructured) and a missing accessibility attribute on `PlayerAvatar` (no `aria-label`, violating WCAG 1.1.1). Both were corrected as part of this work.

### §1.2 Test Gap Detail

| Component | Change Risk | Root Reason Untested |
|---|---|---|
| `PlayerAvatar` | High (14 render sites) | Original implementation predates test infrastructure |
| `DayDiscussionScreen` | High (modified in PRD-007) | Added in same sprint as ADR-015 seer panel work |
| `VillagerDecoyUI` | High (modified in PRD-007) | Puzzle system added in same sprint, no tests written |

### §1.3 Bug Fixed During Audit

**VillagerDecoyUI dead prop** (`VillagerDecoyUI.tsx:10`):
`gameState: StrippedGameState` was declared in the `Props` interface but never destructured or used in the component body. `NightActionShell` passed it at the call site. Removed from both the interface and the call site.

**PlayerAvatar accessibility** (`PlayerAvatar.tsx:18`):
`role="img"` and `aria-label={player.display_name}` added. See ADR-016.

---

## §2. System Behavior

### §2.1 PlayerAvatar Contract

```typescript
interface Props {
  player: PlayerState   // required
  size?: number         // overrides CSS default 44px; fontSize = size * 0.38
  className?: string    // appended to .player-avatar
  style?: React.CSSProperties  // merged last (highest specificity)
}
```

- Background color: `getAvatarColor(player.avatar_id)` from `AVATAR_COLORS` map; fallback `#718096`
- Text content: `getInitials(player.display_name)` = `displayName.slice(0, 2).toUpperCase()`
- Accessible name: `aria-label={player.display_name}`, `role="img"`
- Default size: CSS `width/height: 44px`, `font-size: 16px` (inline style only set when `size` prop provided)

### §2.2 DayDiscussionScreen Behaviors Under Test

| Behavior | Mechanism |
|---|---|
| Timer display | `useTimer(timer_ends_at)` → `secondsRemaining` formatted as `MM:SS` |
| Warning state | `isWarning` → adds `timer--warning` CSS class |
| Critical state | `isCritical` → adds `timer--critical` (replaces `timer--warning`, not in addition) |
| Notepad toggle | `useState(false)` → open/close on button click |
| Player filter | notepad shows `is_alive && player_id !== myPlayerId` only |
| Tag cycling | `? → Sus → Safe → ?`; Sus/Safe written to localStorage, `?` removes key |
| Key scoping | `ww_note_{game_id}_{my_id}_{target_id}` |
| Stale key pruning | On mount: removes keys not matching current `game_id` |
| Seer panel | Rendered only when `myPlayer.role === 'seer'` AND `seer_knowledge` has entries |

### §2.3 VillagerDecoyUI States Under Test

| `puzzle_state` value | Rendered |
|---|---|
| `null` / `undefined` | "The Archives await…" |
| `active: true, puzzle_type: 'logic'\|'math'` | `ChoicePuzzle` |
| `active: true, puzzle_type: 'sequence'` | `SequencePuzzle` |
| `active: false, solved: true, hint_pending: true` (no hint) | "✓ Clue incoming…" |
| `active: false, solved: true` + `latestHint` provided | Hint text + expiry |
| `active: false, solved: false` | "No clue this round." |

Button lock: after answer submit, buttons are disabled for `LOCK_TIMEOUT_MS` (4000ms) as a safety valve against WRONG_PHASE server rejections. Re-enable after timeout if no state update arrives.

---

## §3. User Stories

| As a | I want to | So that |
|---|---|---|
| Mobile Player | See my avatar displayed consistently across all phases | I can identify myself and others at a glance |
| Mobile Player | Have my notepad tags persist when the discussion timer updates | I don't lose my notes between state syncs |
| Seer | See my investigation results in the day discussion panel | I can act on intel when coordinating a vote |
| Villager / Mayor / Jester | See visual feedback after submitting a puzzle answer | I know my submission was registered |
| QA Engineer | Have automated tests for recently modified components | I can confidently ship changes without manual regression |

---

## §4. Phase-Gate Plan

### Phase 1 — Bug Fixes ✓
- Remove dead `gameState` prop from `VillagerDecoyUI` Props interface and call site
- Add `role="img"` + `aria-label` to `PlayerAvatar` (see ADR-016)

### Phase 2 — Test Coverage ✓
- `frontend-mobile/src/test/components/PlayerAvatar.test.tsx` (7 tests)
- `frontend-mobile/src/test/components/DayDiscussionScreen.test.tsx` (11 tests)
- `frontend-mobile/src/test/components/VillagerDecoyUI.test.tsx` (11 tests)

### Phase 3 — Documentation ✓
- ADR-016: PlayerAvatar accessibility decision
- PRD-008: This document

---

## §5. Acceptance Criteria

**Automated:**
```bash
cd frontend-mobile
npm test   # 77 tests pass, 0 failures, 0 regressions
```

**Coverage targets (3 new files):**
- `PlayerAvatar.test.tsx` — 7 cases covering: initials, color, fallback color, size prop, style merge, className, aria-label
- `DayDiscussionScreen.test.tsx` — 11 cases covering: timer format, warning/critical classes, notepad toggle, alive filter, tag cycling, localStorage persistence, stale key pruning, seer panel visibility
- `VillagerDecoyUI.test.tsx` — 11 cases covering: null puzzle, logic/math/sequence rendering, answer submission + lock, lock timeout re-enable, all 3 resolved states

**Manual (regression check):**
- PlayerAvatar renders identically to pre-change (only attribute addition, no layout change)
- `NightActionShell` compiles and routes correctly after `gameState` prop removal from `VillagerDecoyUI`

---

## §6. Open Questions

| Question | Resolution |
|---|---|
| Should `getInitials` handle empty `display_name`? | Deferred. Backend validates name min-length = 1 char. Edge case not reachable in production. |
| Should remaining 9 untested components be covered? | Separate PRD. Prioritize by change frequency and blast radius. |
