# PRD-001: Werewolf — Core Game System Architecture

## §1. Context & Problem

We are building a self-hosted, web-based digital implementation of *Werewolf* (also known as *Mafia*), a social deduction party game for 5–18 players. The physical game's biggest pain points are (1) requiring a dedicated human moderator, (2) awkward night-phase logistics where players must close their eyes and trust honor, and (3) rules confusion during complex multi-role interactions.

The solution is a **"Jackbox-style" dual-client architecture**: players use personal mobile devices as private role cards and action pads, while a shared central TV display acts as the automated Game Master — driving narrative, managing timers, and animating public outcomes. This eliminates the moderator entirely.

The server must be **strictly authoritative**: it holds canonical role assignments, validates night actions, resolves conflicts, and broadcasts stripped state views. Clients send only "intents"; the server determines what each client is allowed to know.

The defining security challenge is **role secrecy**: a player's role must never appear in any WebSocket payload sent to another player's socket. The State Stripper middleware is the highest-risk component — an accidental role leak would ruin the game.

---

## §2. Game Rules Execution

### §2.1 Core Constraints

| Rule | Enforcement Level | Notes |
|------|------------------|-------|
| Roles are secret until game over | Server-hard | State Stripper removes `role` from all other player objects |
| Each night action submitted once per round | Server-hard | Server rejects duplicate action submissions |
| Wolves must reach consensus on kill target | Server-soft | Majority vote; ties block elimination (no kill that night) |
| Doctor cannot protect the same player two consecutive nights | Server-hard | Server tracks `last_protected_player_id` per Doctor |
| Player cannot vote to eliminate themselves | Server-hard | Server rejects self-vote intent |
| Day vote requires simple majority (>50%) | Server-hard | Tie = no elimination that day |
| Dead players cannot submit actions or votes | Server-hard | Server checks `is_alive` before processing any intent |
| Wolves win when `wolves_alive >= villagers_alive` | Server-hard | Win check runs after every elimination |
| Villagers win when `wolves_alive == 0` | Server-hard | Win check runs after every elimination |

### §2.2 Base Roles

| Role | Team | Night Action | Count (8-player default) |
|------|------|-------------|--------------------------|
| Villager | Village | Decoy task (count sheep) | 4 |
| Werewolf | Wolf | Vote to kill a living player | 2 |
| Seer | Village | Peek at one player's `investigationResult` (`"village"` / `"werewolf"` / `"neutral"`) | 1 |
| Doctor | Village | Protect one player from elimination | 1 |

> **Note:** Role counts are configurable by the host at lobby creation. Minimum viable game: 5 players (3 Villagers, 1 Wolf, 1 Seer).

### §2.3 Phase Machine

```
LOBBY → ROLE_DEAL → [NIGHT → DAY → DAY_VOTE → (HUNTER_PENDING?)]* → GAME_OVER
```

| Phase | Trigger In | Trigger Out | Duration |
|-------|-----------|-------------|----------|
| `lobby` | Game created | Host starts game | Indefinite |
| `role_deal` | Host presses Start | All players confirm role reveal OR timer expires | Up to 30s |
| `night` | `day_vote` resolves (or first round) | All active roles submit OR timer expires | 60s default |
| `day` | Night resolution complete | Host/timer advances to `day_vote` | 180s default |
| `day_vote` | `day` discussion ends | All living players vote OR timer expires | 90s default |
| `hunter_pending` | Hunter is eliminated (night or day) | Hunter submits revenge target OR timer expires | 30s |
| `game_over` | Win condition met | N/A | Indefinite |

**Auto-advance:** If all players with `wakeOrder > 0` (Wolves, Seer, Doctor) submit their night actions before the timer expires, the server immediately transitions to `day`. Villagers (`wakeOrder == 0`) run a decoy task and do **not** block auto-advance.

**`role_deal` auto-confirm:** If a player has not confirmed their role reveal when the 30s timer expires, the server auto-confirms them and the phase advances.

### §2.4 Night Resolution Order

The server resolves night actions in a fixed sequence to handle conflicts deterministically:

