"""
FastAPI application entry point.
Lifespan: creates/closes Redis connection pool.
Includes lobby REST routes, WebSocket endpoint, and TTS audio serving (PRD-008).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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

    from storage.db import get_engine
    get_engine()  # warm the async DB connection pool
    logger.info("Postgres pool created: %s", settings.database_url)

    # Start narrator audio cleanup loop if narrator is enabled
    cleanup_task = None
    if settings.narrator_enabled:
        from api.narrator.tts import run_cleanup_loop
        cleanup_task = asyncio.create_task(run_cleanup_loop())
        logger.info("Narrator audio cleanup loop started")

    yield

    if cleanup_task is not None:
        cleanup_task.cancel()
    await app.state.redis.aclose()
    logger.info("Redis pool closed.")
    await get_engine().dispose()
    logger.info("Postgres pool closed.")


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
    from api.players.routes import router as players_router
    from api.ws.endpoint import router as ws_router

    app.include_router(lobby_router)
    app.include_router(players_router)
    app.include_router(ws_router)

    @app.get("/health", tags=["ops"])
    async def health():
        return {"status": "ok", "schema_version": settings.schema_version}

    # TTS audio serving (PRD-008) — serve generated WAV files to display client
    @app.get("/tts/audio/{filename}", tags=["narrator"])
    async def serve_tts_audio(filename: str):
        from api.narrator.config import get_narrator_settings
        cfg = get_narrator_settings()
        audio_path = Path(cfg.narrator_audio_dir) / filename
        if not audio_path.exists() or audio_path.suffix != ".wav":
            raise HTTPException(status_code=404, detail="Audio file not found")
        return FileResponse(str(audio_path), media_type="audio/wav")

    # Prebaked TTS static files (ADR-021) — only mounted when audio dir is populated.
    # Distinct from /tts/audio/ (ephemeral Kokoro files); nginx /tts/ proxy covers both.
    from api.narrator.config import get_narrator_settings as _get_ns
    _prebaked_dir = Path(_get_ns().narrator_prebaked_dir)
    if _prebaked_dir.exists():
        app.mount("/tts/static", StaticFiles(directory=str(_prebaked_dir)), name="prebaked_audio")

    return app


app = create_app()
