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
})


def player_view(G: MasterGameState, player_id: str | None) -> dict[str, Any]:
    """
    Return a stripped copy of game state appropriate for the given player.
    player_id=None means the Display client (all role data removed).
    """
    state = G.model_dump(mode="json")
    is_game_over = G.phase == Phase.GAME_OVER

    # Determine view type
    if player_id is None:
        return _display_view(state, is_game_over)

    player = G.players.get(player_id)
    if player is None:
        # Unknown player — treat as display (safest fallback)
        return _display_view(state, is_game_over)

    if not player.is_alive:
        return _dead_spectator_view(state, player_id, is_game_over)

    team = player.team
    role = player.role

    if team == "werewolf":
        return _wolf_team_view(state, player_id, G, is_game_over)
    if role == "seer":
        return _seer_view(state, player_id, G, is_game_over)
    if role == "tracker":
        return _tracker_view(state, player_id, G, is_game_over)
    if role == "arsonist":
        return _arsonist_view(state, player_id, G, is_game_over)
    # village_nonseer, neutral_alive, and all other roles
    return _baseline_alive_view(state, player_id, G, is_game_over)


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

    # Strip night_actions entirely — keep only aggregate counts
    na = s.get("night_actions", {})
    s["night_actions"] = {
        "actions_submitted_count": na.get("actions_submitted_count", 0),
        "actions_required_count": na.get("actions_required_count", 0),
    }

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

    # Night actions: wolf team sees wolf_votes only (plus aggregate counts)
    na = s.get("night_actions", {})
    s["night_actions"] = {
        "wolf_votes": na.get("wolf_votes", {}),
        "actions_submitted_count": na.get("actions_submitted_count", 0),
        "actions_required_count": na.get("actions_required_count", 0),
        # puzzle_state: only if this wolf is wakeOrder==0 (uncommon, but handled)
        "puzzle_state": _strip_puzzle_for_player(na.get("puzzle_state"), player_id, G),
    }
    _strip_night_action_always(s)

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

    # Night actions: only aggregate counts + own puzzle if applicable
    na = state.get("night_actions", {})
    s["night_actions"] = {
        "actions_submitted_count": na.get("actions_submitted_count", 0),
        "actions_required_count": na.get("actions_required_count", 0),
        "puzzle_state": _strip_puzzle_for_player(na.get("puzzle_state"), player_id, G),
    }

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

    # night_actions: entirely removed during live play
    s["night_actions"] = {
        "actions_submitted_count": state.get("night_actions", {}).get("actions_submitted_count", 0),
        "actions_required_count": state.get("night_actions", {}).get("actions_required_count", 0),
    }

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


def _strip_night_action_always(s: dict[str, Any]) -> None:
    """Remove always-stripped fields from the night_actions dict."""
    na = s.get("night_actions", {})
    for field in _ALWAYS_STRIP_NIGHT_ACTION_FIELDS:
        na.pop(field, None)


def _hide_elimination_log_details(s: dict[str, Any]) -> None:
    """Null out role and saved_by_doctor in elimination_log during live play."""
    for event in s.get("elimination_log", []):
        event["role"] = None
        event["saved_by_doctor"] = False


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

    # Strip correct_index — never send to client
    stripped = deepcopy(puzzle_state)
    if "puzzle_data" in stripped:
        stripped["puzzle_data"] = dict(stripped["puzzle_data"])
        stripped["puzzle_data"].pop("correct_index", None)

    return stripped
