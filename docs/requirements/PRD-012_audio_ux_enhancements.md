# PRD-012: Audio UX Enhancements — Voting Countdown, Night Ambient, Wolf Kill Scream

## 1. Context & Problem

The display client has foundational audio infrastructure (night ambient, narrator TTS, game-over
fanfares) but lacks moment-to-moment tension audio. Three gaps:

1. The 90-second voting timer expires silently — players lose urgency in the final seconds.
2. Night ambient audio is wired in `NightScreen.tsx` but the required MP3 file is not yet placed
   in the asset tree, so it never plays.
3. There is no audio feedback when the wolf pack locks in their kill, causing the night phase to
   feel inert for spectators watching the display.

---

## 2. Rules Execution

### §2.1 Countdown Beep (Voting Phase)

| Condition | Behaviour |
|-----------|-----------|
| `phase === 'day_vote'` AND `secondsRemaining <= 10` | One synthetic beep fires per second |
| `secondsRemaining === 1` | Final beep uses 880 Hz (double-pitch emphasis) |
| Any other phase or `secondsRemaining > 10` | No beep |
| `audioUnlocked === false` | No beep (browser autoplay gate) |

Implementation uses the Web Audio API oscillator — no MP3 asset required (see ADR-023).

### §2.2 Night Ambient

| Condition | Behaviour |
|-----------|-----------|
| `phase === 'night'` AND `audioUnlocked === true` | Looping ambient track starts at volume 0.4 |
| Phase exits `night` | Audio paused via React `useEffect` cleanup |

Code already exists in `NightScreen.tsx:31–41`. Feature is blocked only by the missing asset at
`frontend-display/public/audio/night-ambient.mp3`.

### §2.3 Wolf Kill Scream

| Condition | Behaviour |
|-----------|-----------|
| First wolf-team member submits `submit_night_action` with a kill vote this night | Backend emits `wolf_kill_queued` to all room sockets |
| Display receives `wolf_kill_queued` AND `audioUnlocked === true` | Scream SFX plays after a random 3 000–30 000 ms delay |
| Night phase ends before the delay fires | Scheduled scream is cancelled |
| Subsequent wolf votes the same night | Ignored (one signal per night via `len(wolf_votes) == 1` guard) |

### §2.4 New WebSocket Payload Schema

```json
// Server → all sockets in game room
{ "type": "wolf_kill_queued" }
```

No state carried — display client only uses this as a timing cue.

---

## 3. Client-Server Specification

### Display Client

| Component / Hook | Responsibility |
|------------------|----------------|
| `useCountdownBeep(secondsRemaining, isActive)` | Web Audio oscillator, fires once per second tick ≤ 10 |
| `PhaseTimer` | Accepts `enableCountdownBeep` + `audioUnlocked` props; calls hook |
| `DayScreen` | Passes `enableCountdownBeep={isVoting}` + `audioUnlocked` to PhaseTimer |
| `useGameState.onWolfKillQueued` | Callback forwarded to App.tsx scream scheduler |
| `App.tsx` | Schedules scream via `setTimeout`; cancels via `screamTimeoutRef` on phase exit |

### Backend

| File | Change |
|------|--------|
| `backend-engine/api/intents/handlers.py` | After first wolf vote recorded: `broadcast_raw(game_id, {"type": "wolf_kill_queued"})` |

---

## 4. User Stories

| As a | I want to | So that |
|------|-----------|---------|
| Display Client | hear a tick each second in the final 10s of voting | the room feels the urgency of the deadline |
| Display Client | hear looping atmospheric audio during the night phase | spectators feel the tension of the dark |
| Display Client | hear a scream sound 3–30s after wolves commit to a kill | the night phase has an unpredictable horror moment |
| Game Server | emit only one scream signal per night regardless of wolf count | the display never plays duplicate screams |

---

## 5. Required Assets

| Path | Description | Notes |
|------|-------------|-------|
| `frontend-display/public/audio/night-ambient.mp3` | Looping atmospheric night track | Any duration; must loop cleanly |
| `frontend-display/public/audio/scream.mp3` | Short scream SFX | 1–3s recommended |

Countdown beep uses Web Audio API — no file required.

---

## 6. Phase-Gate Plan

| Phase | Deliverable |
|-------|-------------|
| 1 | `useCountdownBeep` hook + PhaseTimer + DayScreen wiring |
| 2 | App.tsx wolf-kill scream scheduler + type + useGameState callback |
| 3 | Backend `wolf_kill_queued` signal in handlers.py |
| 4 | Asset files placed at `public/audio/` |

---

## 7. Open Questions

- Should the scream volume be configurable via the lobby settings panel (PRD-011)?
- Should `wolf_kill_queued` be suppressed when `narrator_enabled=false` in game config?
