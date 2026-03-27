# Data Dictionary: Werewolf — Game State Schemas

**Last updated:** 2026-03-26 (schema v0.5: Phase 1 corrections — investigationResult enum `"wolf"` not `"werewolf"`; round increment rule; timer_ends_at timed phases; GameConfig defaults; hunter_pending_timer added; player_id UUID; complete role enum including framer/tracker/cupid/infector/arsonist; full EliminationCause enum; post_match.winner enum; source path corrected)
**Schema version:** 0.5
**Source of truth:** `backend-engine/engine/state/` (models, enums); `backend-engine/api/intents/` (handlers, dispatch)
**Static board data:** `docs/architecture/roles.json` (role definitions, dynamic composition templates, balance weights, win conditions, archive puzzle system)
**Shared TypeScript types:** `backend-engine/api/schemas/shared_types.ts` (synced to `frontend-mobile/src/types/` and `frontend-display/src/types/`)

---

## State Stripper Rules

The server never sends role data to the wrong client. `player_view(G, player_id)` is a pure function called once per connected socket on every broadcast.

**`investigationResult` vs `team`:** These are distinct fields. `team` is the actual faction (`"village"` / `"werewolf"` / `"neutral"`). `investigationResult` is what the Seer's inspect action returns — it may differ (e.g., Alpha Wolf has `team: "werewolf"` but `investigationResult: "village"`). The Seer never sees `team` directly; they only see `investigationResult`.

| View type | `player_id` arg | `role` visible | `team` visible | Wolf teammates visible | `night_actions` visible | `seer_knowledge` |
|-----------|----------------|---------------|----------------|----------------------|------------------------|-----------------|
| **Werewolf team (alive)** | own ID, `team == "werewolf"` | Own only | Own + wolf teammates | ✅ wolf teammates' roles + names | `wolf_votes`, `roleblock_target_id` (own team only) | ❌ |
| **Seer (alive)** | own ID, `role == "seer"` | Own only | Own only | ❌ | Own `seer_target_id` + `seer_result` | ✅ own accumulated entries |
| **Village non-Seer (alive)** | own ID, `team == "village"`, not seer | Own only | Own only | ❌ | ❌ block removed | ❌ |
| **Neutral (alive)** | own ID, `team == "neutral"` | Own only | Own only | ❌ | Own action only (`serial_killer_target_id` for SK) | ❌ |
| **Dead (spectator)** | own ID, `is_alive == false` | ✅ all players | ✅ all players | ✅ | ✅ full (after `game_over` phase only) | ✅ full |
| **Display client** | `None` | ❌ all null | ❌ all null | ❌ | ❌ block removed; `actions_submitted_count` only | ❌ |

**Critical invariant:** `role` and `team` fields must NEVER appear in any payload where the recipient's `player_id` differs from the target player — and never in Display client payloads. A single leak here ruins the session. `investigationResult` is equally sensitive and must follow the same rule.

---

## WebSocket Connection Lifecycle

### Accept & register sequence

1. `endpoint.py` calls `await websocket.accept()` — the sole accept point for each connection.
2. Session token is validated (player connections) or the `"display"` sentinel is verified.
3. `manager.connect(game_id, player_id, ws)` registers the already-accepted socket in `_rooms[game_id]`.
4. `queue.start()` begins the per-game intent consumer.
5. **Initial state unicast:** `load_game(redis, game_id)` → `player_view(G, player_id)` → `websocket.send_text(state_update)`. This ensures the connecting client receives current state immediately without waiting for the next game event.
6. Receive loop begins.

> **Why the initial push matters:** Without step 5, a display client connecting mid-game (or after a page refresh) shows "Waiting for game…" indefinitely. The dark-background symptom on `/display/` was caused by this missing push combined with a double `ws.accept()` bug (see ADR-004).

---

## WebSocket Payload Wrapper (StatePayload)

Top-level object sent server → all connected sockets on every state mutation, and also unicast to each client on connect (initial state push).

| Field | Type | Description | Source / Logic | Nullable |
|:------|:-----|:------------|:---------------|:---------|
| `type` | `str` | Message discriminator. Always `"state_update"` for game state broadcasts. | Server constant | No |
| `state` | `MasterGameState` (stripped) | Full game state, stripped per recipient via `player_view()`. | Server authoritative state | No |
| `state_id` | `int` | Monotonically incrementing version counter. Clients echo this on every action as a stale-state fence — server rejects actions with mismatched `state_id`. | Incremented on every successful state mutation | No |
| `schema_version` | `str` | Build-time schema version. Client hard-reloads on mismatch. Set via `SCHEMA_VERSION` env var. | Build-time constant | No |

**Error payload** (server → single client):

| Field | Type | Description |
|:------|:-----|:------------|
| `type` | `str` | `"error"` |
| `code` | `str` | Machine-readable error code. See Error Codes section. |
| `message` | `str` | Human-readable description. Used for development logging, not UI display. |

---

## Error Codes

