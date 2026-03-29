"""
GameDriver: high-level helpers for driving a game through phases in tests.

Design principles:
- All helpers operate through the real WebSocket + REST stack.
- send_player_intent() opens a player WS, authenticates, sends one intent, closes.
  Closing triggers a player_disconnected broadcast — callers drain with consume_until().
- display_ws stays open throughout so callers can observe all broadcasts.
- No state is stored; all helpers are stateless module-level functions.
"""

from __future__ import annotations

from typing import Any

from tests.helpers.ws_patterns import consume_until, until_phase


# ── Low-level helpers ─────────────────────────────────────────────────────────

def create_and_fill(client, n: int = 5) -> tuple[str, str, list[dict[str, str]]]:
    """
    Create a game and join n players.
    Returns (game_id, host_secret, players) where players[0] is the host.
    """
    resp = client.post("/api/games", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    game_id: str = data["game_id"]
    host_secret: str = data["host_secret"]

    players: list[dict[str, str]] = []
    for i in range(n):
        r = client.post(
            f"/api/games/{game_id}/join",
            json={"display_name": f"Player{i + 1}"},
        )
        assert r.status_code == 200, r.text
        j = r.json()
        players.append({"player_id": j["player_id"], "session_token": j["session_token"]})

    return game_id, host_secret, players


def send_player_intent(
    client,
    game_id: str,
    player: dict[str, str],
    intent: dict[str, Any],
) -> None:
    """
    Open a player WebSocket, authenticate, receive the sync, send one intent,
    then close.  The server enqueues the intent before the disconnect fires, so
    the intent is always processed first.
    """
    pid = player["player_id"]
    with client.websocket_connect(f"/ws/{game_id}/{pid}") as ws:
        ws.send_json({"type": "auth", "session_token": player["session_token"]})
        ws.receive_json()  # consume sync
        ws.send_json(intent)


# ── Phase drivers ─────────────────────────────────────────────────────────────

def drive_role_deal(
    client,
    game_id: str,
    players: list[dict[str, str]],
    display_ws,
) -> dict[str, Any]:
    """
    Confirm role reveal for every player, then drain display_ws until NIGHT.
    Returns the NIGHT broadcast message.
    """
    for player in players:
        send_player_intent(client, game_id, player, {"type": "confirm_role_reveal"})
    return consume_until(display_ws, until_phase("night"))


def drive_night(
    client,
    game_id: str,
    players: list[dict[str, str]],
    display_ws,
    night_acts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Submit a dict of {player_id: intent} for the night phase.
    Drains display_ws until DAY / GAME_OVER / HUNTER_PENDING.
    Returns the first matching broadcast.

    Only waking-role players need entries in night_acts (wakeOrder > 0).
    The last submission triggers auto-advance inline.
    """
    for pid, intent in night_acts.items():
        player = next(p for p in players if p["player_id"] == pid)
        send_player_intent(client, game_id, player, intent)

    return consume_until(
        display_ws,
        lambda m: m.get("state", {}).get("phase") in ("day", "game_over", "hunter_pending"),
        max_messages=50,
    )


def drive_to_day_vote(
    client,
    game_id: str,
    players: list[dict[str, str]],
    display_ws,
) -> dict[str, Any]:
    """
    Host (players[0]) sends advance_phase from DAY → DAY_VOTE.
    Returns the DAY_VOTE broadcast.
    """
    send_player_intent(client, game_id, players[0], {"type": "advance_phase"})
    return consume_until(display_ws, until_phase("day_vote"))


def drive_votes(
    client,
    game_id: str,
    players: list[dict[str, str]],
    display_ws,
    voter_pids: list[str],
    target_id: str,
) -> dict[str, Any]:
    """
    Each pid in voter_pids votes for target_id.
    Drains display_ws until NIGHT / GAME_OVER / HUNTER_PENDING.
    Returns the first matching broadcast.
    """
    for pid in voter_pids:
        player = next(p for p in players if p["player_id"] == pid)
        send_player_intent(
            client,
            game_id,
            player,
            {"type": "submit_day_vote", "target_id": target_id},
        )

    return consume_until(
        display_ws,
        lambda m: m.get("state", {}).get("phase") in ("night", "game_over", "hunter_pending"),
        max_messages=50,
    )
