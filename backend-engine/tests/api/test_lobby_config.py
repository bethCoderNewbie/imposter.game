"""
Integration tests for PATCH /api/games/{id}/config.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestConfigUpdate:
    def test_patch_difficulty_returns_ok(self, client):
        data = client.post("/api/games", json={}).json()
        r = client.patch(f"/api/games/{data['game_id']}/config",
                         json={"host_secret": data["host_secret"], "difficulty_level": "hard"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_patch_timer_returns_ok(self, client):
        data = client.post("/api/games", json={}).json()
        r = client.patch(f"/api/games/{data['game_id']}/config",
                         json={"host_secret": data["host_secret"], "night_timer_seconds": 90})
        assert r.status_code == 200

    def test_patch_wrong_secret_returns_403(self, client):
        data = client.post("/api/games", json={}).json()
        r = client.patch(f"/api/games/{data['game_id']}/config",
                         json={"host_secret": "wrong", "difficulty_level": "easy"})
        assert r.status_code == 403

    def test_patch_nonexistent_game_returns_404(self, client):
        r = client.patch("/api/games/NOPE/config",
                         json={"host_secret": "x", "difficulty_level": "easy"})
        assert r.status_code == 404

    def test_patch_timer_below_min_returns_422(self, client):
        data = client.post("/api/games", json={}).json()
        r = client.patch(f"/api/games/{data['game_id']}/config",
                         json={"host_secret": data["host_secret"], "night_timer_seconds": 10})
        assert r.status_code == 422

    def test_patch_timer_above_max_accepted(self, client):
        data = client.post("/api/games", json={}).json()
        r = client.patch(f"/api/games/{data['game_id']}/config",
                         json={"host_secret": data["host_secret"], "day_timer_seconds": 9999})
        assert r.status_code == 200

    def test_patch_invalid_difficulty_returns_422(self, client):
        data = client.post("/api/games", json={}).json()
        r = client.patch(f"/api/games/{data['game_id']}/config",
                         json={"host_secret": data["host_secret"], "difficulty_level": "legendary"})
        assert r.status_code == 422

    def test_patch_partial_update_leaves_other_fields_unchanged(self, client):
        data = client.post("/api/games", json={}).json()
        client.patch(f"/api/games/{data['game_id']}/config",
                     json={"host_secret": data["host_secret"], "night_timer_seconds": 30})
        with client.websocket_connect(f"/ws/{data['game_id']}/display") as ws:
            msg = ws.receive_json()
        cfg = msg["state"]["config"]
        assert cfg["night_timer_seconds"] == 30
        assert cfg["day_timer_seconds"] == 180   # unchanged default
        assert cfg["difficulty_level"] == "standard"  # unchanged default

    def test_patch_updates_config_in_state(self, client):
        data = client.post("/api/games", json={}).json()
        client.patch(f"/api/games/{data['game_id']}/config",
                     json={"host_secret": data["host_secret"], "difficulty_level": "easy",
                           "night_timer_seconds": 45})
        with client.websocket_connect(f"/ws/{data['game_id']}/display") as ws:
            msg = ws.receive_json()
        assert msg["state"]["config"]["difficulty_level"] == "easy"
        assert msg["state"]["config"]["night_timer_seconds"] == 45

    def test_patch_broadcasts_update_to_connected_display(self, client):
        data = client.post("/api/games", json={}).json()
        with client.websocket_connect(f"/ws/{data['game_id']}/display") as ws:
            ws.receive_json()  # consume sync
            client.patch(f"/api/games/{data['game_id']}/config",
                         json={"host_secret": data["host_secret"], "difficulty_level": "hard"})
            msg = ws.receive_json()
        assert msg["type"] == "update"
        assert msg["state"]["config"]["difficulty_level"] == "hard"
