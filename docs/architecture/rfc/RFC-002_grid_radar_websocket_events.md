# RFC-002: Werewolf — Grid & Radar WebSocket Event Protocol

## Status
Proposed

## Date
2026-04-15

## Context

PRD-013 (Night Grid + Wolf Radar) introduces three new client→server intents and one new server→client side-channel event. This RFC governs the exact message formats, delivery guarantees, security rules, and integration with the existing ADR-007 (WebSocket Message Type Protocol) and ADR-004 (Connection Protocol).

The existing intent dispatch loop (`api/intents/handlers.py`) handles all client messages. The existing `broadcast_raw()` path in `connection_manager.py` handles side-channel events like `wolf_kill_queued` and `sound_triggered`. Both extension points are well-established.

This RFC addresses two novel concerns not covered by ADR-007:
1. **A new side-channel event (`grid_ripple`)** that must fire immediately at the moment of node completion, before the full state broadcast arrives, to enable smooth radar animation.
2. **New view-restricted state fields** in `NightActions` that must be added to the stripper without creating information leakage vectors.

---

## Proposed Protocol

### 1. New Client → Server Intents

All three intents follow the existing intent envelope `{ "type": "<intent_name>", ...fields }` sent over the player's WebSocket connection. They are processed by the existing `handle_intent()` dispatcher.

#### 1.1 `select_grid_node`

```jsonc
{
  "type": "select_grid_node",
  "row": 2,     // integer [0, 4]
  "col": 3      // integer [0, 4]
}
```

**Server action:** Assigns a `PuzzleState` to `G.players[player_id].grid_puzzle_state` based on the tier at `G.night_actions.grid_layout[row][col]`. Increments `night_action_change_count[player_id]`. Broadcasts state update.

**Error codes:** `WRONG_PHASE`, `NOT_YOUR_TURN` (wakeOrder != 0), `NODE_OCCUPIED` (already in `grid_activity`), `PUZZLE_ALREADY_ACTIVE` (existing `grid_puzzle_state` is active).

#### 1.2 `submit_grid_answer`

```jsonc
{
  "type": "submit_grid_answer",
  "answer_index": 1     // integer [0, 3]
}
```

**Server action:** Validates against `grid_puzzle_state.puzzle_data["correct_index"]` (never sent to client). On correct: generates tier hint, appends `grid_activity`, fires `grid_ripple`, clears position. On wrong: clears puzzle, player can navigate again. Broadcasts state update.

**Error codes:** `WRONG_PHASE`, `NO_ACTIVE_PUZZLE`.

#### 1.3 `sonar_ping`

```jsonc
{
  "type": "sonar_ping",
  "quadrant": "top_right"   // "top_left" | "top_right" | "bottom_left" | "bottom_right"
}
```

**Server action:** Reads `grid_activity` for the given quadrant, computes heat + tier_counts, appends result to `sonar_ping_results`, increments `sonar_pings_used`. Broadcasts state update (wolves see new result).

**Error codes:** `WRONG_PHASE`, `NOT_WOLF` (team != werewolf), `INVALID_QUADRANT`.

---

### 2. New Server → Client Event: `grid_ripple`

#### 2.1 Message Format

```jsonc
{
  "type": "grid_ripple",
  "quadrant": "bottom_left",    // which quadrant completed
  "tier": 2                     // 1 | 2 | 3 — drives animation color on radar
}
```

#### 2.2 Delivery Target

`grid_ripple` is delivered **only to wolf-team players** via the existing `broadcast_raw()` mechanism, filtered by team. This uses the same delivery path as `wolf_kill_queued`.

Pseudo-code:
```python
wolf_pids = [pid for pid, p in G.players.items() if p.is_alive and p.team == "werewolf"]
for pid in wolf_pids:
    await manager.unicast_raw(G.game_id, pid, {"type": "grid_ripple", "quadrant": q, "tier": t})
```

If `unicast_raw` doesn't exist, `broadcast_raw` with a wolf-only filter. See ADR-004 §3 for the connection manager API.

#### 2.3 Timing

`grid_ripple` fires **before** the state broadcast in `handle_submit_grid_answer`. This ensures wolf clients receive the animation trigger before the state update, allowing the animation to start immediately rather than waiting for the full JSON state parse.

Ordering:
```
1. validate answer
2. update G (grid_activity, grid_puzzle_state.solved, hint_pending)
3. unicast hint_reward → player
4. unicast grid_ripple → all wolves    ← side-channel, fires first
5. manager.broadcast(game_id, G)       ← full state update, fires second
```

#### 2.4 Why a Side-Channel vs. Embedded in State

State broadcasts require stripping and serializing the full `MasterGameState` (~2–5 KB JSON). The ripple animation should start within ~16ms of the node solve to feel real-time. By sending `grid_ripple` as a 3-field message immediately, we decouple the animation trigger from the state serialization pipeline.

This matches the existing `wolf_kill_queued` pattern (ADR-007 §4): a minimal side-channel event fires for audio/visual effects; the full state update follows.

---

### 3. State Fields — View Restrictions

The following new `NightActions` fields require explicit stripper rules.

