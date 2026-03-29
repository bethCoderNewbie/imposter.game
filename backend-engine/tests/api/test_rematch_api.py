"""
Integration tests for POST /api/games/{id}/rematch and POST /api/games/{id}/abandon.
Uses fakeredis + TestClient — no real Redis or running server required.

Fixtures override `fake_redis` locally with a FakeServer-backed async client so that
a sync `sync_redis` fixture can share the same backing store for direct state setup.

Markers: pytest.mark.integration
"""

from __future__ import annotations

import json

import fakeredis
import fakeredis.aioredis
import pytest

from engine.state.enums import Phase
from engine.state.models import MasterGameState


# ── Shared-store fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def fake_server():
    return fakeredis.FakeServer()


@pytest.fixture
def fake_redis(fake_server):
    """Override api/conftest fake_redis — uses the shared FakeServer."""
    return fakeredis.aioredis.FakeRedis(server=fake_server, decode_responses=True)


@pytest.fixture
def sync_redis(fake_server):
    """Sync Redis client sharing the same FakeServer as fake_redis."""
    return fakeredis.FakeRedis(server=fake_server, decode_responses=True)


def _set_game_over(sync_redis, game_id: str, winner: str = "village") -> None:
    """Directly mutate game state in Redis to GAME_OVER (sync, no event loop)."""
    raw = sync_redis.get(f"wolf:game:{game_id}")
    assert raw is not None, f"Game {game_id} not found in Redis"
    data = json.loads(raw)
    data["phase"] = "game_over"
    data["winner"] = winner
    sync_redis.set(f"wolf:game:{game_id}", json.dumps(data))


def _load_game_sync(sync_redis, game_id: str) -> MasterGameState:
    raw = sync_redis.get(f"wolf:game:{game_id}")
    assert raw is not None, f"Game {game_id} not found"
    return MasterGameState.model_validate_json(raw)


@pytest.fixture
def game_over_game(client, sync_redis):
    """Create a 5-player lobby, then fast-forward to GAME_OVER via sync Redis."""
    data = client.post("/api/games", json={}).json()
    game_id: str = data["game_id"]
    host_secret: str = data["host_secret"]

    for i in range(5):
        client.post(f"/api/games/{game_id}/join", json={"display_name": f"P{i}"})

    _set_game_over(sync_redis, game_id)
    return game_id, host_secret


# ── POST /{game_id}/rematch ────────────────────────────────────────────────────

@pytest.mark.integration
class TestRematch:
    def test_rematch_returns_200(self, client, game_over_game):
        game_id, host_secret = game_over_game
        resp = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": host_secret})
        assert resp.status_code == 200

    def test_rematch_returns_new_game_id_and_secret(self, client, game_over_game):
        game_id, host_secret = game_over_game
        data = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": host_secret}).json()
        assert "new_game_id" in data
        assert "new_host_secret" in data

    def test_rematch_new_game_id_differs_from_old(self, client, game_over_game):
        game_id, host_secret = game_over_game
        data = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": host_secret}).json()
        assert data["new_game_id"] != game_id

    def test_rematch_new_host_secret_differs_from_old(self, client, game_over_game):
        game_id, host_secret = game_over_game
        data = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": host_secret}).json()
        assert data["new_host_secret"] != host_secret

    def test_rematch_new_game_exists_and_is_joinable(self, client, game_over_game):
        game_id, host_secret = game_over_game
        data = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": host_secret}).json()
        resp = client.post(
            f"/api/games/{data['new_game_id']}/join",
            json={"display_name": "NewPlayer"},
        )
        assert resp.status_code == 200

    def test_rematch_migrates_all_players(self, client, sync_redis, game_over_game):
        game_id, host_secret = game_over_game
        data = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": host_secret}).json()
        new_G = _load_game_sync(sync_redis, data["new_game_id"])
        assert len(new_G.players) == 5

    def test_rematch_migrated_players_have_clean_state(self, client, sync_redis, game_over_game):
        game_id, host_secret = game_over_game
        data = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": host_secret}).json()
        new_G = _load_game_sync(sync_redis, data["new_game_id"])
        for ps in new_G.players.values():
            assert ps.role is None
            assert ps.team is None
            assert ps.is_alive is True

    def test_rematch_preserves_player_names(self, client, sync_redis, game_over_game):
        game_id, host_secret = game_over_game
        old_G = _load_game_sync(sync_redis, game_id)
        old_names = {ps.display_name for ps in old_G.players.values()}

        data = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": host_secret}).json()
        new_G = _load_game_sync(sync_redis, data["new_game_id"])
        new_names = {ps.display_name for ps in new_G.players.values()}

        assert new_names == old_names

    def test_rematch_new_game_is_in_lobby_phase(self, client, sync_redis, game_over_game):
        game_id, host_secret = game_over_game
        data = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": host_secret}).json()
        new_G = _load_game_sync(sync_redis, data["new_game_id"])
        assert new_G.phase == Phase.LOBBY

    def test_rematch_migrated_players_can_rejoin_new_game(self, client, sync_redis, game_over_game):
        game_id, host_secret = game_over_game
        data = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": host_secret}).json()
        new_game_id = data["new_game_id"]
        new_G = _load_game_sync(sync_redis, new_game_id)
        # Any migrated player's session token should work for rejoin
        ps = next(iter(new_G.players.values()))
        resp = client.post(
            f"/api/games/{new_game_id}/rejoin",
            json={"session_token": ps.session_token},
        )
        assert resp.status_code == 200

    def test_rematch_wrong_secret_returns_403(self, client, game_over_game):
        game_id, _ = game_over_game
        resp = client.post(f"/api/games/{game_id}/rematch", json={"host_secret": "wrong"})
        assert resp.status_code == 403

    def test_rematch_nonexistent_game_returns_404(self, client):
        resp = client.post("/api/games/NOPE99/rematch", json={"host_secret": "any"})
        assert resp.status_code == 404

    def test_rematch_on_active_game_returns_409(self, client):
        """Rematch is only valid after GAME_OVER — lobby games must be rejected."""
        data = client.post("/api/games", json={}).json()
        resp = client.post(
            f"/api/games/{data['game_id']}/rematch",
            json={"host_secret": data["host_secret"]},
        )
        assert resp.status_code == 409


# ── POST /{game_id}/abandon ────────────────────────────────────────────────────

@pytest.mark.integration
class TestAbandon:
    def test_abandon_returns_200(self, client, game_over_game):
        game_id, host_secret = game_over_game
        resp = client.post(f"/api/games/{game_id}/abandon", json={"host_secret": host_secret})
        assert resp.status_code == 200

    def test_abandon_response_contains_ok(self, client, game_over_game):
        game_id, host_secret = game_over_game
        data = client.post(f"/api/games/{game_id}/abandon", json={"host_secret": host_secret}).json()
        assert data.get("ok") is True

    def test_abandon_wrong_secret_returns_403(self, client, game_over_game):
        game_id, _ = game_over_game
        resp = client.post(f"/api/games/{game_id}/abandon", json={"host_secret": "wrong"})
        assert resp.status_code == 403

    def test_abandon_nonexistent_game_returns_404(self, client):
        resp = client.post("/api/games/NOPE99/abandon", json={"host_secret": "any"})
        assert resp.status_code == 404

    def test_abandon_on_active_game_returns_409(self, client):
        """Abandon is only valid after GAME_OVER."""
        data = client.post("/api/games", json={}).json()
        resp = client.post(
            f"/api/games/{data['game_id']}/abandon",
            json={"host_secret": data["host_secret"]},
        )
        assert resp.status_code == 409
