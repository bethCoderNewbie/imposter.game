# PRD-011: Display Pre-Game Settings & Host Authority on CreateMatchScreen

## §1 Context & Problem

The Display client at `http://<HOST>/display/` is the **authoritative game host**: it creates the match, holds the `host_secret`, configures difficulty and timers in the lobby, starts the game, and manages rematch/abandon after game-over. Despite this authority, the landing screen (`CreateMatchScreen`) presented a blank page with only a "Create New Match" button — no settings, no defaults visible.

Game hosts had no way to set difficulty or phase timers until *after* creating a game. Settings were only accessible in `LobbyConfigPanel` once a game ID existed. This created a disjointed flow: create → watch the lobby load → then configure. For hosts who run recurring sessions, pre-configuring before players join is a natural expectation.

Additionally, a related regression made "Play Again" and "New Match → Create New Match" non-functional on the Display client (see ADR-019). This PRD covers the UX surface; ADR-019 covers the underlying state-fence bug.

---

## §2 Requirements

### §2.1 Rules Execution

1. **Pre-game settings panel** is shown on `CreateMatchScreen` above the "Create New Match" button.
2. The panel renders:
   - Difficulty selector: **Easy / Balanced / Hard** (3 buttons; default: Balanced)
   - Phase timers: **Night / Day / Vote** stepper rows with the same bounds as `LobbyConfigPanel` (Night 30–120 s step 15, Day 60–300 s step 30, Vote 30–120 s step 15)
3. On "Create New Match" click, the flow is:
   a. `POST /api/games` → receive `game_id` + `host_secret`
   b. `PATCH /api/games/{game_id}/config` with selected difficulty + timers + `host_secret`
   c. Call `onCreated(game_id, host_secret)` → transition to `LobbyScreen`
4. If the PATCH fails (network error), it is silently ignored — the game proceeds with server defaults. This is acceptable because `LobbyConfigPanel` remains available in the lobby for re-adjustment.
5. `LobbyConfigPanel` in `LobbyScreen` retains full edit authority during the lobby phase. Pre-game settings are a convenience, not a replacement.
6. The settings are rendered with **local React state only** — no API calls are made until "Create New Match" is clicked.

### §2.2 Shared Constants

Difficulty labels, timer bounds, timer steps, and timer labels are extracted to `frontend-display/src/components/LobbyConfigPanel/config.ts` and imported by both `LobbyConfigPanel` and `CreateMatchScreen`. This ensures the two surfaces stay in sync without duplication.

---

## §3 Client–Server Specification

### Display CreateMatchScreen → Backend

**Step 1: Game creation (unchanged)**
```
POST /api/games
Body: {}
Response: { game_id, host_secret, join_code }
```

**Step 2: Apply pre-game settings**
```
PATCH /api/games/{game_id}/config
Body: {
  host_secret: string,
  difficulty_level: "easy" | "standard" | "hard",
  night_timer_seconds: number,
  day_timer_seconds: number,
  vote_timer_seconds: number
}
Response: { ok: true }
```

Both steps execute in `handleCreate()` before calling `onCreated()`. The PATCH uses the same endpoint as `LobbyConfigPanel` — no backend changes required.

---

## §4 Files Changed

| File | Change |
|------|--------|
| `frontend-display/src/components/LobbyConfigPanel/config.ts` | New — shared constants extracted here |
| `frontend-display/src/components/LobbyConfigPanel/LobbyConfigPanel.tsx` | Now imports from `./config` |
| `frontend-display/src/components/CreateMatchScreen/CreateMatchScreen.tsx` | Added settings UI + two-step create+PATCH flow |
| `frontend-display/src/test/components/CreateMatchScreen.test.tsx` | Added tests for settings UI + PATCH behavior |

---

## §5 User Stories

| As a | I want to | So that |
|------|-----------|---------|
| Display Host | See difficulty and timer controls on the home screen | I can configure the game before any players join |
| Display Host | Select "Hard" difficulty before creating a match | The role composition reflects the desired challenge level from the start |
| Display Host | Adjust Night/Day/Vote timers before creating | Slower groups get more discussion time without needing to adjust mid-lobby |
| Display Host | Still edit settings in the Lobby screen | I can react to last-minute player count changes |

---

## §6 Open Questions

None — the settings panel uses the same bounds and step increments as the existing `LobbyConfigPanel`, and the PATCH endpoint is already production-hardened.