| Field | Display | Wolf | Villager (baseline) | Dead |
|-------|---------|------|---------------------|------|
| `grid_layout` | ✓ (tier map only, no secrets) | ✓ | ✓ | — |
| `grid_activity` | — | ✓ (anonymized) | — | — |
| `sonar_pings_used` | ✓ | ✓ | ✓ | — |
| `sonar_ping_results` | — | ✓ | — | — |
| `night_action_change_count` | — | — | — | — |

**`grid_activity` anonymization invariant:** Entries in `grid_activity` contain `{row, col, quadrant, sequence_idx}` only. No `player_id` field is ever written into `grid_activity`. This is enforced at write time in `handle_submit_grid_answer`, not at strip time.

**`night_action_change_count` strip rule:** Added to `_ALWAYS_STRIP_NIGHT_ACTION_FIELDS`. The server uses this field to generate `action_log` hints but never exposes raw counts to any client. The hint text reveals only the anonymized maximum count.

The new `PlayerState` fields `grid_node_row`, `grid_node_col` are server-only position tracking. They are added to `_ALWAYS_STRIP_PLAYER_FIELDS`. `grid_puzzle_state` is handled identically to the existing `puzzle_state` — stripped from all other players, `correct_index` removed before delivery to the owner.

---

### 4. `_build_na_for_view()` Refactor

To make the stripper maintainable as `NightActions` grows, we extract `_build_na_for_view(na_raw: dict, view: str) -> dict`:

```python
def _build_na_for_view(na_raw: dict, view: str) -> dict:
    """Build the night_actions dict for a specific view type."""
    # Always public
    base = {
        "actions_submitted_count": na_raw.get("actions_submitted_count", 0),
        "actions_required_count": na_raw.get("actions_required_count", 0),
        "sonar_pings_used": na_raw.get("sonar_pings_used", 0),
        "grid_layout": na_raw.get("grid_layout"),
    }
    if view == "wolf":
        base["wolf_votes"] = na_raw.get("wolf_votes", {})
        base["grid_activity"] = na_raw.get("grid_activity", [])
        base["sonar_ping_results"] = na_raw.get("sonar_ping_results", [])
    if view == "seer":
        base["seer_target_id"] = na_raw.get("seer_target_id")
        base["seer_result"] = na_raw.get("seer_result")
    if view == "tracker":
        base["tracker_target_id"] = na_raw.get("tracker_target_id")
        base["tracker_result"] = na_raw.get("tracker_result", [])
    if view == "arsonist":
        base["arsonist_action"] = na_raw.get("arsonist_action")
        base["arsonist_douse_target_id"] = na_raw.get("arsonist_douse_target_id")
    return base
```

Each view function calls `s["night_actions"] = _build_na_for_view(state.get("night_actions", {}), view_name)` instead of manually constructing the dict. Future fields require changes only in `_build_na_for_view`.

---

### 5. Quadrant Coordinate Definition

The 5×5 grid is divided into 4 quadrants by row and column midpoint:

```
Rows 0–1, Cols 0–1 = top_left      | Rows 0–1, Cols 2–4 = top_right
-----------------------------------------
Rows 2–4, Cols 0–1 = bottom_left   | Rows 2–4, Cols 2–4 = bottom_right
```

Note: The grid is asymmetric (5×5 doesn't divide evenly). The center row (row 2) and center column (col 2) are assigned to the "right" and "bottom" quadrants respectively. This is a fixed convention hard-coded in `_node_to_quadrant(row, col) -> str`.

```python
def _node_to_quadrant(row: int, col: int) -> str:
    top = row <= 1
    left = col <= 1
    if top and left:   return "top_left"
    if top:            return "top_right"
    if left:           return "bottom_left"
    return "bottom_right"
```

The red node is distributed among any quadrant — its position is randomized per seed. Wolves cannot predict which quadrant hosts the red node before pinging.

---

## Alternatives Considered

### A. Embed ripple data in the state broadcast
**Rejected.** State broadcast latency (serialization + WebSocket frame) adds 20–80ms. Real-time animation quality degrades noticeably. The existing `wolf_kill_queued` side-channel proves the value of minimal-payload triggers.

### B. Long-poll `grid_activity` via REST endpoint for wolf radar
**Rejected.** Contradicts ADR-004 (WebSocket-first protocol). All night-phase data flows over the WebSocket connection. A REST endpoint would require a separate auth check and create two code paths for wolf state access.

### C. Include player position in `grid_activity` but strip before broadcast
**Rejected.** Strip-then-restore is error-prone. Attacker with a modified client could potentially read a field present in the server model before stripping. The safer invariant is: player IDs are never written into `grid_activity` at all (enforced at write time, not strip time).

---

## Consequences

- `broadcast_raw()` in `connection_manager.py` must support filtered delivery (wolf-team only). If not already supported, a `unicast_raw(game_id, player_id, payload)` helper is needed.
- `_build_na_for_view()` replaces inline dict construction in `_wolf_team_view`, `_baseline_alive_view`, `_dead_spectator_view`, `_display_view`. Stripper tests must be updated to assert on the new function's output.
- Three new intent types registered in the dispatcher. Existing intent routing (`handle_intent` switch) requires three new cases.
- Mobile frontend must handle `grid_ripple` WS events as a non-state-update message type (existing pattern: `wolf_kill_queued` is handled in the WS message handler in `useGameState.ts` or equivalent).
