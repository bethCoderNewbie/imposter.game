"""
WebSocket message assertion utilities.

consume_until() is the workhorse: drain messages until a predicate matches.
It tolerates disconnect-triggered broadcasts and other noise between intent
submissions.
"""

from __future__ import annotations

from typing import Any, Callable


def consume_until(
    ws,
    predicate: Callable[[dict], bool],
    max_messages: int = 30,
) -> dict[str, Any]:
    """
    Drain ws.receive_json() until predicate(msg) is True.
    Returns the matching message.
    Raises AssertionError if max_messages is exhausted first.
    """
    for i in range(max_messages):
        msg = ws.receive_json()
        if predicate(msg):
            return msg
    raise AssertionError(
        f"consume_until: predicate not satisfied after {max_messages} messages"
    )


def until_phase(phase: str) -> Callable[[dict], bool]:
    """Returns a predicate that matches messages where state.phase == phase."""
    return lambda msg: msg.get("state", {}).get("phase") == phase


def until_type(msg_type: str) -> Callable[[dict], bool]:
    return lambda msg: msg.get("type") == msg_type


def until_game_over() -> Callable[[dict], bool]:
    return lambda msg: msg.get("state", {}).get("phase") == "game_over"


# ── Assertion helpers ──────────────────────────────────────────────────────────

def assert_phase(msg: dict, expected: str) -> None:
    actual = msg.get("state", {}).get("phase")
    assert actual == expected, f"Expected phase={expected!r}, got {actual!r}"


def assert_player_alive(msg: dict, player_id: str) -> None:
    p = msg.get("state", {}).get("players", {}).get(player_id)
    assert p is not None, f"Player {player_id} not found in state"
    assert p["is_alive"] is True, f"Expected player {player_id} to be alive"


def assert_player_dead(msg: dict, player_id: str) -> None:
    p = msg.get("state", {}).get("players", {}).get(player_id)
    assert p is not None, f"Player {player_id} not found in state"
    assert p["is_alive"] is False, f"Expected player {player_id} to be dead"


def assert_game_over(msg: dict, winner: str) -> None:
    assert_phase(msg, "game_over")
    actual = msg.get("state", {}).get("winner")
    assert actual == winner, f"Expected winner={winner!r}, got {actual!r}"


def assert_no_sensitive_role_data(msg: dict) -> None:
    """Assert the display view never exposes role or team for any player."""
    players = msg.get("state", {}).get("players", {})
    for pid, p in players.items():
        assert p.get("role") is None, (
            f"Display view exposed role={p['role']!r} for player {pid}"
        )
        assert p.get("team") is None, (
            f"Display view exposed team={p['team']!r} for player {pid}"
        )
