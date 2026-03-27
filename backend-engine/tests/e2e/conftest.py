"""
E2E test fixtures.
Requires a real Redis instance — set REDIS_URL env var or have Redis on localhost:6379.
Tests are skipped automatically when Redis is unavailable.
"""

from __future__ import annotations

import os

import pytest
import redis as sync_redis
from starlette.testclient import TestClient


def _redis_available(url: str) -> bool:
    """Return True if we can ping Redis at the given URL."""
    try:
        r = sync_redis.from_url(url, socket_connect_timeout=2)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def require_redis():
    """Skip the entire module if Redis is not reachable."""
    url = os.getenv("REDIS_URL", "redis://localhost:6379/15")
    if not _redis_available(url):
        pytest.skip(f"Redis not available at {url} — skipping E2E tests")


@pytest.fixture(autouse=True)
def reset_singletons():
    """Clear module-level singletons before/after each test."""
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


@pytest.fixture(scope="module")
def e2e_client():
    """
    TestClient that uses a real Redis instance.
    The app's lifespan connects to REDIS_URL (defaulting to localhost:6379/15).
    """
    from engine.config import get_settings
    # Clear settings cache so REDIS_URL env var is re-read
    get_settings.cache_clear()

    from api.main import create_app
    app = create_app()
    with TestClient(app) as client:
        yield client

    # Clear settings cache after module so other tests aren't affected
    get_settings.cache_clear()
