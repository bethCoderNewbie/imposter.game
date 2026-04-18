"""
State Stripper: the security boundary of the Werewolf server.

player_view(G, player_id) is called once per connected socket on every broadcast.
It returns a plain dict (not a Pydantic model) ready for JSON serialization.

INVARIANT: role, team, seer_knowledge, and night_actions details must NEVER appear
in the output for unauthorized recipients. A single missed field = game-breaking cheat.

All six view types:
  display          player_id is None
  wolf_team        alive + team == "werewolf"
  seer             alive + role == "seer"
  village_nonseer  alive + team == "village" + role != "seer"
  neutral_alive    alive + team == "neutral"
  dead_spectator   not is_alive
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from engine.state.enums import Phase
from engine.state.models import MasterGameState

# Fields stripped from ALL views — these are NEVER sent to any client.
_ALWAYS_STRIP_PLAYER_FIELDS = frozenset({
    "is_protected",
    "last_protected_player_id",
    "session_token",
    "hunter_fired",
    "is_framed_tonight",
    "hints_received",
    "infect_used",
    "permanent_id",
    "witch_heal_used",
    "witch_kill_used",
    "lunatic_redirect_used",
    "wise_shield_used",
    # Grid system — server-only position tracking and attack state
    "grid_node_row",
    "grid_node_col",
    "grid_last_quadrant",
    "under_attack",   # restored for own player only in _baseline_alive_view
})

_ALWAYS_STRIP_NIGHT_ACTION_FIELDS = frozenset({
    "roleblock_target_id",
    "doctor_target_id",
    "roleblocked_player_id",
    "false_hint_queued",
    "false_hint_payload",
    "infector_target_id",
    "framer_action",
    "framer_target_id",
    "cupid_link",
    "witch_action",
    "witch_target_id",
    "lunatic_redirect",
    "bodyguard_target_id",
    # Grid system — wolf-only and server-only fields
    "grid_activity",          # wolf view only; restored by _build_na_for_view
    "sonar_ping_results",     # wolf view only; restored by _build_na_for_view
    "night_action_change_count",  # server-only; never sent to any client
    "wolf_charges",               # server-only; never sent to any client
    "charge_kill_target_id",      # server-only; consumed by resolve_night(), never broadcast
})


def player_view(G: MasterGameState, player_id: str | None) -> dict[str, Any]:
    """
    Return a stripped copy of game state appropriate for the given player.
    player_id=None means the Display client (all role data removed).
    Ghost identity is always hidden from other players via _hide_ghost_from_others.
    """
    state = G.model_dump(mode="json", exclude={"host_secret", "rematch_redirect", "lunatic_cursed_wolf_id"})
    is_game_over = G.phase == Phase.GAME_OVER

    # Determine view type
    if player_id is None:
        s = _display_view(state, is_game_over)
    else:
        player = G.players.get(player_id)
        if player is None:
            # Unknown player — treat as display (safest fallback)
            s = _display_view(state, is_game_over)
        elif not player.is_alive:
            s = _dead_spectator_view(state, player_id, is_game_over)
        else:
            team = player.team
            role = player.role
            if team == "werewolf":
                s = _wolf_team_view(state, player_id, G, is_game_over)
            elif role == "seer":
                s = _seer_view(state, player_id, G, is_game_over)
            elif role == "tracker":
                s = _tracker_view(state, player_id, G, is_game_over)
            elif role == "arsonist":
                s = _arsonist_view(state, player_id, G, is_game_over)
            elif role == "witch":
                s = _witch_view(state, player_id, G, is_game_over)
            elif role == "lunatic":
                s = _lunatic_view(state, player_id, G, is_game_over)
            else:
                # village_nonseer, neutral_alive, ghost (alive), and all other roles
                s = _baseline_alive_view(state, player_id, G, is_game_over)

    _hide_ghost_from_others(s, player_id)
    return s


def strip_fabricated_flag(fp: dict[str, Any]) -> dict[str, Any]:
    """Remove is_fabricated from a FalseHintPayload before sending to clients."""
    result = dict(fp)
    result.pop("is_fabricated", None)
    return result


# ── View type implementations ─────────────────────────────────────────────────

def _display_view(state: dict[str, Any], is_game_over: bool) -> dict[str, Any]:
    """Display client: no role/team, only aggregate action counts."""
    s = deepcopy(state)

    # Strip all role/team from all players
    for pid, p in s["players"].items():
        _strip_player_fields(p, _ALWAYS_STRIP_PLAYER_FIELDS)
        p["role"] = None
        p["team"] = None
        p["night_action_submitted"] = None  # aggregate only
        p["doused_player_ids"] = []
        p["lovers_partner_id"] = None
        p["puzzles_solved_count"] = 0
        p["vote_target_id"] = None
        p["puzzle_state"] = None
        p["grid_puzzle_state"] = None
        p["under_attack"] = False

    s["night_actions"] = _build_na_for_view(s.get("night_actions", {}), "display")

    s["seer_knowledge"] = {}
    s["tracker_knowledge"] = {}
    s["lovers_pair"] = None if not is_game_over else s.get("lovers_pair")

    if not is_game_over:
        _hide_elimination_log_details(s)

    return s


def _wolf_team_view(
    state: dict[str, Any], player_id: str, G: MasterGameState, is_game_over: bool
) -> dict[str, Any]:
    """Wolf team: sees wolf teammates' roles, wolf_votes, own night action status."""
    s = deepcopy(state)
    wolf_pids = {pid for pid, p in G.players.items() if p.team == "werewolf"}

    for pid, p in s["players"].items():
        _strip_player_fields(p, _ALWAYS_STRIP_PLAYER_FIELDS)
        if pid not in wolf_pids:
            p["role"] = None
            p["team"] = None
        # Only show own night_action_submitted + wolf teammates
        if pid != player_id and pid not in wolf_pids:
            p["night_action_submitted"] = None
        p["doused_player_ids"] = []
        p["lovers_partner_id"] = None if G.players[pid].lovers_partner_id is None or pid != player_id else p["lovers_partner_id"]
        p["puzzles_solved_count"] = 0 if pid != player_id else p["puzzles_solved_count"]
        if pid == player_id:
            _ps = G.players[player_id].puzzle_state
            p["puzzle_state"] = _strip_puzzle_for_player(
                _ps.model_dump(mode="json") if _ps else None, player_id, G
            )
        else:
            p["puzzle_state"] = None
        # Wolves don't use the grid (no grid_puzzle_state or under_attack for wolf team)
        p["grid_puzzle_state"] = None
        p["under_attack"] = False

    s["night_actions"] = _build_na_for_view(s.get("night_actions", {}), "wolf")

    s["seer_knowledge"] = {}
    s["tracker_knowledge"] = {}
    if not is_game_over:
        s["lovers_pair"] = None
        _hide_elimination_log_details(s)

    return s


