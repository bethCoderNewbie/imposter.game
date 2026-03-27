"""
Shared fixtures for API integration tests.
Uses fakeredis so no real Redis instance is required.
"""

from __future__ import annotations

import pytest
import fakeredis.aioredis
import redis.asyncio
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_singletons():
    """Clear module-level singletons before/after each test to prevent cross-test leakage."""
    from api import game_queue
    from api.connection_manager import manager

    # Stop any leftover tasks and clear state
    for q in list(game_queue._queues.values()):
        q.stop()
    game_queue._queues.clear()
    manager._rooms.clear()
    yield
    for q in list(game_queue._queues.values()):
        q.stop()
    game_queue._queues.clear()
    manager._rooms.clear()


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def client(fake_redis, monkeypatch):
    """TestClient backed by fakeredis — no real Redis needed."""
    monkeypatch.setattr(redis.asyncio, "from_url", lambda *a, **kw: fake_redis)
    from api.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c
