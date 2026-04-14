"""
Integration tests for lobby REST endpoints.
Uses FastAPI TestClient + fakeredis + in-memory SQLite — no real services required.

Markers: pytest.mark.integration
"""

from __future__ import annotations

import pytest

from tests.helpers.game_driver import register_and_join


def _reg(client, name: str) -> str:
    """Register a player and return their permanent_id."""
    return client.post("/api/players/register", json={"display_name": name}).json()["permanent_id"]


@pytest.mark.integration
class TestCreateGame:
    def test_returns_200(self, client):
        resp = client.post("/api/games", json={})
        assert resp.status_code == 200

    def test_response_contains_required_fields(self, client):
        data = client.post("/api/games", json={}).json()
        assert "game_id" in data
        assert "host_secret" in data
        assert "join_code" in data

    def test_game_id_equals_join_code(self, client):
        data = client.post("/api/games", json={}).json()
        assert data["game_id"] == data["join_code"]

    def test_each_game_gets_unique_id(self, client):
        id1 = client.post("/api/games", json={}).json()["game_id"]
        id2 = client.post("/api/games", json={}).json()["game_id"]
        assert id1 != id2


@pytest.mark.integration
class TestJoinGame:
    def test_join_returns_200(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        resp = client.post(f"/api/games/{game_id}/join", json={"permanent_id": _reg(client, "Alice")})
        assert resp.status_code == 200

    def test_join_response_contains_required_fields(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        data = client.post(f"/api/games/{game_id}/join", json={"permanent_id": _reg(client, "Alice")}).json()
        assert "game_id" in data
        assert "player_id" in data
        assert "session_token" in data

    def test_join_returns_game_id_matching_request(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        data = client.post(f"/api/games/{game_id}/join", json={"permanent_id": _reg(client, "Alice")}).json()
        assert data["game_id"] == game_id

    def test_each_player_gets_unique_id(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        p1 = client.post(f"/api/games/{game_id}/join", json={"permanent_id": _reg(client, "Alice")}).json()
        p2 = client.post(f"/api/games/{game_id}/join", json={"permanent_id": _reg(client, "Bob")}).json()
        assert p1["player_id"] != p2["player_id"]

    def test_join_nonexistent_game_returns_404(self, client):
        resp = client.post("/api/games/NOPE/join", json={"permanent_id": _reg(client, "Alice")})
        assert resp.status_code == 404

    def test_join_with_unknown_permanent_id_returns_404(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        resp = client.post(f"/api/games/{game_id}/join", json={"permanent_id": "00000000-0000-0000-0000-000000000000"})
        assert resp.status_code == 404

    def test_join_full_lobby_returns_409(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        for i in range(16):
            register_and_join(client, game_id, f"P{i}")
        resp = client.post(f"/api/games/{game_id}/join", json={"permanent_id": _reg(client, "TooMany")})
        assert resp.status_code == 409


@pytest.mark.integration
class TestPlayerRegistry:
    def test_register_returns_200(self, client):
        resp = client.post("/api/players/register", json={"display_name": "Alice"})
        assert resp.status_code == 200

    def test_register_returns_permanent_id_and_name(self, client):
        data = client.post("/api/players/register", json={"display_name": "Alice"}).json()
        assert "permanent_id" in data
        assert data["display_name"] == "Alice"

    def test_register_name_too_long_returns_422(self, client):
        resp = client.post("/api/players/register", json={"display_name": "A" * 17})
        assert resp.status_code == 422

    def test_register_empty_name_returns_422(self, client):
        resp = client.post("/api/players/register", json={"display_name": ""})
        assert resp.status_code == 422

    def test_get_player_returns_name(self, client):
        pid = _reg(client, "Bob")
        data = client.get(f"/api/players/{pid}").json()
        assert data["display_name"] == "Bob"

    def test_get_unknown_player_returns_404(self, client):
        resp = client.get("/api/players/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_update_name_returns_new_name(self, client):
        pid = _reg(client, "OldName")
        data = client.put(f"/api/players/{pid}", json={"display_name": "NewName"}).json()
        assert data["display_name"] == "NewName"

    def test_update_name_persists_on_get(self, client):
        pid = _reg(client, "Before")
        client.put(f"/api/players/{pid}", json={"display_name": "After"})
        assert client.get(f"/api/players/{pid}").json()["display_name"] == "After"

    def test_update_unknown_player_returns_404(self, client):
        resp = client.put("/api/players/00000000-0000-0000-0000-000000000000", json={"display_name": "X"})
        assert resp.status_code == 404


@pytest.mark.integration
class TestStartGame:
    def _create_and_fill(self, client, n: int = 5):
        create_data = client.post("/api/games", json={}).json()
        game_id = create_data["game_id"]
        host_secret = create_data["host_secret"]
        for i in range(n):
            register_and_join(client, game_id, f"P{i}")
        return game_id, host_secret

    def test_start_with_correct_secret_returns_200(self, client):
        game_id, host_secret = self._create_and_fill(client, 5)
        resp = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
        assert resp.status_code == 200

    def test_start_response_contains_ok(self, client):
        game_id, host_secret = self._create_and_fill(client, 5)
        data = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret}).json()
        assert data.get("ok") is True

    def test_start_with_wrong_secret_returns_403(self, client):
        game_id, _ = self._create_and_fill(client, 5)
        resp = client.post(f"/api/games/{game_id}/start", json={"host_secret": "wrong-secret"})
        assert resp.status_code == 403

    def test_start_with_too_few_players_returns_409(self, client):
        create_data = client.post("/api/games", json={}).json()
        game_id = create_data["game_id"]
        host_secret = create_data["host_secret"]
        for i in range(3):
            register_and_join(client, game_id, f"P{i}")
        resp = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
        assert resp.status_code == 409

    def test_start_with_no_players_returns_409(self, client):
        create_data = client.post("/api/games", json={}).json()
        resp = client.post(f"/api/games/{create_data['game_id']}/start", json={"host_secret": create_data["host_secret"]})
        assert resp.status_code == 409

    def test_start_nonexistent_game_returns_404(self, client):
        resp = client.post("/api/games/NOPE/start", json={"host_secret": "any"})
        assert resp.status_code == 404


@pytest.mark.integration
class TestRejoinGame:
    def test_rejoin_with_valid_token_returns_200(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        token = register_and_join(client, game_id, "Alice")["session_token"]
        resp = client.post(f"/api/games/{game_id}/rejoin", json={"session_token": token})
        assert resp.status_code == 200

    def test_rejoin_returns_same_player_id(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        join_data = register_and_join(client, game_id, "Alice")
        rejoin_data = client.post(f"/api/games/{game_id}/rejoin", json={"session_token": join_data["session_token"]}).json()
        assert rejoin_data["player_id"] == join_data["player_id"]

    def test_rejoin_with_invalid_token_returns_401(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        resp = client.post(f"/api/games/{game_id}/rejoin", json={"session_token": "fake-token-xyz"})
        assert resp.status_code == 401

    def test_rejoin_with_wrong_game_id_returns_401(self, client):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        other_game_id = client.post("/api/games", json={}).json()["game_id"]
        token = register_and_join(client, game_id, "Alice")["session_token"]
        resp = client.post(f"/api/games/{other_game_id}/rejoin", json={"session_token": token})
        assert resp.status_code == 401


@pytest.mark.integration
class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_status_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_returns_schema_version(self, client):
        data = client.get("/health").json()
        assert "schema_version" in data
