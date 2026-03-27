"""
WebSocket connection manager.
Tracks active sockets per game room.
Calls player_view() per socket on every broadcast — this is where security is enforced.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from engine.config import get_settings
from engine.state.models import MasterGameState
from engine.stripper import player_view

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # {game_id: {player_id | None: WebSocket}}
        # player_id=None is the display client
        self._rooms: dict[str, dict[str | None, WebSocket]] = {}

    async def connect(self, game_id: str, player_id: str | None, ws: WebSocket) -> None:
        await ws.accept()
        if game_id not in self._rooms:
            self._rooms[game_id] = {}
        self._rooms[game_id][player_id] = ws
        logger.info("Connected: game=%s player=%s", game_id, player_id or "display")

    def disconnect(self, game_id: str, player_id: str | None) -> None:
        room = self._rooms.get(game_id, {})
        room.pop(player_id, None)
        if not room:
            self._rooms.pop(game_id, None)
        logger.info("Disconnected: game=%s player=%s", game_id, player_id or "display")

    async def broadcast(self, game_id: str, G: MasterGameState) -> None:
        """
        Send a stripped state update to every socket in the game room.
        player_view() is called per socket — security is enforced here.
        """
        room = self._rooms.get(game_id, {})
        settings = get_settings()
        dead_sockets: list[str | None] = []

        for pid, ws in list(room.items()):
            stripped = player_view(G, pid)
            payload = {
                "type": "state_update",
                "state_id": G.state_id,
                "schema_version": settings.schema_version,
                "state": stripped,
            }
            try:
                await ws.send_text(json.dumps(payload))
            except (WebSocketDisconnect, RuntimeError):
                dead_sockets.append(pid)

        for pid in dead_sockets:
            self.disconnect(game_id, pid)

    async def unicast(self, game_id: str, player_id: str | None, payload: dict[str, Any]) -> None:
        """Send a payload to a single socket only (hints, errors)."""
        room = self._rooms.get(game_id, {})
        ws = room.get(player_id)
        if ws is None:
            return
        try:
            await ws.send_text(json.dumps(payload))
        except (WebSocketDisconnect, RuntimeError):
            self.disconnect(game_id, player_id)

    def is_connected(self, game_id: str, player_id: str | None) -> bool:
        return player_id in self._rooms.get(game_id, {})

    def player_count(self, game_id: str) -> int:
        return len(self._rooms.get(game_id, {}))


# Singleton — shared across all WebSocket connections
manager = ConnectionManager()
