"""
Lobby REST endpoints: create, join, rejoin.
All game lifecycle initialization happens here before WebSocket connection.
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from engine.config import get_settings
from engine.setup import setup_game
from engine.state.enums import Phase
from engine.state.models import GameConfig, PlayerState
from storage.redis_store import (
    issue_session_token,
    load_game,
    save_game,
    validate_session_token,
)

router = APIRouter(prefix="/api/games", tags=["lobby"])


class CreateGameRequest(BaseModel):
    pass  # Display creates the game; no host player needed


class JoinGameRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=16)
    avatar_id: str = "default_01"


class RejoinGameRequest(BaseModel):
    session_token: str


class StartGameRequest(BaseModel):
    host_secret: str


class ConfigUpdateRequest(BaseModel):
    host_secret: str
    difficulty_level: str | None = None
    night_timer_seconds: int | None = None
    day_timer_seconds: int | None = None
    vote_timer_seconds: int | None = None


def _get_redis(request: Request):
    return request.app.state.redis


@router.post("")
async def create_game(body: CreateGameRequest, redis=Depends(_get_redis)):
    """Create a new game lobby. Returns game_id and host_secret for the Display client."""
    game_id = secrets.token_urlsafe(6).upper()
    host_secret = secrets.token_urlsafe(32)

    settings = get_settings()
    cfg = GameConfig(
        player_count=0,
        roles={},
        night_timer_seconds=settings.night_timer_seconds,
        day_timer_seconds=settings.day_timer_seconds,
        vote_timer_seconds=settings.vote_timer_seconds,
        role_deal_timer_seconds=settings.role_deal_timer_seconds,
        hunter_pending_timer_seconds=settings.hunter_pending_timer_seconds,
    )
    G = setup_game(game_id, host_player_id=None, config=cfg, host_secret=host_secret)
    await save_game(redis, game_id, G)

    return {
        "game_id": game_id,
        "host_secret": host_secret,
        "join_code": game_id,
    }


@router.post("/{game_id}/join")
async def join_game(game_id: str, body: JoinGameRequest, redis=Depends(_get_redis)):
    """Join an existing lobby. Returns player_id and session token."""
    G = await load_game(redis, game_id)
    if G is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    if G.phase != Phase.LOBBY:
        raise HTTPException(status_code=409, detail="Game already started.")
    if len(G.players) >= 16:
        raise HTTPException(status_code=409, detail="Lobby is full.")

    player_id = str(uuid.uuid4())
    G = G.model_copy(deep=True)
    G.players[player_id] = PlayerState(
        player_id=player_id,
        display_name=body.display_name,
        avatar_id=body.avatar_id,
    )

    # First player to join becomes the host
    if G.host_player_id is None:
        G.host_player_id = player_id

    token = await issue_session_token(redis, game_id, player_id)
    G.players[player_id].session_token = token

    await save_game(redis, game_id, G)

    # Broadcast updated lobby state to all connected sockets
    from api.connection_manager import manager
    await manager.broadcast(game_id, G)
    await manager.broadcast_roster(game_id, list(G.players.values()))

    return {
        "game_id": game_id,
        "player_id": player_id,
        "session_token": token,
    }


@router.post("/{game_id}/rejoin")
async def rejoin_game(game_id: str, body: RejoinGameRequest, redis=Depends(_get_redis)):
    """Reconnect using a stored session token. Returns player_id for WS reconnect."""
    result = await validate_session_token(redis, body.session_token)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")

    token_game_id, player_id = result
    if token_game_id != game_id:
        raise HTTPException(status_code=401, detail="Token does not match this game.")

    G = await load_game(redis, game_id)
    if G is None:
        raise HTTPException(status_code=404, detail="Game not found.")

    if player_id not in G.players:
        raise HTTPException(status_code=404, detail="Player not found in game.")

    G = G.model_copy(deep=True)
    G.players[player_id].is_connected = True
    await save_game(redis, game_id, G)

    from api.connection_manager import manager
    await manager.broadcast_roster(game_id, list(G.players.values()))

    return {
        "game_id": game_id,
        "player_id": player_id,
        "session_token": body.session_token,
    }


@router.patch("/{game_id}/config")
async def update_game_config(game_id: str, body: ConfigUpdateRequest, redis=Depends(_get_redis)):
    """Update difficulty level and/or phase timers while game is in lobby phase."""
    G = await load_game(redis, game_id)
    if G is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    if G.host_secret != body.host_secret:
        raise HTTPException(status_code=403, detail="Invalid host secret.")
    if G.phase != Phase.LOBBY:
        raise HTTPException(status_code=409, detail="Game already started.")

    if body.difficulty_level is not None:
        if body.difficulty_level not in ("easy", "standard", "hard"):
            raise HTTPException(status_code=422, detail="difficulty_level must be easy, standard, or hard.")

    TIMER_BOUNDS = {
        "night_timer_seconds":  (30, 120),
        "day_timer_seconds":    (60, 300),
        "vote_timer_seconds":   (30, 120),
    }
    for field, (lo, hi) in TIMER_BOUNDS.items():
        val = getattr(body, field)
        if val is not None and not (lo <= val <= hi):
            raise HTTPException(status_code=422, detail=f"{field} must be {lo}–{hi}.")

    G = G.model_copy(deep=True)
    updates: dict = {}
    if body.difficulty_level is not None:
        updates["difficulty_level"] = body.difficulty_level
    for field in ("night_timer_seconds", "day_timer_seconds", "vote_timer_seconds"):
        val = getattr(body, field)
        if val is not None:
            updates[field] = val

    G.config = G.config.model_copy(update=updates)
    await save_game(redis, game_id, G)

    from api.connection_manager import manager
    await manager.broadcast(game_id, G)

    return {"ok": True}


@router.post("/{game_id}/start")
async def start_game_via_display(game_id: str, body: StartGameRequest, redis=Depends(_get_redis)):
    """Allow the Display client to start the game using its host_secret."""
    G = await load_game(redis, game_id)
    if G is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    if G.host_secret != body.host_secret:
        raise HTTPException(status_code=403, detail="Invalid host secret.")
    if G.phase != Phase.LOBBY:
        raise HTTPException(status_code=409, detail="Game already started.")
    if G.host_player_id is None:
        raise HTTPException(status_code=409, detail="No players have joined yet.")
    if len(G.players) < 5:
        shortage = 5 - len(G.players)
        raise HTTPException(status_code=409, detail=f"Need {shortage} more player{'s' if shortage != 1 else ''} to start.")

    from api.connection_manager import manager
    from api.game_queue import get_or_create_queue
    from api.intents.dispatch import dispatch_intent

    queue = get_or_create_queue(game_id)
    queue.start(redis, manager, dispatch_intent)
    await queue.enqueue({
        "type": "start_game",
        "game_id": game_id,
        "player_id": G.host_player_id,
    })

    return {"ok": True}
