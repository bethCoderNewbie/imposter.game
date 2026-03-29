# ADR-011: Werewolf — Mobile Client Protocol Parity & Missing Phase Screens

## Status

Accepted

## Date

2026-03-28

## Context

A full validation of `frontend-mobile` against ADR-003, ADR-007, PRD-001, and PRD-002 revealed six gaps introduced between the ADR-007 protocol rename (2026-03-27) and the mobile client's last update. The gaps fall into three categories:

1. **Protocol mismatch** — ADR-007 renamed the WS state-push discriminator from `state_update` to `sync` (initial push) and `update` (per-event broadcast). `frontend-display` was updated; `frontend-mobile` was not. Mobile's `useGameState.ts:26` filters on `state_update`, which the backend never emits — the mobile client receives zero game state updates.

2. **Wrong or missing intents for two phases** — `hunter_pending` was routed to `DayVoteScreen`, which emits `submit_day_vote`. The backend's `handle_hunter_revenge` calls `_require_phase(G, Phase.HUNTER_PENDING)`, rejecting `submit_day_vote` with `WRONG_PHASE`. The Hunter's revenge shot was permanently broken.

3. **Missing night action UIs for four roles** — `NightActionShell` routed `tracker`, `serial_killer`, `cupid`, and `arsonist` to `VillagerDecoyUI` (the archive puzzle shell). These roles have `wakeOrder > 0` so the server never populates `puzzle_state` for them. They saw "The Archives await…" with no puzzle and no way to submit their night action. Auto-advance timed out every night they were in play.

4. **`game_over` stub and dead-player precedence** — The `game_over` screen was an inline div showing only winner + own role. PRD-001 §3 requires all roles revealed and an elimination timeline. Additionally, the dead-player guard (`!myPlayer.is_alive`) preceded the `game_over` check, causing eliminated players to see `DeadSpectatorScreen` through the end of the game, missing the final reveal entirely.

5. **Neutral win not handled** — `App.tsx:180` used a binary `village`/`wolves` string. `winner` can be `'neutral'` (Jester, Serial Killer), with the winning player identified by `winner_player_id`. Non-village, non-wolf wins silently rendered "Wolves Win!".

6. **`GameConfig.difficulty_level` missing from mobile types** — ADR-010 added `difficulty_level` to `GameConfig`. The mobile `types/game.ts` was not updated, leaving the mobile schema out of sync with the backend model.

---

## Decision

### 1. Sync WS message types: `state_update` → `sync` / `update`

**Decision:** Replace `StateUpdateMessage { type: 'state_update' }` in `frontend-mobile/src/types/game.ts` with two interfaces mirroring the display client:

```typescript
interface SyncMessage  { type: 'sync';   state_id: number; schema_version: string; state: StrippedGameState }
interface UpdateMessage { type: 'update'; state_id: number; schema_version: string; state: StrippedGameState }
```

`ServerMessage` union updated to `SyncMessage | UpdateMessage | ErrorMessage | HintPayload`.

`useGameState.ts` handler updated: `msg.type === 'state_update'` → `msg.type === 'sync' || msg.type === 'update'`.

**Why not introduce a third `state_update` alias in the backend:** The backend has already committed to `sync`/`update` (ADR-007). Adding a backwards-compat alias would widen the backend surface for no gain. The mobile fix is a one-line handler change.

**Mobile vs display divergence intentional:** The display hook also seeds a Zustand roster store on `sync` (ADR-009). Mobile has no Zustand dependency and no roster store — the `sync`-seeding branch is omitted. Both clients apply the same `state_id > lastStateIdRef.current` fence.

---

### 2. `hunter_pending` → dedicated `HunterPendingScreen`

**Decision:** Split `App.tsx`'s combined `'day_vote' || 'hunter_pending'` routing into two cases. `hunter_pending` renders a new `HunterPendingScreen` component.

`HunterPendingScreen` is structurally identical to `DoctorProtectUI` (single-target picker, `ActionUI.css`). The only difference is the intent type and label:

```typescript
sendIntent({ type: 'hunter_revenge', target_id: selectedId })
```

Target filter: all living players except the Hunter themselves. There is no "last target" constraint (Hunter fires once, `hunter_fired` flag is server-enforced).

**Why not reuse DayVoteScreen with a prop:** `DayVoteScreen` is bound to `submit_day_vote` semantics (voting to eliminate, change-vote UX, "Vote cast — waiting" status). The Hunter's one-shot revenge is a different interaction model. A dedicated component is clearer and avoids a conditional intent-type prop threading through `DayVoteScreen`.

---

### 3. Night action UIs for tracker, serial_killer, cupid, arsonist

**Decision:** Four new UI components added to `NightActionShell/`. `NightActionShell` routing extended before the `else → VillagerDecoyUI` fallback.

| Component | Role | Intent |
|-----------|------|--------|
| `TrackerUI` | `tracker` | `{ type: 'submit_night_action', target_id }` — all living, exclude self |
| `SerialKillerUI` | `serial_killer` | `{ type: 'submit_night_action', target_id }` — all living, exclude self |
| `CupidUI` | `cupid` (round 1 only) | `{ type: 'submit_night_action', link_target_a, link_target_b }` — two-step dual-picker |
| `ArsonistUI` | `arsonist` | Douse: `{ …, arsonist_action: 'douse', target_id }` / Ignite: `{ …, arsonist_action: 'ignite' }` |