| Code | Trigger |
|:-----|:--------|
| `STALE_STATE` | `state_id` in intent does not match server's current `state_id` |
| `WRONG_PHASE` | Intent submitted during incorrect phase (e.g., night action during day) |
| `DEAD_PLAYER_ACTION` | Dead player attempted to submit an action or vote |
| `DUPLICATE_ACTION` | Player already submitted a night action this round |
| `INVALID_TARGET` | Target player ID does not exist, is dead, or is the submitting player (self-vote) |
| `INVALID_WOLF_TARGET` | Werewolf team player attempted to vote for a wolf teammate |
| `CONSECUTIVE_PROTECT` | Doctor attempted to protect the same player as last round |
| `NO_NIGHT_ACTION` | Player with `actionPhase: "none"` submitted a night action intent |
| `HUNTER_NOT_PENDING` | `hunter_revenge` intent received but no Hunter elimination is pending |
| `HUNTER_ALREADY_FIRED` | Hunter attempted a second revenge kill (maxUses: 1 exceeded) |
| `ROLEBLOCK_NOT_AVAILABLE` | `roleblock` secondary intent submitted by a non-Wolf-Shaman player |
| `INSUFFICIENT_PLAYERS` | Host attempted to start game with fewer than 5 players |
| `INVALID_COMPOSITION` | Role counts in GameConfig do not sum to `player_count`, or wolves ≥ non-wolves at start |
| `ROLE_NOT_FOUND` | Role ID in composition not present in `roles.json` |
| `INFECT_ALREADY_USED` | Infector submitted an infect action but `infect_used == true` |
| `INFECT_NOT_AVAILABLE` | `infector_target_id` submitted by a non-Infector player |
| `CUPID_WRONG_ROUND` | Cupid submitted `link_players` intent after round 1 |
| `CUPID_DUPLICATE_TARGET` | Cupid selected the same player for both link slots |
| `ARSONIST_IGNITE_NO_DOUSED` | Arsonist submitted `ignite` but `doused_player_ids` is empty |
| `ARSONIST_INVALID_CHOICE` | Arsonist `arsonist_action` value is not `"douse"` or `"ignite"` |
| `TRACKER_SELF_TARGET` | Tracker attempted to track themselves |
| `PUZZLE_NOT_ACTIVE` | `submit_puzzle_answer` intent received but no puzzle is active for this player (wrong phase, or player has `wakeOrder > 0`) |
| `INVALID_PUZZLE_ANSWER` | Answer submitted does not match a valid option for the current puzzle type |
| `HINT_ALREADY_RECEIVED` | Server attempted to deliver a hint the player already received this session (deduplication fence — server-internal, not sent to client) |
| `FRAMER_INVALID_ACTION` | `framer_action` value is not `"frame"` or `"hack_archives"` |
| `FALSE_HINT_CATEGORY_INVALID` | `false_hint_category` is not one of `["wolf_count", "no_role_present", "role_present"]` |
| `FALSE_HINT_MISSING_PARAM` | Template requires a parameter (role name or wolf count) but none was provided in the intent |

---

## RoleDefinition (from roles.json)

Static, loaded at startup from `docs/architecture/roles.json`. Never mutated at runtime. Sent to clients as `state.role_registry` in the initial `state_update` broadcast so Mobile clients can render role descriptions and UI prompts without a separate API call.

