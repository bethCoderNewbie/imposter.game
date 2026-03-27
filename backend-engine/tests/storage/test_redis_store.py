"""
Unit tests for storage/redis_store.py using fakeredis (no real Redis required).
"""

from __future__ import annotations

import json
import string

import fakeredis.aioredis
import pytest

from engine.config import get_settings
from engine.state.enums import Phase
from storage.redis_store import (
    delete_game,
    issue_session_token,
    load_game,
    revoke_session_token,
    save_game,
    validate_session_token,
)

# Re-use the five-player helper from the shared conftest
from tests.conftest import _five_player_game


# ── Fixtures ────────────────────────────────────────────────────────────────────


@pytest.fixture
async def redis():
    r = fakeredis.aioredis.FakeRedis()
    yield r
    await r.aclose()


@pytest.fixture
def sample_game():
    G, _ = _five_player_game()
    return G


# ── TestLoadGame ─────────────────────────────────────────────────────────────────


class TestLoadGame:
    async def test_returns_none_for_nonexistent_game_id(self, redis):
        result = await load_game(redis, "does-not-exist")
        assert result is None

    async def test_returns_none_for_empty_game_id(self, redis):
        result = await load_game(redis, "")
        assert result is None

    async def test_round_trips_and_returns_master_game_state(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        loaded = await load_game(redis, sample_game.game_id)
        assert loaded is not None

    async def test_round_trip_preserves_game_id(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        loaded = await load_game(redis, sample_game.game_id)
        assert loaded.game_id == sample_game.game_id

    async def test_round_trip_preserves_phase(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        loaded = await load_game(redis, sample_game.game_id)
        assert loaded.phase == sample_game.phase

    async def test_round_trip_preserves_player_count(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        loaded = await load_game(redis, sample_game.game_id)
        assert set(loaded.players.keys()) == set(sample_game.players.keys())

    async def test_round_trip_preserves_night_actions_required_count(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        loaded = await load_game(redis, sample_game.game_id)
        assert loaded.night_actions.actions_required_count == sample_game.night_actions.actions_required_count

    async def test_returns_none_for_corrupted_json(self, redis):
        await redis.set("wolf:game:bad-game", b"not-valid-json{{{{")
        result = await load_game(redis, "bad-game")
        assert result is None

    async def test_returns_none_for_valid_json_that_fails_model_validate(self, redis):
        await redis.set("wolf:game:broken", json.dumps({"garbage_key": True}))
        result = await load_game(redis, "broken")
        assert result is None

    async def test_uses_correct_redis_key_prefix(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        exists = await redis.exists(f"wolf:game:{sample_game.game_id}")
        assert exists == 1

    async def test_different_game_id_returns_none(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        result = await load_game(redis, "completely-different-id")
        assert result is None


# ── TestSaveGame ─────────────────────────────────────────────────────────────────


class TestSaveGame:
    async def test_sets_ttl_on_saved_key(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        ttl = await redis.ttl(f"wolf:game:{sample_game.game_id}")
        settings = get_settings()
        assert 0 < ttl <= settings.redis_game_ttl_seconds

    async def test_overwrites_existing_game(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        updated = sample_game.model_copy(deep=True)
        updated.phase = Phase.DAY
        await save_game(redis, sample_game.game_id, updated)
        loaded = await load_game(redis, sample_game.game_id)
        assert loaded.phase == Phase.DAY

    async def test_serializes_phase_as_string(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        raw = await redis.get(f"wolf:game:{sample_game.game_id}")
        decoded = raw.decode() if isinstance(raw, bytes) else raw
        data = json.loads(decoded)
        # Pydantic serializes enums using their .value; Phase.NIGHT = "night"
        assert isinstance(data["phase"], str)

    async def test_saves_game_with_empty_players(self, redis, sample_game):
        empty = sample_game.model_copy(deep=True)
        empty.players = {}
        await save_game(redis, empty.game_id, empty)
        loaded = await load_game(redis, empty.game_id)
        assert loaded is not None
        assert loaded.players == {}


# ── TestDeleteGame ────────────────────────────────────────────────────────────────


class TestDeleteGame:
    async def test_load_returns_none_after_delete(self, redis, sample_game):
        await save_game(redis, sample_game.game_id, sample_game)
        await delete_game(redis, sample_game.game_id)
        assert await load_game(redis, sample_game.game_id) is None

    async def test_delete_nonexistent_key_does_not_raise(self, redis):
        await delete_game(redis, "ghost-game")  # should not raise

    async def test_delete_only_removes_target_game(self, redis, sample_game):
        from tests.conftest import _eight_player_game
        G2, _ = _eight_player_game()
        await save_game(redis, sample_game.game_id, sample_game)
        await save_game(redis, G2.game_id, G2)
        await delete_game(redis, sample_game.game_id)
        assert await load_game(redis, G2.game_id) is not None


# ── TestIssueSessionToken ─────────────────────────────────────────────────────────


class TestIssueSessionToken:
    async def test_returns_non_empty_string(self, redis):
        token = await issue_session_token(redis, "g1", "p1")
        assert isinstance(token, str)
        assert len(token) > 0

    async def test_token_is_url_safe(self, redis):
        token = await issue_session_token(redis, "g1", "p1")
        allowed = set(string.ascii_letters + string.digits + "-_")
        assert all(c in allowed for c in token)

    async def test_two_calls_produce_different_tokens(self, redis):
        t1 = await issue_session_token(redis, "g1", "p1")
        t2 = await issue_session_token(redis, "g1", "p1")
        assert t1 != t2

    async def test_token_stored_under_correct_key_prefix(self, redis):
        token = await issue_session_token(redis, "g1", "p1")
        exists = await redis.exists(f"wolf:token:{token}")
        assert exists == 1

    async def test_stored_value_is_game_id_colon_player_id(self, redis):
        token = await issue_session_token(redis, "game42", "player99")
        raw = await redis.get(f"wolf:token:{token}")
        value = raw.decode() if isinstance(raw, bytes) else raw
        assert value == "game42:player99"

    async def test_token_has_positive_ttl(self, redis):
        token = await issue_session_token(redis, "g1", "p1")
        ttl = await redis.ttl(f"wolf:token:{token}")
        assert ttl > 0

    async def test_player_id_containing_colon_is_preserved(self, redis):
        # validate_session_token uses split(":", 1) so "game1:a:b" -> ("game1", "a:b")
        token = await issue_session_token(redis, "game1", "a:b")
        result = await validate_session_token(redis, token)
        assert result == ("game1", "a:b")


# ── TestValidateSessionToken ──────────────────────────────────────────────────────


class TestValidateSessionToken:
    async def test_returns_tuple_for_valid_token(self, redis):
        token = await issue_session_token(redis, "g1", "p1")
        result = await validate_session_token(redis, token)
        assert result == ("g1", "p1")

    async def test_returns_none_for_unknown_token(self, redis):
        result = await validate_session_token(redis, "completely-made-up-token")
        assert result is None

    async def test_returns_none_for_empty_string_token(self, redis):
        result = await validate_session_token(redis, "")
        assert result is None

    async def test_handles_bytes_value_from_redis(self, redis):
        await redis.set("wolf:token:tok-bytes", b"g1:p1")
        result = await validate_session_token(redis, "tok-bytes")
        assert result == ("g1", "p1")

    async def test_handles_string_value_from_redis(self, redis):
        await redis.set("wolf:token:tok-str", "g1:p1")
        result = await validate_session_token(redis, "tok-str")
        assert result == ("g1", "p1")

    async def test_returns_none_for_malformed_value_without_colon(self, redis):
        await redis.set("wolf:token:tok-bad", "nodivider")
        result = await validate_session_token(redis, "tok-bad")
        assert result is None


# ── TestRevokeSessionToken ────────────────────────────────────────────────────────


class TestRevokeSessionToken:
    async def test_validate_returns_none_after_revoke(self, redis):
        token = await issue_session_token(redis, "g1", "p1")
        await revoke_session_token(redis, token)
        assert await validate_session_token(redis, token) is None

    async def test_revoke_nonexistent_token_does_not_raise(self, redis):
        await revoke_session_token(redis, "ghost-token")  # should not raise

    async def test_revoke_only_removes_target_token(self, redis):
        tok_a = await issue_session_token(redis, "g1", "p1")
        tok_b = await issue_session_token(redis, "g1", "p2")
        await revoke_session_token(redis, tok_a)
        assert await validate_session_token(redis, tok_b) == ("g1", "p2")

    async def test_token_key_absent_in_redis_after_revoke(self, redis):
        token = await issue_session_token(redis, "g1", "p1")
        await revoke_session_token(redis, token)
        exists = await redis.exists(f"wolf:token:{token}")
        assert exists == 0