def _seer_view(
    state: dict[str, Any], player_id: str, G: MasterGameState, is_game_over: bool
) -> dict[str, Any]:
    """Seer: receives own seer_knowledge, seer_target_id, seer_result."""
    s = _baseline_alive_view(state, player_id, G, is_game_over)

    # Override: give seer their knowledge and current-round results
    s["seer_knowledge"] = deepcopy(state.get("seer_knowledge", {}))
    na = s.get("night_actions", {})
    na["seer_target_id"] = state.get("night_actions", {}).get("seer_target_id")
    na["seer_result"] = state.get("night_actions", {}).get("seer_result")

    return s


def _tracker_view(
    state: dict[str, Any], player_id: str, G: MasterGameState, is_game_over: bool
) -> dict[str, Any]:
    """Tracker: receives tracker_knowledge and tracker_result."""
    s = _baseline_alive_view(state, player_id, G, is_game_over)
    s["tracker_knowledge"] = deepcopy(state.get("tracker_knowledge", {}))
    na = s.get("night_actions", {})
    na["tracker_target_id"] = state.get("night_actions", {}).get("tracker_target_id")
    na["tracker_result"] = state.get("night_actions", {}).get("tracker_result", [])
    return s


def _arsonist_view(
    state: dict[str, Any], player_id: str, G: MasterGameState, is_game_over: bool
) -> dict[str, Any]:
    """Arsonist: sees own doused_player_ids and arsonist_action."""
    s = _baseline_alive_view(state, player_id, G, is_game_over)
    # Restore own doused list
    s["players"][player_id]["doused_player_ids"] = deepcopy(
        state["players"][player_id].get("doused_player_ids", [])
    )
    na = s.get("night_actions", {})
    na["arsonist_action"] = state.get("night_actions", {}).get("arsonist_action")
    na["arsonist_douse_target_id"] = state.get("night_actions", {}).get("arsonist_douse_target_id")
    return s


def _lunatic_view(
    state: dict[str, Any], player_id: str, G: MasterGameState, is_game_over: bool
) -> dict[str, Any]:
    """Lunatic: sees own redirect-used flag so the UI can disable the spent button."""
    s = _baseline_alive_view(state, player_id, G, is_game_over)
    s["players"][player_id]["lunatic_redirect_used"] = state["players"][player_id].get("lunatic_redirect_used", False)
    return s


def _witch_view(
    state: dict[str, Any], player_id: str, G: MasterGameState, is_game_over: bool
) -> dict[str, Any]:
    """Witch: sees own potion availability (witch_heal_used, witch_kill_used)."""
    s = _baseline_alive_view(state, player_id, G, is_game_over)
    # Restore own potion state so WitchUI can disable spent buttons
    s["players"][player_id]["witch_heal_used"] = state["players"][player_id].get("witch_heal_used", False)
    s["players"][player_id]["witch_kill_used"] = state["players"][player_id].get("witch_kill_used", False)
    return s