**Routing addition in NightActionShell:**
```
role === 'tracker'                   → TrackerUI
role === 'serial_killer'             → SerialKillerUI
role === 'cupid' && round === 1      → CupidUI
role === 'arsonist'                  → ArsonistUI
else                                 → VillagerDecoyUI  (villager, mayor, jester, cupid r2+, hunter)
```

**Cupid round-gate:** After round 1, Cupid has `actionPhase: "night_one_only"` — they are treated as `wakeOrder == 0` by the server and receive a `puzzle_state`. Routing Cupid in round 2+ to `VillagerDecoyUI` is correct.

**Hunter at night:** Hunter's `actionPhase` is `"on_death"`, not `"night"`. A Hunter player during the normal night phase behaves like a Villager (`wakeOrder == 0`). Their revenge is served by `HunterPendingScreen` (Decision 2), not `NightActionShell`.

**`ArsonistUI` — `doused_player_ids` field:** The state stripper sends `doused_player_ids` only to the Arsonist's own player strip. `PlayerState` in `frontend-mobile/src/types/game.ts` gains an optional `doused_player_ids?: string[]` field so `ArsonistUI` can read it without a type assertion.

**Why not a generic `TargetPickerUI`:** `TrackerUI` and `SerialKillerUI` are structurally identical but their header text and CSS selection class differ. `CupidUI` has a two-step interaction model. `ArsonistUI` has a binary mode toggle. A single generic component would require 4+ props to cover all variants — more complex than 4 small focused components.

---

### 4. `game_over` phase takes precedence; `GameOverScreen` extracted

**Decision (4a — precedence):** The dead-player guard in `App.tsx` is moved below the `game_over` check. Both alive and eliminated players see `GameOverScreen` when `phase === 'game_over'`. The dead guard continues to apply for all live phases (`lobby` through `hunter_pending`).

**Decision (4b — GameOverScreen component):** A dedicated `GameOverScreen` component replaces the inline div. It renders:
- Winner banner: handles `village` / `werewolf` / `neutral` via `winner_player_id` lookup
- All-player grid: avatars + role badges (server sends full roles at `game_over` per state stripper rules)
- Elimination log: `elimination_log[]` ordered list with round, cause, player name
- "Play Again" → clears session

**Why extract to a component:** The inline div was a placeholder. `GameOverScreen` centralises the end-state display for testability and future enhancement (animations, share button, etc.).

---

### 5. `GameConfig.difficulty_level` added to mobile types

**Decision:** Add `difficulty_level: 'easy' | 'standard' | 'hard'` to the `GameConfig` interface in `frontend-mobile/src/types/game.ts`. Inline union (no separate export) because mobile reads but never mutates this field.

---

## Consequences

### Files Changed

| File | Change |
|------|--------|
| `frontend-mobile/src/types/game.ts` | Replace `StateUpdateMessage` with `SyncMessage` + `UpdateMessage`; update `ServerMessage` union; add `difficulty_level` to `GameConfig`; add `doused_player_ids?` to `PlayerState` |
| `frontend-mobile/src/hooks/useGameState.ts` | Handler: `'state_update'` → `'sync' \|\| 'update'` |
| `frontend-mobile/src/App.tsx` | `game_over` check before dead guard; `hunter_pending` → `HunterPendingScreen`; `GameOverScreen` import; remove inline div |
| `frontend-mobile/src/components/HunterPendingScreen/HunterPendingScreen.tsx` | New — `hunter_revenge` intent |
| `frontend-mobile/src/components/HunterPendingScreen/HunterPendingScreen.css` | New |
| `frontend-mobile/src/components/NightActionShell/NightActionShell.tsx` | Extended routing chain |
| `frontend-mobile/src/components/NightActionShell/TrackerUI.tsx` | New |
| `frontend-mobile/src/components/NightActionShell/SerialKillerUI.tsx` | New |
| `frontend-mobile/src/components/NightActionShell/CupidUI.tsx` | New |
| `frontend-mobile/src/components/NightActionShell/ArsonistUI.tsx` | New |
| `frontend-mobile/src/components/GameOverScreen/GameOverScreen.tsx` | New |
| `frontend-mobile/src/components/GameOverScreen/GameOverScreen.css` | New |

### No Backend Changes

All six gaps were client-side. The backend already emits the correct message types, handles `hunter_revenge`, and strips state correctly for all roles.

### Tests

No mobile test infrastructure exists. These components follow the same structural patterns as their display-client counterparts (covered by `frontend-display/src/test/`). A mobile test setup sprint is deferred.

### Positive

- Mobile client now receives game state — the protocol fix unblocks the entire application.
- Hunter can fire their revenge shot — a silent game-breaking bug is resolved.
- Four roles can perform their night actions — tracker, SK, Cupid, Arsonist are no longer stuck.
- `game_over` shows all roles and the elimination timeline per PRD-001 §3.
- Neutral wins display correctly for Jester and Serial Killer.
- Mobile `GameConfig` type is in sync with the backend schema.

### Negative

- No mobile tests added in this sprint. The new components are untested beyond manual verification.
- `ArsonistUI` reads `doused_player_ids` from `myPlayer` — if the server ever stops sending this field to the Arsonist's strip, the ignite button will be disabled indefinitely. The data dictionary documents this as an Arsonist-only field, so the risk is low.
