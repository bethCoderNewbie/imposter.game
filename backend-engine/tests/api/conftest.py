"""
Shared fixtures for API integration tests.
Uses fakeredis (no real Redis) and in-memory SQLite (no real Postgres).
"""

from __future__ import annotations

import asyncio

import fakeredis.aioredis
import pytest
import redis.asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient


async def _create_tables(engine):
    from storage.models_db import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Clear module-level singletons before/after each test to prevent cross-test leakage."""
    from api import game_queue
    from api.connection_manager import manager

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
    """TestClient backed by fakeredis + in-memory SQLite — no external services needed."""
    monkeypatch.setattr(redis.asyncio, "from_url", lambda *a, **kw: fake_redis)

    # In-memory SQLite replaces Postgres for tests
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    asyncio.run(_create_tables(test_engine))

    import storage.db as db_module
    monkeypatch.setattr(db_module, "_engine", test_engine)
    monkeypatch.setattr(db_module, "_session_factory", test_session_factory)

    from api.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c

    asyncio.run(test_engine.dispose())
