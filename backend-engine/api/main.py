"""
FastAPI application entry point.
Lifespan: creates/closes Redis connection pool.
Includes lobby REST routes and WebSocket endpoint.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    logger.info("Redis pool created: %s", settings.redis_url)
    yield
    await app.state.redis.aclose()
    logger.info("Redis pool closed.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Werewolf Game Server",
        description="Server-authoritative Werewolf backend — FastAPI + WebSockets + Redis",
        version=settings.schema_version,
        lifespan=lifespan,
    )

    # CORS — permissive for LAN play; tighten for production.
    # allow_credentials must NOT be combined with allow_origins=["*"] — the CORS
    # spec forbids it and Safari strictly rejects the response.  Session tokens
    # are carried in headers/body (not cookies), so credentials are not needed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    from api.lobby.routes import router as lobby_router
    from api.ws.endpoint import router as ws_router

    app.include_router(lobby_router)
    app.include_router(ws_router)

    @app.get("/health", tags=["ops"])
    async def health():
        return {"status": "ok", "schema_version": settings.schema_version}

    return app


app = create_app()