| Field | Type | Description | Nullable |
|:------|:-----|:------------|:---------|
| `id` | `str` | Snake-case role key. E.g., `"alpha_wolf"`, `"serial_killer"`. Primary key — used as `PlayerState.role`. | No |
| `name` | `str` | Display name shown on Role Reveal screen. E.g., `"Alpha Wolf"`. | No |
| `team` | `str` enum | Faction membership. `"village"` \| `"werewolf"` \| `"neutral"`. Determines win condition eligibility. **Never sent to clients other than own player.** | No |
| `investigationResult` | `str` enum | What the Seer's `inspect` action returns when targeting this role. `"village"` \| `"wolf"` \| `"neutral"`. May differ from `team` (Alpha Wolf: `team="werewolf"`, `investigationResult="village"`). **Never sent to clients other than the Seer.** | No |
| `wakeOrder` | `int` | Night wake sequence position. `0` = no wake (decoy task). `1` = Cupid + wolf team (simultaneous). `2` = Seer + Framer (simultaneous). `3` = Doctor + Infector (simultaneous). `4` = Arsonist + Serial Killer (simultaneous). `5` = Tracker (always last — reads all resolved actions). Roles sharing a `wakeOrder` receive their prompts simultaneously on mobile but their server effects resolve in the order defined in `nightResolutionOrder`. | No |
| `actionPhase` | `str` enum | When this role's action fires. `"none"` \| `"night"` \| `"night_one_only"` \| `"day"` \| `"on_death"`. `"night_one_only"` = role submits a night action only in round 1 (Cupid). After round 1 the role is treated as `"none"` and shown the decoy prompt. | No |
| `actionType` | `str` enum | Mechanical action classification. Server uses this to route `submit_night_action` intents to the correct resolver. Values: `"none"` \| `"inspect"` \| `"protect"` \| `"eliminate_group"` \| `"eliminate_solo"` \| `"roleblock"` \| `"double_vote"` \| `"revenge_kill"` \| `"manipulate_or_hack"` (Framer — either sets `is_framed_tonight` OR queues false hint; branches on `framer_action`) \| `"convert"` (Infector — changes role/team) \| `"link_players"` (Cupid — establishes lovers_pair) \| `"multi_choice"` (Arsonist — douse or ignite) \| `"track"` (Tracker — returns target's action targets). | No |
| `maxUses` | `int` \| `null` | Maximum times this ability can be used. `null` = unlimited. `1` = once only (Hunter). | Yes |
| `description` | `str` | One-sentence role description shown on Role Reveal screen bullet 0. | No |
| `abilities` | `array[str]` | 2–3 bullet strings shown on Role Reveal screen while player holds button. | No |
| `uiPromptNight` | `str` | Text displayed on the Mobile night-phase action screen header. Non-acting roles (wakeOrder=0) show the decoy task prompt here. | No |
| `winCondition` | `str` | Key into `roles.json` `winConditions` map. Determines which win check applies to this role. | No |
| `ui.colorToken` | `str` | CSS custom property name for this role's color. E.g., `"--role-wolf"`. Cross-references PRD-003 §5 color tokens. | No |
| `ui.icon` | `str` | SVG asset filename for role icon. | No |
| `ui.revealBackground` | `str` hex | Hex color for Role Reveal screen background while button is held. | No |
| `balanceWeight` | `int` | Signed integer quantifying this role's net impact on game balance. Positive = pro-village. Negative = pro-wolf/chaos. Used by the dynamic composition engine to validate and re-roll pool draws. See `roles.json` `balanceWeightSystem` for the full reference table. | No |

> **Note on Alpha Wolf:** `investigationResult: "village"` is the entire design of this role. The Seer gets a false negative. The server must use `investigationResult` — not `team` — when resolving Seer peeks. Using `team` by mistake silently breaks the Alpha Wolf mechanic.
>
> **Note on Framer + Seer interaction:** Framer's `manipulate` action sets `is_framed_tonight = true` on the target (step 2 of resolution). When the Seer's `inspect` resolves (step 6), the server checks `is_framed_tonight` first: if `true`, the result is forced to `"wolf"` regardless of `investigationResult`. This means a Framer can make an Alpha Wolf appear as Werewolf to the Seer — the Framer's effect overrides the Alpha Wolf's disguise. `is_framed_tonight` is reset to `false` at the start of every new night phase.
>
> **Note on Framer Archives Hack:** When `framer_action == "hack_archives"`, `framer_target_id` is `null` and `is_framed_tonight` is not set on any player. Instead, `false_hint_queued = true` and `false_hint_payload` is stored server-only. The Tracker observing the Framer sees `tracker_result: []` — `"archives"` is not a player ID and is not reported. The Framer receives no confirmation that any delivery occurred. If no `wakeOrder=0` player solves a puzzle that round, `false_hint_queued` is cleared at phase transition with no delivery.
>
> **Note on Cupid Lovers:** `lovers_pair` is set in `MasterGameState`. The two linked players each receive `lovers_partner_id` in their own `PlayerState` strip. No other player or the Display client receives this field until `game_over`. The link is permanent — it cannot be broken. Death chain can create cascading Hunter / Serial Killer / Arsonist interactions.

---

## MasterGameState (Top-Level)

| Field | Type | Description | Source / Logic | Nullable | HiddenFromPlayer |
|:------|:-----|:------------|:---------------|:---------|:----------------|
| `game_id` | `str` (UUID) | Unique identifier for the game session. Used as the Redis key prefix and WebSocket room ID. | Server-generated on `POST /games` | No | No |
| `schema_version` | `str` | Schema version string. Clients compare against `StatePayload.schema_version` for reload detection. | Set at `setup_game()` | No | No |
| `seed` | `str` | Master PRNG seed used for role assignment shuffle. Stored for post-game replay and audit. | Server-generated or host-supplied at setup | No | No |
| `phase` | `str` enum | Current game phase. One of `"lobby"` \| `"role_deal"` \| `"night"` \| `"day"` \| `"day_vote"` \| `"hunter_pending"` \| `"game_over"`. `"hunter_pending"` is a blocking sub-phase inserted after any Hunter elimination — it exits back to the previous phase type after the Hunter fires or times out. | Phase machine FSM — advanced by `transition_phase()` | No | No |
| `round` | `int` | Current round number. Starts at `1`. Increments each time `transition_phase()` targets `"night"` and the current phase is not `"lobby"` or `"role_deal"` — i.e., every night entry after the first. | `transition_phase()` on any→night (except lobby/role_deal→night) | No | No |
| `host_player_id` | `str` | Player ID of the session host. Host has permission to start the game and advance timers manually. | Set on `POST /games` | No | No |
| `timer_ends_at` | `str` ISO8601 UTC \| `null` | Absolute timestamp when the current timed phase expires. `null` only during `lobby` and `game_over`. Timed phases: `night`, `day`, `day_vote`, `role_deal`, `hunter_pending`. Server-owned — clients derive displayed countdown from `(timer_ends_at − Date.now())` only. **Never use client-side `setInterval` as source of truth.** | Set by `transition_phase()` on each timed phase entry; cancelled by `resolve_night()` on early auto-advance | Yes | No |
| `players` | `map[str → PlayerState]` | All players in the game, keyed by `player_id` (e.g., `"p1"`, `"p2"`). | Populated on `POST /games/{id}/join`; mutated through the game | No | Partial — see PlayerState |
| `night_actions` | `NightActions` | Current round's submitted night actions. Reset to empty at the start of each night phase. | Mutated by `submit_night_action`; resolved by `resolve_night()` | No | **Yes — heavily stripped per role** |
| `day_votes` | `map[str → str]` | Maps voter `player_id` → target `player_id`. Updated live as votes arrive during `"day_vote"` phase. | Mutated by `submit_day_vote`; cleared at phase reset | No | No |
| `elimination_log` | `array[EliminationEvent]` | Append-only ordered list of all player eliminations. Roles in events are hidden until `game_over`. | Appended by `resolve_night()` and `resolve_day_vote()` | No (empty until first elimination) | Partial — see EliminationEvent |
| `winner` | `str` enum \| `null` | Winning team. `"village"` \| `"werewolf"` \| `"neutral"` \| `null`. Set by `check_win_condition()` after every elimination. Neutral wins are role-specific (see `winner_player_id`). | `check_win_condition()` — runs after every elimination event including Hunter revenge | Yes | No |
| `winner_player_id` | `str` \| `null` | Set only for neutral solo wins (Jester, Serial Killer). Identifies the specific winning player. `null` for team wins and during live play. | `check_win_condition()` | Yes | No |
| `seer_knowledge` | `map[str → str]` | Maps target `player_id` → `investigationResult` string for every player the Seer has investigated. Accumulates across rounds. Values: `"village"` \| `"werewolf"` \| `"neutral"`. Note: reflects `investigationResult` — Alpha Wolf returns `"village"` here. | Mutated by `resolve_night()` when processing seer's `seer_target_id` | No (empty map until Seer acts) | **Yes — sent only to the Seer; removed for all others** |
| `hunter_queue` | `array[str]` | Ordered list of Hunter player IDs eliminated this resolution step who have not yet fired. Non-empty only during `hunter_pending`. Win check blocked until empty. | Set when Hunter is eliminated; popped by `resolve_hunter_revenge()` | No (empty array) | No |
| `lovers_pair` | `array[str, str]` \| `null` | The two player IDs linked by Cupid. `null` if no Cupid in game or before Cupid acts. Permanent once set — cannot be unlinked. Both linked players receive `lovers_partner_id` in their stripped state. Display client receives this only in `game_over` broadcast. | Set by `resolve_night()` step 3 (Cupid link) in round 1 | Yes | **Yes — sent only to the two linked players during live play; full value revealed at `game_over`** |
| `tracker_knowledge` | `map[str → array[str]]` | Maps round number (as string key) → list of player IDs the Tracker's chosen target visited that round. Accumulates across rounds. `{}` until Tracker acts. Example: `{"1": ["p3"], "2": []}` | Populated by `resolve_night()` step 11 (Tracker result) | No (empty map) | **Yes — sent only to the Tracker; removed for all others** |
| `config` | `GameConfig` | Host-configured game settings (timers, role set). Frozen at game start. | Set by host on `POST /games` | No | No |
| `role_registry` | `map[str → RoleDefinition]` | Read-only copy of `roles.json` filtered to roles active in this game. Sent to clients on initial `state_update`. Never changes after game start. | Loaded from `roles.json` at `setup_game()` | No | No |

---

## GameConfig

Frozen at game start. Host sets these in the lobby before pressing Start.

| Field | Type | Description | Default | Nullable |
|:------|:-----|:------------|:--------|:---------|
| `night_timer_seconds` | `int` | Duration of the night phase timer. Auto-advance fires early if all active roles submit. | `60` | No |
| `day_timer_seconds` | `int` | Duration of the discussion sub-phase timer before voting opens. | `180` | No |
| `vote_timer_seconds` | `int` | Duration of the voting sub-phase timer. | `90` | No |
| `role_deal_timer_seconds` | `int` | Grace period for all players to confirm role reveal before auto-advancing. | `30` | No |
| `hunter_pending_timer_seconds` | `int` | Window for the Hunter to fire their revenge shot before auto-skipping. | `30` | No |
| `player_count` | `int` | Total number of players. Range: 5–18. | Set at game creation | No |
| `roles` | `map[str → int]` | Role ID → count for this session. Must sum to `player_count`. Validated against `roles.json` on setup. Example: `{"villager": 4, "werewolf": 2, "seer": 1, "doctor": 1}`. Generated by the dynamic composition engine: server selects the matching `dynamicTemplates` range, fills guaranteed roles, draws from `flexPools`, and runs the `balanceWeightSystem` check. Final resolved composition is frozen here at game start. | Resolved by `build_composition(player_count)` using `roles.json` `dynamicTemplates`; stored frozen at `setup_game()` | No |

---

## PlayerState

| Field | Type | Description | Source / Logic | Nullable | HiddenFromPlayer |
|:------|:-----|:------------|:---------------|:---------|:----------------|
| `player_id` | `str` (UUID) | Unique player identifier. Server-generated UUID on join. E.g., `"p1"` is used only in tests — production IDs are `uuid4()` strings. | `POST /games/{id}/join` | No | No |
| `display_name` | `str` | Name chosen by the player at onboarding. Max 16 characters. | Player-supplied at join | No | No |
| `avatar_id` | `str` | Key into the static avatar asset registry. E.g., `"wolf_01"`, `"village_03"`. | Player-chosen at onboarding | No | No |
| `is_connected` | `bool` | Whether this player currently has an active WebSocket connection. Used to show disconnected-player indicator on Display lobby. | Updated on WebSocket connect/disconnect | No | No |
| `role` | `str` enum \| `null` | The player's secret role. One of: `"villager"` \| `"werewolf"` \| `"alpha_wolf"` \| `"wolf_shaman"` \| `"framer"` \| `"seer"` \| `"doctor"` \| `"tracker"` \| `"cupid"` \| `"infector"` \| `"arsonist"` \| `"mayor"` \| `"hunter"` \| `"jester"` \| `"serial_killer"`. `null` during `lobby` phase (before assignment). | Assigned by `assign_roles()` at game start using shuffled PRNG draw | Yes | **Yes — sent only to own player, wolf-team teammates, and dead/game_over spectators** |
| `team` | `str` enum \| `null` | Faction membership. `"village"` \| `"werewolf"` \| `"neutral"`. `null` during lobby. Derived from `role` via `roles.json`. Used for team win condition checks. **Distinct from `investigationResult`** — do not use `team` in Seer logic. | Derived from `role` on assignment | Yes | **Yes — same stripping rules as `role`** |
| `hunter_fired` | `bool` | Tracks whether this Hunter has used their revenge kill. Server rejects `HUNTER_REVENGE` if `true`. Only present on Hunter players. | `false` at assignment; set `true` by `resolve_hunter_revenge()` | No | **Yes — server-only** |
| `is_framed_tonight` | `bool` | Set to `true` by the Framer's `manipulate` action (resolution step 2). Forces Seer's result to `"werewolf"` at step 6 regardless of actual `investigationResult`. Reset to `false` at start of every night phase. | Set by `resolve_night()` step 2; reset by `transition_phase("night")` | No | **Yes — server-only; never sent to clients** |
| `doused_player_ids` | `array[str]` | List of player IDs doused by the Arsonist. Accumulates across rounds. Only present on the Arsonist's own `PlayerState` entry. Persists even if doused player dies — dead players in the list are skipped during ignite. | Appended by `resolve_night()` step 8 on each douse action | No (empty array) | **Yes — sent only to the Arsonist; server-only for all others** |
| `infect_used` | `bool` | Whether the Infector has consumed their one infection. Server rejects `convert` action if `true`. Only present on Infector players. | `false` at assignment; set `true` by `resolve_night()` step 7 on infection | No | **Yes — server-only** |
| `lovers_partner_id` | `str` \| `null` | The partner player ID for a Lover. `null` for all non-Lover players. Sent only to the linked player in their own strip — they see their partner's ID but not the Cupid's identity. | Set by `resolve_night()` step 3 | Yes | **Yes — sent only to the linked player themselves; null for all others** |
| `is_alive` | `bool` | Whether the player is still in the game. | `true` at game start; set to `false` by `resolve_night()` or `resolve_day_vote()` | No | No |
| `is_protected` | `bool` | Whether the Doctor chose this player for protection this round. Evaluated during `resolve_night()`. Reset to `false` at start of each night phase. | Set by `resolve_night()` when processing `doctor_target_id` | No | **Yes — server-only; never sent to any client** |
| `last_protected_player_id` | `str` \| `null` | Player ID the Doctor protected last round. Enforces the consecutive-protect ban. Server-only field. | Set by `resolve_night()` when the Doctor acts. Only present on the Doctor's own PlayerState entry. | Yes | **Yes — server-only; never sent to any client** |
| `night_action_submitted` | `bool` | Whether this player has submitted their night action this round. Reset to `false` at night phase start. | Set to `true` by `submit_night_action()` | No | **Yes — visible to own player and wolf teammates only. Display client receives aggregate count via `actions_submitted_count`, not individual booleans** |
| `role_confirmed` | `bool` | Whether this player has held the "Hold to Reveal" button long enough to confirm they've seen their role. Used to gate the `role_deal` → `night` auto-advance. | Set by `confirm_role_reveal` intent | No | No |
| `session_token` | `str` \| `null` | Opaque reconnect token. Set on join; re-issued on `/rejoin`. Stored in browser `sessionStorage` key `wolf_token`. Allows seamless reconnect on page refresh. | Server-generated UUID on join | Yes | **Yes — sent only to own player on join/rejoin; never in state broadcasts** |
| `puzzles_solved_count` | `int` | Total puzzles the player has solved correctly across all rounds. Used by the Archives system to track engagement; not surfaced to other players. Only present on players with `wakeOrder == 0`. | Incremented by `resolve_puzzle()` on correct answer | No | **Yes — sent only to own player** |
| `hints_received` | `array[str]` | List of `hint_id` strings for hints delivered to this player. Used as a deduplication registry — server checks this before delivering a new hint to prevent re-send on reconnect. Only present on players with `wakeOrder == 0`. | Appended by hint delivery handler | No (empty array) | **Yes — server-only; never sent in state broadcasts** |

> **`display_name` is not re-sent in every state broadcast** — it is included in `PlayerState` only for the game duration convenience. The canonical join-time name record lives in Redis match metadata (`meta:{game_id}:roster`).

---

## NightActions

Holds the current round's night action submissions. Fully reset at the start of each `night` phase. The server resolves these in a fixed order during `resolve_night()` — see `roles.json` `nightResolutionOrder` for the authoritative sequence.

| Field | Type | Description | Source / Logic | Nullable | HiddenFromPlayer |
|:------|:-----|:------------|:---------------|:---------|:----------------|
| `wolf_votes` | `map[str → str]` | Maps wolf-team `player_id` → chosen kill target `player_id`. Majority wins; ties result in no kill. Populated by all three wolf roles: `werewolf`, `alpha_wolf`, `wolf_shaman`. | `submit_night_action` for wolf-team players | No (empty map) | **Yes — wolf-team players only. Removed for all village, neutral, and Display client** |
| `roleblock_target_id` | `str` \| `null` | Player ID hexed by the Wolf Shaman this round. That player's night ability is nullified before any other resolution. | `submit_night_action` secondary action from `wolf_shaman` only | Yes | **Yes — server-only; never sent to any client** |
| `seer_target_id` | `str` \| `null` | The player ID the Seer chose to inspect this round. | `submit_night_action` for Seer | Yes | **Yes — sent only to the Seer** |
| `seer_result` | `str` enum \| `null` | Result of the Seer's inspect this round. Returns `investigationResult` field of the target — `"village"` \| `"wolf"` \| `"neutral"`. **Uses `investigationResult`, not `team`** — Alpha Wolf returns `"village"` here. Stored transiently for broadcast; cumulative record lives in `MasterGameState.seer_knowledge`. | Computed by `resolve_night()` from `players[seer_target_id].investigationResult` | Yes | **Yes — sent only to the Seer** |
| `doctor_target_id` | `str` \| `null` | The player ID the Doctor chose to protect this round. | `submit_night_action` for Doctor | Yes | **Yes — server-only; never sent to any client** |
| `serial_killer_target_id` | `str` \| `null` | Player ID the Serial Killer chose to eliminate. | `submit_night_action` for Serial Killer | Yes | **Yes — Serial Killer only; server-only until `game_over`** |
| `framer_action` | `str` enum \| `null` | Framer's mode this round: `"frame"` \| `"hack_archives"` \| `null` (not yet submitted). When `"frame"`, `framer_target_id` is set and `is_framed_tonight` fires at step 2. When `"hack_archives"`, `framer_target_id` is `null` and `false_hint_queued` is set instead. | `submit_night_action` for Framer | Yes | **Yes — server-only; never sent to any client** |
| `framer_target_id` | `str` \| `null` | Player ID the Framer chose to frame this round. Only set when `framer_action == "frame"`. On resolution, sets `is_framed_tonight = true` on this player before the Seer resolves. `null` when `framer_action == "hack_archives"`. | `submit_night_action` for Framer | Yes | **Yes — server-only; never sent to any client** |
| `false_hint_queued` | `bool` | `true` when the Framer chose `hack_archives` this round and the crafted false hint is waiting for delivery. Checked by the hint delivery handler when any `wakeOrder=0` player solves a puzzle — if `true`, delivers `false_hint_payload` instead of a real hint. Reset to `false` at the start of each night phase. | Set by `resolve_night()` step 2 when `framer_action == "hack_archives"`; reset by `transition_phase("night")` | No | **Yes — server-only; never sent to any client** |
| `false_hint_payload` | `FalseHintPayload` \| `null` | The fabricated hint queued by the Framer. Non-null only when `false_hint_queued == true`. `is_fabricated` flag is stripped before unicast delivery — the receiving client gets a schema-identical standard `HintPayload`. | Set by `resolve_night()` step 2; cleared at phase reset | Yes | **Yes — server-only; `is_fabricated` stripped before delivery; client payload is identical to real `HintPayload`** |
| `arsonist_action` | `str` enum \| `null` | The Arsonist's choice this round: `"douse"` \| `"ignite"` \| `null` (not yet submitted). | `submit_night_action` for Arsonist | Yes | **Yes — Arsonist only; server-only for all others** |
| `arsonist_douse_target_id` | `str` \| `null` | Target to add to `doused_player_ids`. Only set when `arsonist_action == "douse"`. `null` when igniting. | `submit_night_action` for Arsonist | Yes | **Yes — Arsonist only** |
| `infector_target_id` | `str` \| `null` | Player ID the Infector chose to infect this round. `null` = Infector skipped (wolf kill proceeds). Non-null cancels wolf kill and queues conversion. | `submit_night_action` for Infector | Yes | **Yes — server-only; wolf team sees pack kill vote but not the infect decision** |
| `cupid_link` | `array[str, str]` \| `null` | The two player IDs Cupid linked. Only present in round 1. Immediately written to `MasterGameState.lovers_pair` on resolution. | `submit_night_action` for Cupid, round 1 only | Yes | **Yes — server-only during resolution; Cupid sees both linked IDs in their own strip** |
| `tracker_target_id` | `str` \| `null` | Player ID the Tracker chose to follow this round. | `submit_night_action` for Tracker | Yes | **Yes — Tracker only** |
| `tracker_result` | `array[str]` | Computed at resolution step 11. List of player IDs the tracked player targeted with a night action this round. Empty if tracked player was roleblocked, had `wakeOrder == 0`, or submitted no action. Stored to `tracker_knowledge[round]` after broadcast. | Computed from other `night_actions` fields post-resolution | No (empty array) | **Yes — Tracker only; server-only for all others** |
| `roleblocked_player_id` | `str` \| `null` | Computed at step 1: the player whose action is nullified this round. Any action submitted by this player is discarded. | Computed from `roleblock_target_id` at resolution start | Yes | **Yes — server-only** |
| `actions_submitted_count` | `int` | Count of players with `wakeOrder > 0` (accounting for `night_one_only` after round 1) who have submitted. Computed at broadcast time. | `sum(p.night_action_submitted for active_role_players)` | No | No — public. Display: `"X / Y players have acted"` |
| `actions_required_count` | `int` | Total players with `wakeOrder > 0` this round. Cupid is excluded after round 1. | Computed from living players' roles at phase entry | No | No — public |
| `puzzle_state` | `PuzzleState` \| `null` | Active puzzle for a `wakeOrder == 0` player this night round. `null` for all players with `wakeOrder > 0`, and for all wakeOrder=0 players outside the night phase. Sent only in the individual player's own strip — never broadcast globally. | Set by `start_night_phase()` for each eligible player; cleared on phase transition | Yes | **Yes — sent only to the eligible player; null in all other strips** |

---

## EliminationEvent

Appended to `MasterGameState.elimination_log` by `resolve_night()` and `resolve_day_vote()`.

| Field | Type | Description | Source / Logic | Nullable | HiddenFromPlayer |
|:------|:-----|:------------|:---------------|:---------|:----------------|
| `round` | `int` | Round number when elimination occurred. | `MasterGameState.round` at time of resolution | No | No |
| `phase` | `str` enum | Phase that caused the elimination. `"night"` \| `"day"`. | Current phase at resolution | No | No |
| `player_id` | `str` | The player who was eliminated. | Set by resolver | No | No |
| `cause` | `str` enum | How they died. `"wolf_kill"` \| `"village_vote"` \| `"arsonist_ignite"` \| `"serial_killer_kill"` \| `"broken_heart"` \| `"hunter_revenge"`. | Set by resolver | No | No |
| `role` | `str` enum \| `null` | The eliminated player's true role. **Hidden until `game_over`** — sent as `null` in `elimination_log` entries during live play. Populated in final `game_over` broadcast. | `players[player_id].role` at time of elimination | Yes | **Yes — null during live play; revealed in `game_over` state broadcast** |
| `saved_by_doctor` | `bool` | `true` if the Doctor's protection blocked a wolf kill targeting this player on the same night (player survived). This flag is only included in the `game_over` broadcast — during live play the Doctor's success is silent. | Set by `resolve_night()` when `is_protected == true` on wolf's target | No | **Yes — included only in `game_over` broadcast** |

---

## GameConfig (Reconstituted for game_over broadcast)

On `game_over`, the server adds a `post_match` object to the state payload containing the full event timeline for the Game Over screen's elimination timeline animation (PRD-002 §2.6).

| Field | Type | Description | Nullable |
|:------|:-----|:------------|:---------|
| `post_match.timeline` | `array[TimelineEvent]` | Ordered list of key game events for the post-match reveal. Constructed server-side from `elimination_log`, `night_actions` history, and `seer_knowledge`. | No |
| `post_match.winner` | `str` | `"village"` \| `"werewolf"` \| `"neutral"` | No |
| `post_match.rounds_played` | `int` | Total rounds completed. | No |

### TimelineEvent

| Field | Type | Description |
|:------|:-----|:------------|
| `round` | `int` | Round this event occurred in |
| `phase` | `str` | `"night"` \| `"day"` |
| `event_type` | `str` enum | `"wolf_kill"` \| `"doctor_save"` \| `"village_vote"` \| `"seer_peek"` |
| `actor_id` | `str` \| `null` | Player who performed the action (null for events with no single actor, e.g. consensus wolf kill) |
| `target_id` | `str` \| `null` | Player targeted by the action |
| `display_text` | `str` | Pre-formatted display string for the Game Over timeline, e.g. `"Jordan was saved by the Doctor"`. Generated server-side. |

---

## DynamicTemplate

One entry per player-count range in `roles.json` `dynamicTemplates`. The server selects the matching template at `setup_game()` and resolves it into a frozen `GameConfig.roles` map.

| Field | Type | Description | Nullable |
|:------|:-----|:------------|:---------|
| `playerCount.min` | `int` | Inclusive lower bound of this template's player count range. | No |
| `playerCount.max` | `int` | Inclusive upper bound of this template's player count range. | No |
| `guaranteed` | `map[str → int]` | Role ID → count. These roles are always included regardless of pool draws. | No |
| `flexPools` | `array[FlexPool]` | Ordered list of role pools drawn in sequence. Each pool contributes 0–N roles to the composition. | No |

## FlexPool

One draw pool within a `DynamicTemplate`.

| Field | Type | Description | Nullable |
|:------|:-----|:------------|:---------|
| `type` | `str` | Human-readable pool category label. E.g., `"protection"`, `"wolf_support"`, `"chaos_neutral"`, `"filler"`. Not machine-interpreted — for documentation and debug logging only. | No |
| `picks` | `int` \| `"remaining_slots"` | Number of roles to draw from this pool. `"remaining_slots"` means fill all un-assigned slots — used only on the final filler pool. | No |
| `rerollable` | `bool` | If `true`, this pool is eligible for one re-draw when the composition's balance sum falls outside `balanceWeightSystem.targetRange`. Filler pools are always `false`. | No |
| `options` | `array[str]` | Role IDs to sample from (with replacement). `"none"` is a valid option — selecting it contributes no role for that pick. Duplicates in the array increase selection probability. | No |

---

## PuzzleState

Ephemeral object in `NightActions.puzzle_state`. Present only for `wakeOrder == 0` players during the `night` phase. Stripped from all other players' views.

| Field | Type | Description | Nullable |
|:------|:-----|:------------|:---------|
| `active` | `bool` | `true` while the puzzle window is open and awaiting a `submit_puzzle_answer` intent. Set to `false` on correct answer, timeout, or wrong answer. | No |
| `puzzle_type` | `str` enum | One of `"math"` \| `"logic"` \| `"sequence"`. Determines how `puzzle_data` is structured. | No |
| `puzzle_data` | `object` | Type-specific puzzle content. **math:** `{ "expression": str, "answer_options": [str, str, str], "correct_index": int }`. **logic:** `{ "question": str, "answer_options": [str, str], "correct_index": int }` — question drawn from `puzzles.md` static bank (400 trivia Q&A, project root); distractors generated server-side. **sequence:** `{ "sequence": [str] }` — list of color IDs to replay. | No |
| `time_limit_seconds` | `int` | Seconds until puzzle times out. Derived from `archivePuzzleSystem.puzzleTypes[puzzle_type].timeLimitSeconds`. | No |
| `solved` | `bool` \| `null` | `null` while active. `true` if player answered correctly. `false` on timeout or wrong answer. | Yes |
| `hint_pending` | `bool` | Briefly `true` after a correct solve while the server constructs and dispatches the `HintPayload` unicast. Clients may use this to show a brief "clue incoming..." indicator. | No |

> **`puzzle_data.correct_index` stripping:** The `correct_index` field within `puzzle_data` is **never sent to the client**. It is server-only. The client receives `expression` and `answer_options` only, and submits their selection index via `submit_puzzle_answer`. The server validates against its stored `correct_index`.

---

## HintPayload

Unicast message sent server → solving player only, immediately after a correct puzzle solve. Not part of the global `StatePayload` broadcast. Never visible to the Display client or other players.

| Field | Type | Description | Nullable |
|:------|:-----|:------------|:---------|
| `type` | `str` | Always `"hint_reward"`. Discriminates this message from `"state_update"` and `"error"`. | No |
| `hint_id` | `str` (UUID) | Unique identifier for this hint delivery. Stored in `PlayerState.hints_received` to prevent re-delivery on reconnect. | No |
| `category` | `str` enum | One of the `archivePuzzleSystem.hintCategories[].id` values: `"wolf_count"` \| `"no_role_present"` \| `"role_present"` \| `"neutral_exists"` \| `"seer_blocked_last_night"`. | No |
| `text` | `str` | Pre-formatted hint string ready for display. E.g., `"There are 3 Wolves total in this game."`. Generated server-side from the category template. | No |
| `round` | `int` | Round number when the hint was earned. | No |
| `expires_after_round` | `int` \| `null` | Round number after which this hint is stale. `null` = permanent (composition-derived hints). Set to `(round + 1)` for behavioral hints that reference the previous night's events. | Yes |

---

## FalseHintPayload

Server-internal variant of `HintPayload` used when the Framer hacks The Archives. Stored in `NightActions.false_hint_payload`. **Never sent to any client directly.** Before unicast delivery, the server calls `strip_fabricated_flag()` which returns a standard `HintPayload` — schema-identical to a real hint.

| Field | Type | Description | Nullable | Sent to client? |
|:------|:-----|:------------|:---------|:----------------|
| `type` | `str` | Always `"hint_reward"`. | No | Yes (same as HintPayload) |
| `hint_id` | `str` (UUID) | UUID generated at step 2 resolution. Used for deduplication in `PlayerState.hints_received`. Same `hint_id` delivered to all solvers that round. | No | Yes |
| `category` | `str` enum | One of the Framer-allowed categories: `"wolf_count"` \| `"no_role_present"` \| `"role_present"`. | No | Yes |
| `text` | `str` | Pre-formatted false hint string as crafted by the Framer. E.g., `"There IS a Doctor in this game."`. Not generated from composition truth — taken verbatim from the `submit_night_action` intent's `false_hint_text` field. | No | Yes |
| `round` | `int` | Round number when the false hint was queued. | No | Yes |
| `expires_after_round` | `int` \| `null` | Expiry rule. `null` for composition-category false hints (permanent — this creates lasting misinformation). | Yes | Yes |
| `is_fabricated` | `bool` | Always `true`. Server-internal audit flag. **Stripped before unicast — client payload never includes this field.** | No | **No — stripped** |

> **Stripping invariant:** `strip_fabricated_flag(FalseHintPayload) -> HintPayload` must exclude `is_fabricated` and no other fields. Any future field added to `FalseHintPayload` that is also in `HintPayload` is sent; any field unique to `FalseHintPayload` must be explicitly excluded.

---

## Reconnect Token (Mobile sessionStorage)

Stored under key `wolf_session` in browser `sessionStorage`. Enables seamless reconnect on page refresh without re-entering name or re-scanning QR.

| Field | Type | Description | Nullable |
|:------|:-----|:------------|:---------|
| `game_id` | `str` | The game this player belongs to | No |
| `player_id` | `str` | Player slot ID (e.g., `"p1"`) | No |
| `session_token` | `str` | Opaque auth token. Re-issued on each `/rejoin`. | No |
| `display_name` | `str` | Name stored to skip re-entry on reconnect form | No |

**Written by:** Mobile join handler on `POST /games/{id}/join` response.
**Read by:** Mobile `App.tsx` mount effect — if token present and valid, auto-reconnects without showing onboarding form.
**Cleared by:** `clearSession()` — only when the game ends (`game_over` broadcast) or player explicitly chooses "Leave Game".

---

## WebSocket Intent Payloads (Mobile → Server)

All intents include `game_id`, `player_id`, `state_id` (stale-state fence), and a `type` discriminator. The server rejects any intent whose `state_id` does not match the current server `state_id`.

```jsonc
// Lobby → Role Deal (host only)
{ "type": "start_game",           "game_id": "uuid", "player_id": "p1", "state_id": 0 }

// Role Deal phase — all players
{ "type": "confirm_role_reveal",  "game_id": "uuid", "player_id": "p1", "state_id": 1 }

// Night phase — village / neutral roles with wakeOrder > 0
{ "type": "submit_night_action",  "game_id": "uuid", "player_id": "p1", "state_id": 4,
  "target_id": "p5" }

// Night phase — Wolf Shaman only (two targets: pack kill + hex)
{ "type": "submit_night_action",  "game_id": "uuid", "player_id": "p2", "state_id": 4,
  "target_id": "p5",              // pack kill vote
  "secondary_target_id": "p3"     // roleblock hex target
}

// Night phase — Cupid (round 1 only, two linked targets)
{ "type": "submit_night_action",  "game_id": "uuid", "player_id": "p7", "state_id": 4,
  "link_target_a": "p2",
  "link_target_b": "p5"
}

// Night phase — Arsonist (douse)
{ "type": "submit_night_action",  "game_id": "uuid", "player_id": "p9", "state_id": 4,
  "arsonist_action": "douse",
  "target_id": "p3"
}

// Night phase — Arsonist (ignite — no target_id needed)
{ "type": "submit_night_action",  "game_id": "uuid", "player_id": "p9", "state_id": 4,
  "arsonist_action": "ignite"
}

// Night phase — Infector (use infection)
{ "type": "submit_night_action",  "game_id": "uuid", "player_id": "p4", "state_id": 4,
  "target_id": "p6"               // non-null = use infection this round
}

// Night phase — Infector (skip infection, proceed with wolf kill)
{ "type": "submit_night_action",  "game_id": "uuid", "player_id": "p4", "state_id": 4,
  "target_id": null               // null = skip; wolf kill from wakeOrder=1 vote proceeds
}

// Day discussion → voting (host only, advances timer early)
{ "type": "advance_phase",        "game_id": "uuid", "player_id": "p1", "state_id": 7 }

// Day Vote phase — all living players
{ "type": "submit_day_vote",      "game_id": "uuid", "player_id": "p1", "state_id": 8,
  "target_id": "p3" }

// Hunter pending sub-phase — Hunter only, fires immediately after elimination
{ "type": "hunter_revenge",       "game_id": "uuid", "player_id": "p6", "state_id": 11,
  "target_id": "p4" }

// Night phase — Framer (traditional frame)
{ "type": "submit_night_action",  "game_id": "uuid", "player_id": "p3", "state_id": 4,
  "framer_action": "frame",
  "target_id": "p6" }

// Night phase — Framer (Archives hack)
{ "type": "submit_night_action",  "game_id": "uuid", "player_id": "p3", "state_id": 4,
  "framer_action": "hack_archives",
  "false_hint_category": "role_present",
  "false_hint_text": "There IS a Doctor in this game." }

// Night phase — wakeOrder=0 players (Villager, Mayor, Jester, post-round-1 Cupid)
// multiple_choice puzzle: answer_index is 0-based index into puzzle_state.puzzle_data.answer_options
{ "type": "submit_puzzle_answer", "game_id": "uuid", "player_id": "p8", "state_id": 4,
  "answer_index": 2 }

// Night phase — wakeOrder=0 players — sequence puzzle: answer_sequence is the tapped color IDs in order
{ "type": "submit_puzzle_answer", "game_id": "uuid", "player_id": "p8", "state_id": 4,
  "answer_sequence": ["red", "blue", "red", "green"] }
```

> **`hunter_pending` sub-phase:** When a Hunter is eliminated, the server broadcasts `phase: "hunter_pending"` and `hunter_queue: ["p6"]`. All other clients see the interstitial. Only the Hunter's client renders the target selector. The game does not advance until `hunter_revenge` is submitted or a 30-second timeout fires (server auto-picks the wolf kill target as revenge if timed out).
