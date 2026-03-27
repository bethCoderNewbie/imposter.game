"""
E2E tests for the full game flow.
Requires real Redis — see conftest.py for skip logic.

These tests exercise the entire stack:
  REST API → Redis persistence → WebSocket broadcast → State stripping

Markers: pytest.mark.e2e
"""

from __future__ import annotations

import pytest


def _create_game(client):
    """Helper: create a new game and return (game_id, host_secret)."""
    data = client.post("/api/games", json={}).json()
    return data["game_id"], data["host_secret"]


def _join_players(client, game_id: str, n: int) -> list[dict]:
    """Helper: join n players and return list of {player_id, session_token}."""
    players = []
    for i in range(n):
        data = client.post(f"/api/games/{game_id}/join", json={"display_name": f"Player{i}"}).json()
        players.append({"player_id": data["player_id"], "session_token": data["session_token"]})
    return players


@pytest.mark.e2e
class TestLobbyFlow:
    def test_create_join_start_lobby_via_rest(self, e2e_client):
        """Full REST lobby flow: create → join → start with enough players."""
        game_id, host_secret = _create_game(e2e_client)

        # Join 5 players
        players = _join_players(e2e_client, game_id, 5)
        assert len(players) == 5
        assert len({p["player_id"] for p in players}) == 5  # all unique

        # Start game
        resp = e2e_client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_create_join_too_few_cannot_start(self, e2e_client):
        game_id, host_secret = _create_game(e2e_client)
        _join_players(e2e_client, game_id, 4)  # need 5, only 4 joined
        resp = e2e_client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
        assert resp.status_code == 409

    def test_rejoin_preserves_player(self, e2e_client):
        game_id, _ = _create_game(e2e_client)
        join_data = e2e_client.post(f"/api/games/{game_id}/join", json={"display_name": "Alice"}).json()
        player_id = join_data["player_id"]
        token = join_data["session_token"]

        rejoin_data = e2e_client.post(f"/api/games/{game_id}/rejoin", json={"session_token": token}).json()
        assert rejoin_data["player_id"] == player_id


@pytest.mark.e2e
class TestWebSocketLobbyBroadcast:
    def test_display_receives_lobby_state_on_connect(self, e2e_client):
        """Display WS receives the current game state immediately on connection."""
        game_id, _ = _create_game(e2e_client)
        _join_players(e2e_client, game_id, 3)

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as ws:
            msg = ws.receive_json()

        assert msg["type"] == "state_update"
        assert msg["state"]["phase"] == "lobby"
        assert len(msg["state"]["players"]) == 3

    def test_display_receives_update_when_player_joins(self, e2e_client):
        """Joining via REST while display WS is open triggers a live broadcast."""
        game_id, _ = _create_game(e2e_client)

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as ws:
            initial = ws.receive_json()
            assert len(initial["state"]["players"]) == 0

            # Join a player — triggers lobby broadcast
            e2e_client.post(f"/api/games/{game_id}/join", json={"display_name": "Bob"})

            updated = ws.receive_json()
            assert updated["state"]["phase"] == "lobby"
            assert len(updated["state"]["players"]) == 1

    def test_player_ws_receives_initial_state_after_auth(self, e2e_client):
        game_id, _ = _create_game(e2e_client)
        join_data = e2e_client.post(f"/api/games/{game_id}/join", json={"display_name": "Alice"}).json()
        player_id = join_data["player_id"]
        token = join_data["session_token"]

        with e2e_client.websocket_connect(f"/ws/{game_id}/{player_id}") as ws:
            ws.send_json({"type": "auth", "session_token": token})
            msg = ws.receive_json()

        assert msg["type"] == "state_update"
        assert msg["state"]["phase"] == "lobby"

    def test_display_state_never_exposes_host_secret(self, e2e_client):
        game_id, host_secret = _create_game(e2e_client)
        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as ws:
            msg = ws.receive_json()
        assert host_secret not in str(msg)
        assert "host_secret" not in str(msg["state"])


@pytest.mark.e2e
class TestGameStart:
    def test_start_transitions_to_role_deal_via_display_ws(self, e2e_client):
        """
        Full flow: join 5 players, start game, display WS receives ROLE_DEAL update.
        This validates: REST → Redis → game_queue → intent handler → broadcast → WS.
        """
        game_id, host_secret = _create_game(e2e_client)
        _join_players(e2e_client, game_id, 5)

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as ws:
            # Consume initial LOBBY state
            initial = ws.receive_json()
            assert initial["state"]["phase"] == "lobby"
            assert len(initial["state"]["players"]) == 5

            # Start the game via REST
            start_resp = e2e_client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
            assert start_resp.status_code == 200

            # Wait for the game queue to process start_game and broadcast ROLE_DEAL
            role_deal_msg = ws.receive_json()
            assert role_deal_msg["type"] == "state_update"
            assert role_deal_msg["state"]["phase"] == "role_deal"

    def test_role_deal_state_has_all_players(self, e2e_client):
        game_id, host_secret = _create_game(e2e_client)
        _join_players(e2e_client, game_id, 5)

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as ws:
            ws.receive_json()  # initial lobby

            e2e_client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
            role_deal_msg = ws.receive_json()

        assert len(role_deal_msg["state"]["players"]) == 5

    def test_display_role_deal_state_does_not_expose_roles(self, e2e_client):
        """
        Display view must NOT show player roles during ROLE_DEAL
        (players see their own role privately on their mobile).
        """
        game_id, host_secret = _create_game(e2e_client)
        _join_players(e2e_client, game_id, 5)

        with e2e_client.websocket_connect(f"/ws/{game_id}/display") as ws:
            ws.receive_json()  # initial lobby

            e2e_client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
            role_deal_msg = ws.receive_json()

        # Each player entry in the display view should NOT expose the role
        for player_data in role_deal_msg["state"]["players"].values():
            assert player_data.get("role") is None, (
                f"Display should not see player role, got: {player_data.get('role')}"
            )

    def test_player_sees_own_role_after_start(self, e2e_client):
        """
        After game starts, a player's own WS view SHOULD include their own role.
        """
        game_id, host_secret = _create_game(e2e_client)
        players = _join_players(e2e_client, game_id, 5)
        alice = players[0]

        e2e_client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})

        with e2e_client.websocket_connect(f"/ws/{game_id}/{alice['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": alice["session_token"]})
            msg = ws.receive_json()

        assert msg["state"]["phase"] == "role_deal"
        # The authenticated player sees their own role
        own_player = msg["state"]["players"][alice["player_id"]]
        assert own_player["role"] is not None
