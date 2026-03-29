"""
Role discovery and introspection utilities for integration/e2e tests.

Roles are assigned via seeded RNG — there is no REST endpoint to query them.
The only authoritative source is each player's own WS sync message after
start_game transitions to ROLE_DEAL.

Call collect_role_map() BEFORE opening the display WebSocket.  Each player
connect/disconnect triggers a player_disconnected broadcast.  Opening the
display WS first would fill its buffer with noise that is hard to drain later.
"""

from __future__ import annotations

from typing import Any


def collect_role_map(
    client,
    game_id: str,
    players: list[dict[str, str]],
) -> dict[str, str]:
    """
    Open each player's WebSocket, read their sync message, extract role.
    Returns {player_id: role_id}.

    Must be called while game is in ROLE_DEAL phase (after start_game).
    """
    role_map: dict[str, str] = {}
    for player in players:
        pid = player["player_id"]
        with client.websocket_connect(f"/ws/{game_id}/{pid}") as ws:
            ws.send_json({"type": "auth", "session_token": player["session_token"]})
            msg = ws.receive_json()  # sync message
        # Closing triggers player_disconnected broadcast — callers tolerate this.
        role_map[pid] = msg["state"]["players"][pid]["role"]
    return role_map


def first_with_role(
    role_map: dict[str, str],
    role: str,
    players: list[dict[str, str]],
) -> dict[str, str] | None:
    """Return the first player dict whose role matches, or None."""
    for p in players:
        if role_map.get(p["player_id"]) == role:
            return p
    return None


def players_with_role(
    role_map: dict[str, str],
    role: str,
    players: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Return all player dicts whose role matches."""
    return [p for p in players if role_map.get(p["player_id"]) == role]


def get_alive_pids(state: dict[str, Any]) -> list[str]:
    """Return player_ids of all alive players in a state dict."""
    return [
        pid
        for pid, p in state.get("players", {}).items()
        if p.get("is_alive", False)
    ]


def actions_required(role_map: dict[str, str]) -> int:
    """
    Count alive players with a waking night role (wakeOrder > 0 and actionPhase
    in {"night", "night_one_only"}).  Mirrors compute_actions_required() in
    engine.phases.machine — used by tests to know when auto-advance fires.
    """
    from engine.roles_loader import ROLE_REGISTRY

    count = 0
    for role_id in role_map.values():
        role_def = ROLE_REGISTRY.get(role_id, {})
        wake_order = role_def.get("wakeOrder", 0)
        action_phase = role_def.get("actionPhase", "none")
        if wake_order == 0:
            continue
        if action_phase in ("none", "day", "on_death"):
            continue
        count += 1
    return count