def _baseline_alive_view(
    state: dict[str, Any], player_id: str, G: MasterGameState, is_game_over: bool
) -> dict[str, Any]:
    """
    Village non-seer, neutral alive, and base for other specialized views.
    Sees: own role, public player info, aggregate action counts.
    """
    s = deepcopy(state)

    for pid, p in s["players"].items():
        _strip_player_fields(p, _ALWAYS_STRIP_PLAYER_FIELDS)
        if pid != player_id:
            p["role"] = None
            p["team"] = None
            p["night_action_submitted"] = None
        p["doused_player_ids"] = []
        # lovers_partner_id: only to the linked player
        if pid != player_id:
            p["lovers_partner_id"] = None
        p["puzzles_solved_count"] = 0 if pid != player_id else p["puzzles_solved_count"]
        if pid == player_id:
            _ps = G.players[player_id].puzzle_state
            p["puzzle_state"] = _strip_puzzle_for_player(
                _ps.model_dump(mode="json") if _ps else None, player_id, G
            )
            _gps = G.players[player_id].grid_puzzle_state
            p["grid_puzzle_state"] = _strip_puzzle_for_player(
                _gps.model_dump(mode="json") if _gps else None, player_id, G
            )
            # Restore under_attack for own player — wolves must never see this field
            p["under_attack"] = G.players[player_id].under_attack
        else:
            p["puzzle_state"] = None
            p["grid_puzzle_state"] = None
            p["under_attack"] = False

    s["night_actions"] = _build_na_for_view(state.get("night_actions", {}), "baseline")

    s["seer_knowledge"] = {}
    s["tracker_knowledge"] = {}
    if not is_game_over:
        s["lovers_pair"] = None
        _hide_elimination_log_details(s)

    return s


def _dead_spectator_view(
    state: dict[str, Any], player_id: str, is_game_over: bool
) -> dict[str, Any]:
    """
    Dead players: see all roles. night_actions block removed during live play.
    At game_over: elimination_log.role and saved_by_doctor are revealed.
    """
    s = deepcopy(state)

    for pid, p in s["players"].items():
        _strip_player_fields(p, _ALWAYS_STRIP_PLAYER_FIELDS)
        p["doused_player_ids"] = []
        p["lovers_partner_id"] = None
        p["night_action_submitted"] = None
        p["puzzles_solved_count"] = 0
        p["puzzle_state"] = None
        p["grid_puzzle_state"] = None
        p["under_attack"] = False

    s["night_actions"] = _build_na_for_view(state.get("night_actions", {}), "dead")

    if is_game_over:
        # Reveal accumulated seer_knowledge and tracker_knowledge
        s["seer_knowledge"] = deepcopy(state.get("seer_knowledge", {}))
        s["tracker_knowledge"] = deepcopy(state.get("tracker_knowledge", {}))
        # elimination_log roles already revealed by _reveal_roles_on_game_over
    else:
        s["seer_knowledge"] = {}
        s["tracker_knowledge"] = {}
        _hide_elimination_log_details(s)
        s["lovers_pair"] = None

    return s


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_player_fields(p: dict[str, Any], fields: frozenset[str]) -> None:
    """Remove sensitive fields from a player dict in place."""
    for field in fields:
        p.pop(field, None)



def _hide_elimination_log_details(s: dict[str, Any]) -> None:
    """Null out role and saved_by_doctor in elimination_log during live play."""
    for event in s.get("elimination_log", []):
        event["role"] = None
        event["saved_by_doctor"] = False


def _build_na_for_view(na_raw: dict, view: str) -> dict:
    """
    Assemble the night_actions dict for a specific view type.
    Always-stripped fields are excluded; view-specific fields are included here.
    Add new NightActions fields in this single function — not in each view function.

    view values: "display" | "wolf" | "baseline" | "dead" | "seer" | "tracker" | "arsonist"
    """
    # Fields public to all live views
    base: dict = {
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


def _strip_puzzle_for_player(
    puzzle_state: dict[str, Any] | None,
    player_id: str,
    G: MasterGameState,
) -> dict[str, Any] | None:
    """
    Return puzzle_state for the eligible player only, with correct_index stripped.
    Returns None for all other players.
    SECURITY: correct_index must never be sent to any client.
    """
    if puzzle_state is None:
        return None

    # Only wakeOrder==0 players receive puzzle_state
    player = G.players.get(player_id)
    if not player or not player.is_alive:
        return None

    from engine.roles_loader import ROLE_REGISTRY
    role_def = ROLE_REGISTRY.get(player.role or "", {})
    if role_def.get("wakeOrder", 0) != 0:
        return None

    # Strip correct_index — never send to client (including nested hard_logic q1/q2)
    stripped = deepcopy(puzzle_state)
    if "puzzle_data" in stripped:
        pd = dict(stripped["puzzle_data"])
        pd.pop("correct_index", None)
        for qkey in ("q1", "q2"):
            if isinstance(pd.get(qkey), dict):
                pd[qkey] = {k: v for k, v in pd[qkey].items() if k != "correct_index"}
        stripped["puzzle_data"] = pd

    return stripped


def _hide_ghost_from_others(s: dict[str, Any], viewer_id: str | None) -> None:
    """
    Null out role/team for any Ghost player in the players dict, EXCEPT for the
    Ghost's own entry when they are the viewer. Called on every view to ensure
    Ghost identity is never revealed — not during live play, not at game_over.
    """
    for pid, p in s.get("players", {}).items():
        if p.get("role") == "ghost" and pid != viewer_id:
            p["role"] = None
            p["team"] = None
