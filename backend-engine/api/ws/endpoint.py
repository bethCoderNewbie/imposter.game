"""
WebSocket endpoint: /ws/{game_id}/{player_id}
Authenticates via session token, registers connection, then relays intents to the game queue.
Display client connects as player_id="display" with no token (read-only, stripped view).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.connection_manager import manager
from api.game_queue import get_or_create_queue
from api.intents.dispatch import dispatch_intent
from engine.config import get_settings
from engine.stripper import player_view
from storage.redis_store import load_game, validate_session_token

# ── Sound board side-channel ───────────────────────────────────────────────────
# Allowed sound IDs — validated server-side to prevent arbitrary payload injection
_ALLOWED_SOUNDS = {
    "ambulance", "boom", "burp", "clap", "fail", "fart",
    "gasp", "howl", "laugh", "people", "siren", "spooky",
    "surprise", "walk", "warning", "wolfcry",
    "snoring", "shush", "flashback",
}


async def _handle_trigger_sound(
    game_id: str,
    intent: dict,
    player_id: str | None,
) -> None:
    """
    Broadcast a sound trigger to the display client only.
    Does NOT touch game state or the queue — pure side-channel (PRD-012).
    """
    sound_id = str(intent.get("sound_id", ""))
    if sound_id not in _ALLOWED_SOUNDS:
        return  # silently ignore unrecognised sounds
    player_name = str(intent.get("player_name", ""))[:32]
    await manager.unicast(
        game_id,
        None,  # player_id=None → display client
        {"type": "sound_triggered", "sound_id": sound_id, "player_name": player_name},
    )

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{game_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, player_id: str):
    """
    WebSocket handler for a single player or display client.

    Authentication:
    - Display client: player_id == "display" — no token required, receives display-stripped state
    - Players: must send {"type": "auth", "session_token": "..."} as first message

    After auth, the queue run_loop is started (idempotent) and the socket is registered.
    Subsequent messages are enqueued as intents.
    """
    redis = websocket.app.state.redis

    # Accept connection before auth so we can send error messages
    await websocket.accept()

    is_display = player_id == "display"
    authenticated_player_id: str | None = None

    if is_display:
        authenticated_player_id = None  # display view
    else:
        # Expect first message to be auth
        try:
            auth_msg = await websocket.receive_json()
        except Exception:
            await websocket.close(code=1008, reason="Expected auth message.")
            return

        if auth_msg.get("type") != "auth" or not auth_msg.get("session_token"):
            await websocket.close(code=1008, reason="Missing or invalid auth message.")
            return

        token = auth_msg["session_token"]
        result = await validate_session_token(redis, token)

        if result is None:
            await websocket.send_json({
                "type": "error",
                "code": "AUTH_FAILED",
                "message": "Invalid or expired session token.",
            })
            await websocket.close(code=1008, reason="Auth failed.")
            return

        token_game_id, resolved_player_id = result
        if token_game_id != game_id:
            await websocket.send_json({
                "type": "error",
                "code": "AUTH_FAILED",
                "message": "Token does not match this game.",
            })
            await websocket.close(code=1008, reason="Auth failed.")
            return

        if resolved_player_id != player_id:
            await websocket.send_json({
                "type": "error",
                "code": "AUTH_FAILED",
                "message": "Token player mismatch.",
            })
            await websocket.close(code=1008, reason="Auth failed.")
            return

        authenticated_player_id = player_id

    # Register connection
    await manager.connect(game_id, authenticated_player_id, websocket)

    # Ensure the game queue run loop is active
    queue = get_or_create_queue(game_id)
    queue.start(redis, manager, dispatch_intent)

    # Push current state immediately so the display doesn't wait for next event
    G_init = await load_game(redis, game_id)
    if G_init is not None:
        settings = get_settings()
        stripped = player_view(G_init, authenticated_player_id)
        await websocket.send_text(json.dumps({
            "type": "sync",
            "state_id": G_init.state_id,
            "schema_version": settings.schema_version,
            "state": stripped,
        }))

        # If a rematch occurred while this player was disconnected, replay the
        # redirect immediately so they are forwarded to the new game.
        if (
            not is_display
            and G_init.rematch_redirect
            and authenticated_player_id in G_init.rematch_redirect.get("players", {})
        ):
            await websocket.send_json(G_init.rematch_redirect)
    else:
        await websocket.send_json({
            "type": "error",
            "code": "GAME_NOT_FOUND",
            "message": "Game state not found.",
        })
        await websocket.close(code=1011, reason="Game not found.")
        return

    logger.info("WS connected: game=%s player=%s", game_id, authenticated_player_id or "display")

    try:
        while True:
            data = await websocket.receive_json()
            # Inject metadata so handlers can access player identity
            data["game_id"] = game_id
            if authenticated_player_id and "player_id" not in data:
                data["player_id"] = authenticated_player_id

            # ── Sound board: side-channel — does not mutate game state ──────────
            if data.get("type") == "trigger_sound":
                await _handle_trigger_sound(game_id, data, authenticated_player_id)
                continue

            await queue.enqueue(data)
    except WebSocketDisconnect:
        manager.disconnect(game_id, authenticated_player_id)
        if authenticated_player_id:
            # Notify game loop of disconnection
            await queue.enqueue({
                "type": "player_disconnected",
                "game_id": game_id,
                "player_id": authenticated_player_id,
            })
        logger.info("WS disconnected: game=%s player=%s", game_id, authenticated_player_id or "display")
    except Exception:
        logger.exception("WS error: game=%s player=%s", game_id, authenticated_player_id or "display")
        manager.disconnect(game_id, authenticated_player_id)
