"""
Lobby REST endpoints: create, join, rejoin.
All game lifecycle initialization happens here before WebSocket connection.
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from engine.setup import setup_game
from engine.state.enums import Phase
from engine.state.models import PlayerState
from storage.redis_store import (
    issue_session_token,
    load_game,
    save_game,
    validate_session_token,
)

router = APIRouter(prefix="/api/games", tags=["lobby"])


class CreateGameRequest(BaseModel):
    host_display_name: str = Field(..., min_length=1, max_length=16)
    avatar_id: str = "default_01"


class JoinGameRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=16)
    avatar_id: str = "default_01"


class RejoinGameRequest(BaseModel):
    session_token: str


def _get_redis(request: Request):
    return request.app.state.redis


@router.post("")
async def create_game(body: CreateGameRequest, redis=Depends(_get_redis)):
    """Create a new game lobby. Returns game_id, host player_id, session token, and join URL."""
    game_id = secrets.token_urlsafe(6).upper()
    host_player_id = str(uuid.uuid4())

    G = setup_game(game_id, host_player_id, {})
    G.players[host_player_id].display_name = body.host_display_name
    G.players[host_player_id].avatar_id = body.avatar_id

    token = await issue_session_token(redis, game_id, host_player_id)
    G.players[host_player_id].session_token = token

    await save_game(redis, game_id, G)

    return {
        "game_id": game_id,
        "player_id": host_player_id,
        "session_token": token,
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

    token = await issue_session_token(redis, game_id, player_id)
    G.players[player_id].session_token = token

    await save_game(redis, game_id, G)

    # Broadcast updated lobby state to all connected sockets
    from api.connection_manager import manager
    await manager.broadcast(game_id, G)

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

    return {
        "game_id": game_id,
        "player_id": player_id,
        "session_token": body.session_token,
    }