1. **Doctor** protection is applied first (sets `is_protected = true` on target).
2. **Seer** peek is resolved (result stored in Seer's private state, not broadcast).
3. **Wolf vote** is tallied. If majority agrees on a target:
   - If target `is_protected == true` → no elimination, Doctor success (not revealed).
   - Else → target `is_alive = false`, cause = `wolf_kill`.

### §2.5 Master Game State Schema

```json
{
  "game_id": "uuid",
  "schema_version": "0.4",
  "seed": "a3f9c...",
  "phase": "lobby | role_deal | night | day | day_vote | hunter_pending | game_over",
  "round": 1,
  "host_player_id": "p1",
  "timer_ends_at": "ISO8601 UTC timestamp | null",
  "config": {
    "night_timer_seconds": 60,
    "day_timer_seconds": 180,
    "vote_timer_seconds": 90,
    "role_deal_timer_seconds": 30,
    "roles": { "villager": 4, "werewolf": 2, "seer": 1, "doctor": 1 }
  },
  "players": {
    "p1": {
      "player_id": "p1",
      "display_name": "Sarah",
      "avatar_id": "wolf_01",
      "role": "werewolf",
      "team": "werewolf",
      "is_alive": true,
      "is_connected": true,
      "is_protected": false,
      "last_protected_player_id": null,
      "night_action_submitted": false,
      "role_confirmed": false
    }
  },
  "night_actions": {
    "wolf_votes": { "p2": "p5", "p3": "p5" },
    "seer_target_id": "p4",
    "doctor_target_id": "p1",
    "actions_submitted_count": 3,
    "actions_required_count": 4
  },
  "day_votes": { "p1": "p2", "p4": "p2", "p5": "p3" },
  "elimination_log": [
    { "round": 1, "phase": "night", "player_id": "p6", "cause": "wolf_kill", "role": null, "saved_by_doctor": false },
    { "round": 1, "phase": "day",   "player_id": "p2", "cause": "village_vote", "role": null, "saved_by_doctor": false }
  ],
  "winner": null,
  "seer_knowledge": { "p4": "village", "p6": "werewolf" }
}
```

**Field notes:**
- `players` is a `map[player_id → PlayerState]`, not an array.
- `team` values: `"village"` | `"werewolf"` | `"neutral"`. Replaces old `alignment` field.
- `avatar_id` is a key into the avatar registry (e.g., `"wolf_01"`). Not a URL.
- `seer_knowledge` values: `"village"` | `"wolf"` | `"neutral"` (ternary, not `"wolf"`/`"not_wolf"`).
- `winner` values: `"village"` | `"werewolf"` | `"neutral"` | `null`.
- `elimination_log[*].role` is `null` during live play; populated with the player's role at `game_over` broadcast.
- `is_protected` and `last_protected_player_id` are server-only fields — stripped from all client payloads.

### §2.6 Stripped State Payloads

The pure function `player_view(G, player_id)` is called once per connected socket on every broadcast. `player_id=None` = Display client.

**Field visibility matrix:**

| Field | Wolf (alive) | Seer (alive) | Villager/Doctor (alive) | Dead player | Display client |
|-------|-------------|-------------|------------------------|-------------|----------------|
| Own `role` + `team` | Visible | Visible | Visible | Visible (own) | Hidden — `null` |
| Wolf teammates' `role` + `team` | Visible | Hidden | Hidden | Visible | Hidden — `null` |
| All other `role` + `team` | Hidden — `null` | Hidden — `null` | Hidden — `null` | Visible | Hidden — `null` |
| `night_actions.wolf_votes` | Visible (own team) | Removed | Removed | Removed (live); visible at `game_over` | Removed |
| `night_actions.seer_target_id` | Removed | Visible (own) | Removed | Removed (live); visible at `game_over` | Removed |
| `night_actions.doctor_target_id` | Removed | Removed | Removed | Removed (live); visible at `game_over` | Removed |
| `night_actions.actions_submitted_count` | Visible | Visible | Visible | Visible | Visible |
| `night_actions.actions_required_count` | Visible | Visible | Visible | Visible | Visible |
| `seer_knowledge` | Removed (`{}`) | Full map (own peeks) | Removed (`{}`) | Full map (at `game_over`) | Removed (`{}`) |
| `players[*].night_action_submitted` | Own + wolf teammates | Own only | Own only | Removed | Removed |
| `players[*].is_protected` | Removed | Removed | Removed | Removed | Removed |
| `players[*].last_protected_player_id` | Removed | Removed | Removed | Removed | Removed |
| `elimination_log[*].role` | `null` during live play | `null` during live play | `null` during live play | Revealed at `game_over` | Revealed at `game_over` |
| `elimination_log[*].saved_by_doctor` | `false` during live play | `false` during live play | `false` during live play | Revealed at `game_over` | Revealed at `game_over` |

**Key rules:**
- **Display client** never receives any `role`, `team`, individual `night_actions` targets, or `seer_knowledge` — only `actions_submitted_count` / `actions_required_count` to show aggregate progress.
- **Dead players** are spectators. During live play, `night_actions` is stripped entirely. At `game_over`, `elimination_log` entries are enriched with `role` and `saved_by_doctor`.
- **Seer** receives their full accumulated `seer_knowledge` map — every peek result from all prior rounds.

---

## §3. Client–Server Specifications

### §3.1 Mobile Controller Client

- **Platform:** Responsive web app (React), touch-optimized, portrait-first
- **Displays:**
  - Lobby: name input + avatar picker, list of joined players
  - Role Reveal: "Hold to Reveal" overlay — role only visible while thumb is held
  - Night Phase: role-specific action UI (Wolves: player carousel; Seer: player list; Doctor: player list; Villager: decoy sheep counter). Screen is uniformly dark for all roles.
  - Day Phase: casualty announcement banner, living player list, vote buttons, private notepad
  - Dead State: grayed UI, spectator role reveal of all living players
- **Sends:** Intent JSON over WebSocket (`submit_night_action`, `submit_day_vote`, `confirm_role_reveal`)
- **Receives:** `StrippedPlayerState` (own role visible, others hidden)

### §3.2 Display Client

- **Platform:** Web app (React, DOM-only — no Canvas/PixiJS required)
- **Displays:**
  - Lobby: QR code + room code, avatar parade as players join, player count
  - Night Phase: dark atmospheric screen, phase narrative text, aggregate action progress, ambient timer
  - Day Phase: player avatar grid (dead = grayed + tombstone), discussion timer, live vote-web overlay
  - Game Over: winning team splash, role reveal for all players, elimination timeline
- **Sends:** Nothing (read-only observer)
- **Receives:** `StrippedDisplayState` (no role data)

### §3.3 Server (Python FastAPI + WebSockets)

- **Phase machine:** Dict-driven, same pattern as Brass Birmingham. Each phase has an `on_enter`, `process_intent`, and `auto_advance_if` predicate.
- **Timer management:** Server owns all timers as absolute `timer_ends_at` timestamps. A background `asyncio` task fires `phase_timeout` when the timer expires. Clients display a countdown derived from the server timestamp — they do NOT own timer state.
- **Night resolution:** Pure function `resolve_night(G) -> G'` — deterministic, no side effects. Run once when `auto_advance_if` triggers.
- **Concurrency:** Same queue-based serialization as Brass Birmingham — one `asyncio.Queue` per active game.
- **State Stripper:** `player_view(G, player_id)` — pure function per connected socket per broadcast. `player_id=None` = display client (all roles stripped).

### §3.4 WebSocket Intent Payloads

```json
// Mobile → Server: night action
{ "type": "submit_night_action", "game_id": "uuid", "player_id": "p1", "target_id": "p5" }

// Mobile → Server: day vote
{ "type": "submit_day_vote", "game_id": "uuid", "player_id": "p1", "target_id": "p3" }

// Mobile → Server: role confirmed (advances out of role_deal phase)
{ "type": "confirm_role_reveal", "game_id": "uuid", "player_id": "p1" }

// Server → All: state broadcast
{ "type": "state_update", "state_id": 42, "schema_version": "0.4", "state": { ...StrippedState } }

// Server → Mobile: error
{ "type": "error", "code": "DEAD_PLAYER_ACTION", "message": "Dead players cannot submit actions." }
```

---

## §4. Phase-Gate Plan

| Phase | Gate | Deliverable |
|-------|------|-------------|
| 0 — Architecture | ADR-001 approved | Tech stack decisions locked |
| 1 — Backend Core | Tests passing | `GameState` model, phase machine, State Stripper, night resolver |
| 2 — Mobile MVP | Manual QA | Lobby join, role reveal, night action, day vote |
| 3 — Display MVP | Manual QA | All phases render correctly on TV from shared URL |
| 4 — Integration | End-to-end game completes | 5-player game runs start to finish without moderator |
| 5 — Polish | UX review | Timers, atmospheric text, elimination animations, post-match stats |

---

## §5. User Stories

| As a | I want to | So that |
|------|-----------|---------|
| Mobile Player | join a game by scanning a QR code | I don't need to type a long URL |
| Mobile Player | hold a button to privately reveal my role | my neighbors can't accidentally see my card |
| Mobile Player (Werewolf) | see a list of living players during the night phase | I can vote on who to eliminate |
| Mobile Player (Seer) | peek at one player's team affiliation (`"village"` / `"werewolf"` / `"neutral"`) | I can guide the village debate |
| Mobile Player (Doctor) | protect one player per night | I can save a villager from the wolves |
| Mobile Player (Villager) | have a decoy task on my screen | observers can't tell who is a wolf by watching who taps their phone |
| Mobile Player (Dead) | see all roles after being eliminated | I can enjoy watching the game as a spectator |
| Display Client | show an atmospheric night-phase screen | the room feels immersive and tension is built |
| Display Client | show a live vote-web during day voting | the whole room can see alliances form in real time |
| Game Server | auto-advance from night to day when all actions are submitted | the game doesn't drag when players are ready |
| Game Server | detect the win condition after every elimination | the game ends immediately when wolves equal villagers |
| Mobile Player | reconnect to my game if my browser refreshes | a Wi-Fi hiccup doesn't end my game |

---

## §6. Open Questions

| # | Question | Owner | Priority | Status |
|---|----------|-------|----------|--------|
| 1 | Should wolf-team members see each other's identities during the night phase? (Standard: yes) | Game Design | P0 | **Resolved — §7.1** |
| 2 | What happens when a wolf is the last player with a night action — do they still get anonymity? | Game Design | P0 | **Resolved — §7.3** |
| 3 | Should the Seer's peek result persist across rounds on their mobile screen? | UX | P1 | **Resolved — §7.2** |
| 4 | Do we support a "Mayor" role (village vote tiebreaker) in v1? | Game Design | P1 | Out of scope for v1 |
| 5 | Configurable role sets — should the host pick from a preset list or build a custom role mix? | Product | P1 | Preset templates only (see `config.roles`) |
| 6 | Audio: browser autoplay policy restrictions — how do we trigger ambient sound on the Display TV without a user gesture? | Engineering | P1 | Open — host's "Start Game" click unlocks audio context |

---

## §7. Design Decisions

These decisions resolve previously open questions and close implementation gaps discovered during schema validation.

### §7.1 Wolves See Each Other During Night Phase

**Decision:** Yes. When wolves receive their stripped state during the `night` phase, they see `role` and `team` for all wolf teammates. This is standard Werewolf rules and required for the wolf-vote consensus UI.

**Enforcement:** `player_view()` includes wolf teammates' `role`/`team` when `requesting_player.team == "werewolf"`.

### §7.2 Seer Peek History Persists Across Rounds

**Decision:** Yes. The `seer_knowledge` map accumulates all peeks from all prior rounds and is sent to the Seer on every state update. It is displayed as a history list on the Seer's mobile night-phase screen.

**Enforcement:** `seer_knowledge` is append-only; never cleared during live play.

### §7.3 Wolf Night-Vote Tie = No Kill

**Decision:** If wolves split their votes (no single target holds strict majority `> 50%`), no elimination occurs that night. The game proceeds to `day` with zero casualties. Wolves are not penalized — they try again next night.

**Enforcement:** `resolve_night()` tallies `wolf_votes`; requires `count(target) > total_wolves / 2` to trigger an elimination.

### §7.4 Day Vote Is Mutable Until Phase Closes

**Decision:** Players may change their day vote at any time while `phase == "day_vote"`. The last submitted `target_id` overwrites the previous entry in `day_votes`. Votes are finalized when the phase exits.

**Enforcement:** `submit_day_vote` intent updates `day_votes[player_id]` unconditionally (no first-vote locking).

### §7.5 Villagers Do Not Block Night Auto-Advance

**Decision:** `actions_required_count` counts only players with `wakeOrder > 0` (Wolves, Seer, Doctor). Villager decoy tasks (`wakeOrder == 0`) are purely UI — they are never submitted to the server and do not affect phase progression.

**Enforcement:** When computing `auto_advance_if`, server checks `actions_submitted_count >= actions_required_count`, where `actions_required_count` excludes Villagers.

### §7.6 Doctor Consecutive-Protect Includes Self

**Decision:** The Doctor may not protect the same player two consecutive nights, including themselves. `last_protected_player_id` is checked and updated on every Doctor submission.

**Enforcement:** `submit_night_action` for Doctor rejects `target_id == last_protected_player_id` with error code `CONSECUTIVE_PROTECT_FORBIDDEN`.
