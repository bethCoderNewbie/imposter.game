"""
Lobby REST endpoints: create, join, rejoin.
All game lifecycle initialization happens here before WebSocket connection.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from engine.config import get_settings
from engine.setup import setup_game
from engine.state.enums import Phase
from engine.state.models import GameConfig, PlayerState
from storage.db import get_db
from storage.id_gen import new_game_id
from storage.models_db import DBGame, DBGamePlayer, DBPlayer
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
    permanent_id: str
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
    narrator_voice: str | None = None


def _get_redis(request: Request):
    return request.app.state.redis


@router.post("")
async def create_game(body: CreateGameRequest, redis=Depends(_get_redis), db: AsyncSession = Depends(get_db)):
    """Create a new game lobby. Returns game_id and host_secret for the Display client."""
    import secrets
    game_id = new_game_id()
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

    db.add(DBGame(
        game_id=game_id,
        started_at=datetime.now(UTC),
        player_count=0,
    ))
    await db.commit()

    return {
        "game_id": game_id,
        "host_secret": host_secret,
        "join_code": game_id,
    }


@router.post("/{game_id}/join")
async def join_game(game_id: str, body: JoinGameRequest, redis=Depends(_get_redis), db: AsyncSession = Depends(get_db)):
    """Join an existing lobby. Returns player_id and session token."""
    # Look up the player's registered display name
    player_rec = await db.get(DBPlayer, body.permanent_id)
    if player_rec is None:
        raise HTTPException(status_code=404, detail="Player not registered.")

    G = await load_game(redis, game_id)
    if G is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    if G.phase != Phase.LOBBY:
        # Allow re-entry: player was already in this game (token expired / storage cleared)
        existing = next(
            (p for p in G.players.values() if p.permanent_id == body.permanent_id),
            None,
        )
        if existing:
            new_token = await issue_session_token(redis, game_id, existing.player_id)
            G = G.model_copy(deep=True)
            G.players[existing.player_id].is_connected = True
            await save_game(redis, game_id, G)
            return {
                "game_id": game_id,
                "player_id": existing.player_id,
                "session_token": new_token,
            }
        raise HTTPException(status_code=409, detail="Game already started.")
    if len(G.players) >= 16:
        raise HTTPException(status_code=409, detail="Lobby is full.")

    player_id = str(uuid.uuid4())
    G = G.model_copy(deep=True)
    G.players[player_id] = PlayerState(
        player_id=player_id,
        display_name=player_rec.display_name,
        avatar_id=body.avatar_id,
        permanent_id=body.permanent_id,
    )

    # First player to join becomes the host
    if G.host_player_id is None:
        G.host_player_id = player_id

    token = await issue_session_token(redis, game_id, player_id)
    G.players[player_id].session_token = token

    await save_game(redis, game_id, G)

    # Record in game history
    db.add(DBGamePlayer(
        game_id=game_id,
        permanent_id=body.permanent_id,
        per_game_player_id=player_id,
    ))
    game_rec = await db.get(DBGame, game_id)
    if game_rec:
        game_rec.player_count = len(G.players)
    await db.commit()

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

    if body.narrator_voice is not None:
        from pathlib import Path
        from api.narrator.config import get_narrator_settings as _ns
        candidate_dir = Path(_ns().narrator_prebaked_dir) / body.narrator_voice
        if not candidate_dir.exists() or not any(candidate_dir.glob("*.wav")):
            raise HTTPException(status_code=400, detail=f"No prebaked audio for voice '{body.narrator_voice}'")

    G = G.model_copy(deep=True)
    updates: dict = {}
    if body.difficulty_level is not None:
        updates["difficulty_level"] = body.difficulty_level
    for field in ("night_timer_seconds", "day_timer_seconds", "vote_timer_seconds"):
        val = getattr(body, field)
        if val is not None:
            updates[field] = val
    if body.narrator_voice is not None:
        updates["narrator_voice"] = body.narrator_voice

    G.config = G.config.model_copy(update=updates)
    await save_game(redis, game_id, G)

    from api.connection_manager import manager
    await manager.broadcast(game_id, G)

    return {"ok": True}


class RematchRequest(BaseModel):
    host_secret: str


@router.post("/{game_id}/rematch")
async def rematch_game(game_id: str, body: RematchRequest, redis=Depends(_get_redis), db: AsyncSession = Depends(get_db)):
    """Create a new game with the same players. Broadcasts a redirect to all connected sockets."""
    G = await load_game(redis, game_id)
    if G is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    if G.host_secret != body.host_secret:
        raise HTTPException(status_code=403, detail="Invalid host secret.")
    if G.phase != Phase.GAME_OVER:
        raise HTTPException(status_code=409, detail="Game has not ended yet.")

    import secrets
    new_game_id_val = new_game_id()
    new_host_secret = secrets.token_urlsafe(32)

    # Inherit all timer/difficulty settings from the old game
    new_cfg = G.config.model_copy(update={"player_count": 0, "roles": {}})
    new_G = setup_game(new_game_id_val, host_player_id=None, config=new_cfg, host_secret=new_host_secret)

    migration_map: dict[str, tuple[str, str]] = {}
    for old_pid, ps in G.players.items():
        new_pid = str(uuid.uuid4())
        new_token = await issue_session_token(redis, new_game_id_val, new_pid)
        new_G.players[new_pid] = PlayerState(
            player_id=new_pid,
            display_name=ps.display_name,
            avatar_id=ps.avatar_id,
            permanent_id=ps.permanent_id,
        )
        new_G.players[new_pid].session_token = new_token
        migration_map[old_pid] = (new_pid, new_token)

    # Preserve host role across rematch
    if G.host_player_id and G.host_player_id in migration_map:
        new_G.host_player_id = migration_map[G.host_player_id][0]

    await save_game(redis, new_game_id_val, new_G)

    # Record new game + players in history DB
    db.add(DBGame(
        game_id=new_game_id_val,
        started_at=datetime.now(UTC),
        player_count=len(new_G.players),
    ))
    for new_pid, ps in new_G.players.items():
        if ps.permanent_id:
            db.add(DBGamePlayer(
                game_id=new_game_id_val,
                permanent_id=ps.permanent_id,
                per_game_player_id=new_pid,
            ))
    await db.commit()

    from api.connection_manager import manager
    redirect_payload = {
        "type": "redirect",
        "new_game_id": new_game_id_val,
        "players": {
            old_pid: {
                "new_player_id": new_pid,
                "new_session_token": new_token,
            }
            for old_pid, (new_pid, new_token) in migration_map.items()
        },
    }

    # Persist redirect in old game so disconnected players receive it on WS reconnect
    G = G.model_copy(deep=True)
    G.rematch_redirect = redirect_payload
    await save_game(redis, game_id, G)

    await manager.broadcast_raw(game_id, redirect_payload)

    return {"new_game_id": new_game_id_val, "new_host_secret": new_host_secret}


@router.post("/{game_id}/abandon")
async def abandon_game(game_id: str, body: RematchRequest, redis=Depends(_get_redis)):
    """Notify all connected players to return to onboarding (New Match flow)."""
    G = await load_game(redis, game_id)
    if G is None:
        raise HTTPException(status_code=404, detail="Game not found.")
    if G.host_secret != body.host_secret:
        raise HTTPException(status_code=403, detail="Invalid host secret.")
    if G.phase != Phase.GAME_OVER:
        raise HTTPException(status_code=409, detail="Game has not ended yet.")

    from api.connection_manager import manager
    await manager.broadcast_raw(game_id, {"type": "redirect", "new_game_id": None, "players": {}})

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
