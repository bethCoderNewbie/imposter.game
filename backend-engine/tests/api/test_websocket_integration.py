"""
Integration tests for the WebSocket endpoint.
Verifies auth flow, initial state push, and error handling.

Uses starlette.testclient.TestClient + fakeredis — no real Redis required.
Markers: pytest.mark.integration
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestDisplayClientConnection:
    def test_display_connects_without_auth(self, client):
        """Display client (player_id='display') requires no session token."""
        game_id = client.post("/api/games", json={}).json()["game_id"]
        with client.websocket_connect(f"/ws/{game_id}/display") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "state_update"

    def test_display_receives_initial_state(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        with client.websocket_connect(f"/ws/{game_id}/display") as ws:
            msg = ws.receive_json()
            assert "state" in msg
            assert "phase" in msg["state"]

    def test_display_initial_state_is_lobby_phase(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        with client.websocket_connect(f"/ws/{game_id}/display") as ws:
            msg = ws.receive_json()
            assert msg["state"]["phase"] == "lobby"

    def test_display_initial_state_contains_schema_version(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        with client.websocket_connect(f"/ws/{game_id}/display") as ws:
            msg = ws.receive_json()
            assert "schema_version" in msg

    def test_display_initial_state_contains_state_id(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        with client.websocket_connect(f"/ws/{game_id}/display") as ws:
            msg = ws.receive_json()
            assert "state_id" in msg

    def test_display_state_does_not_expose_host_secret(self, client):
        """host_secret must never be sent to any client."""
        game_id = client.post("/api/games", json={}).json()["game_id"]
        with client.websocket_connect(f"/ws/{game_id}/display") as ws:
            msg = ws.receive_json()
        state_json = str(msg["state"])
        assert "host_secret" not in state_json

    def test_display_state_shows_joined_players(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        client.post(f"/api/games/{game_id}/join", json={"display_name": "Alice"})
        client.post(f"/api/games/{game_id}/join", json={"display_name": "Bob"})
        with client.websocket_connect(f"/ws/{game_id}/display") as ws:
            msg = ws.receive_json()
        assert len(msg["state"]["players"]) == 2


@pytest.mark.integration
class TestPlayerAuthentication:
    def test_player_invalid_auth_type_closes_connection(self, client):
        """Sending a non-auth first message closes with code 1008."""
        game_id = client.post("/api/games", json={}).json()["game_id"]
        player_id = "some-player-id"
        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/{game_id}/{player_id}") as ws:
                ws.send_json({"type": "not_auth", "something": "else"})
                ws.receive_json()  # Should fail — connection was closed

    def test_player_missing_token_closes_connection(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        player_id = "some-player-id"
        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/{game_id}/{player_id}") as ws:
                ws.send_json({"type": "auth"})  # no session_token field
                ws.receive_json()

    def test_player_fake_token_receives_auth_error(self, client):
        """Server sends an AUTH_FAILED error then closes when token is invalid."""
        game_id = client.post("/api/games", json={}).json()["game_id"]
        player_id = "some-player-id"
        with client.websocket_connect(f"/ws/{game_id}/{player_id}") as ws:
            ws.send_json({"type": "auth", "session_token": "not-a-real-token"})
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "AUTH_FAILED"

    def test_player_valid_token_receives_initial_state(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        join_data = client.post(f"/api/games/{game_id}/join", json={"display_name": "Alice"}).json()
        player_id = join_data["player_id"]
        token = join_data["session_token"]

        with client.websocket_connect(f"/ws/{game_id}/{player_id}") as ws:
            ws.send_json({"type": "auth", "session_token": token})
            msg = ws.receive_json()
            assert msg["type"] == "state_update"
            assert msg["state"]["phase"] == "lobby"

    def test_player_token_wrong_game_receives_auth_error(self, client):
        """A token for game A cannot be used to connect to game B — server returns AUTH_FAILED."""
        game_a = client.post("/api/games", json={}).json()["game_id"]
        game_b = client.post("/api/games", json={}).json()["game_id"]
        join_data = client.post(f"/api/games/{game_a}/join", json={"display_name": "Alice"}).json()
        player_id = join_data["player_id"]
        token = join_data["session_token"]

        with client.websocket_connect(f"/ws/{game_b}/{player_id}") as ws:
            ws.send_json({"type": "auth", "session_token": token})
            msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "AUTH_FAILED"


@pytest.mark.integration
class TestJoinBroadcast:
    def test_display_receives_update_when_player_joins(self, client):
        """Joining a player should broadcast a state update to the connected display."""
        game_id = client.post("/api/games", json={}).json()["game_id"]

        with client.websocket_connect(f"/ws/{game_id}/display") as ws:
            # Consume the initial state
            initial = ws.receive_json()
            assert len(initial["state"]["players"]) == 0

            # Join a player via REST — triggers broadcast
            client.post(f"/api/games/{game_id}/join", json={"display_name": "Alice"})

            # Display should receive the updated state
            updated = ws.receive_json()
            assert updated["type"] == "state_update"
            assert len(updated["state"]["players"]) == 1
