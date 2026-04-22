# ADR-028: Framer UI — Pack Roster Display and Expanded HACK_ROLES

**Status:** Accepted  
**Date:** 2026-04-19  

---

## Context

The Framer is a wolf-team role whose night actions (Frame a Player, Hack the Archives) require coordination with other wolves. Three gaps were identified during a UI audit:

1. **No confirmed state after submission** — `FramerUI` had no `myPlayer.night_action_submitted` check. After a Framer submitted either the frame or hack action, the UI stayed on the selection screen indefinitely. `WolfVoteUI` (all other wolf roles) already handled this correctly at commit `0b619aa`.

2. **Wolf pack sub-roles invisible during night phase** — The state stripper correctly sends wolf teammates' roles to each other (`_wolf_team_view`, `stripper.py:161`). But no component in `NightActionShell` ever rendered them. In a multi-wolf game, players could not distinguish the Framer from a regular Werewolf or Infector during the night phase, making coordination ambiguous.

3. **`HACK_ROLES` dropdown incomplete** — The custom archive-hack builder in `FramerUI` only offered 7 roles. Roles like `seer`, `werewolf`, `wolf_shaman`, `bodyguard`, `witch`, `lunatic`, `jester`, `wise`, and `cupid` — all plausible targets for disinformation — were absent from the dropdown.

---

## Decision

### 1. FramerUI confirmed state (FramerUI.tsx)
Added `if (myPlayer.night_action_submitted)` guard at the top of `FramerUI`, identical in pattern to `WolfVoteUI`. Shows "Hunt target locked in. Waiting for others…" as a server-state driven transition. The `HackArchives` sub-component's local `submitted` state remains as optimistic UI feedback.

### 2. Wolf pack roster (NightActionShell.tsx + NightActionShell.css)
Added a `wolfTeammates` computed list (alive wolf-team players excluding self) rendered as compact chips above the HUNT/RADAR tabs for all wolf roles. Each chip shows `display_name` + `role` (e.g. "Alice · framer"). Chip styling is deliberately muted (low opacity red border) per PRD-002 §3.4 secrecy constraint — not vivid enough to be noticed across a table.

The roster is omitted entirely when `wolfTeammates.length === 0` (solo wolf game).

### 3. Expanded HACK_ROLES (FramerUI.tsx)
Expanded from 7 to 16 roles, grouped logically:

| Group | Roles |
|-------|-------|
| Wolf team | `werewolf`, `alpha_wolf`, `wolf_shaman`, `framer`, `infector` |
| Village action | `seer`, `tracker`, `doctor`, `bodyguard`, `witch`, `cupid` |
| Neutral/chaos | `serial_killer`, `arsonist`, `lunatic`, `wise`, `jester` |

---

## Consequences

- Framers can now inject false clues about any role that exists in the game, making disinformation more flexible and harder for villagers to cross-reference.
- Multi-wolf teams can see sub-role assignments at a glance during night phase without exchanging verbal cues — reduces meta-game information leakage.
- The pack roster only renders when `team === 'werewolf'` is present on sibling players in the stripped state, so villagers and dead spectators never see it. The server already enforces this boundary in `_wolf_team_view`.
- `HackArchives` local `submitted` state is kept as an immediate optimistic response before the server broadcasts `night_action_submitted: true`. No regression for the hack flow.

---

## Files Changed

| File | Change |
|------|--------|
| `frontend-mobile/src/components/NightActionShell/FramerUI.tsx` | `night_action_submitted` guard; expanded `HACK_ROLES` (7 → 16) |
| `frontend-mobile/src/components/NightActionShell/NightActionShell.tsx` | `wolfTeammates` computation; pack roster JSX above tabs |
| `frontend-mobile/src/components/NightActionShell/NightActionShell.css` | `.night-shell__pack`, `.night-shell__pack-chip`, `.night-shell__pack-name`, `.night-shell__pack-role` |
