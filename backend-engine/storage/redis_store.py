"""
Redis session store: load/save MasterGameState and manage session tokens.
All game sessions use TTL-based storage (4 hours). No PostgreSQL.
"""

from __future__ import annotations

import json
import secrets
import logging
from typing import Any

from engine.config import get_settings
from engine.state.models import MasterGameState

logger = logging.getLogger(__name__)

_GAME_KEY_PREFIX = "wolf:game:"
_TOKEN_KEY_PREFIX = "wolf:token:"


def _game_key(game_id: str) -> str:
    return f"{_GAME_KEY_PREFIX}{game_id}"


def _token_key(token: str) -> str:
    return f"{_TOKEN_KEY_PREFIX}{token}"


async def load_game(redis, game_id: str) -> MasterGameState | None:
    """Load and deserialize a MasterGameState from Redis. Returns None if not found."""
    raw = await redis.get(_game_key(game_id))
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return MasterGameState.model_validate(data)
    except Exception:
        logger.exception("Failed to deserialize game state: game=%s", game_id)
        return None


async def save_game(redis, game_id: str, G: MasterGameState) -> None:
    """Serialize and save MasterGameState to Redis with TTL."""
    settings = get_settings()
    raw = G.model_dump_json()
    await redis.set(_game_key(game_id), raw, ex=settings.redis_game_ttl_seconds)


async def delete_game(redis, game_id: str) -> None:
    await redis.delete(_game_key(game_id))


async def issue_session_token(redis, game_id: str, player_id: str) -> str:
    """Generate and store a session token for reconnect authentication."""
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    value = f"{game_id}:{player_id}"
    await redis.set(_token_key(token), value, ex=settings.redis_game_ttl_seconds)
    return token


async def validate_session_token(redis, token: str) -> tuple[str, str] | None:
    """
    Validate a session token. Returns (game_id, player_id) or None if invalid.
    """
    raw = await redis.get(_token_key(token))
    if raw is None:
        return None
    try:
        decoded = raw.decode() if isinstance(raw, bytes) else raw
        game_id, player_id = decoded.split(":", 1)
        return game_id, player_id
    except (ValueError, AttributeError):
        return None


async def revoke_session_token(redis, token: str) -> None:
    await redis.delete(_token_key(token))
