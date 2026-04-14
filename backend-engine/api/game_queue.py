"""
Per-game async queue: serializes all state mutations for a game.
One asyncio.Queue and one asyncio.Task per active game.
All state mutations flow through this queue — no locks needed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# {game_id: GameQueue}
_queues: dict[str, "GameQueue"] = {}


class GameQueue:
    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def enqueue(self, intent: dict[str, Any]) -> None:
        await self._queue.put(intent)

    def start(self, redis_client, connection_manager, dispatch_fn) -> None:
        """Start the run_loop task if not already running."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run_loop(redis_client, connection_manager, dispatch_fn)
            )

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        _queues.pop(self.game_id, None)

    async def _run_loop(self, redis_client, connection_manager, dispatch_fn) -> None:
        """
        Main processing loop. For each intent:
        1. Load G from Redis
        2. Validate state_id fence (reject stale intents)
        3. Dispatch to handler
        4. Increment state_id
        5. Save G' to Redis
        6. Broadcast G' to all connected sockets
        """
        from storage.redis_store import load_game, save_game

        while True:
            try:
                intent = await self._queue.get()
                intent_type = intent.get("type", "")
                game_id = intent.get("game_id", self.game_id)

                G = await load_game(redis_client, game_id)
                if G is None:
                    logger.warning("Game not found in Redis: %s (intent: %s)", game_id, intent_type)
                    continue

                # State ID fence: reject stale player intents (not system intents)
                system_intents = {"phase_timeout", "player_disconnected"}
                if intent_type not in system_intents:
                    intent_state_id = intent.get("state_id")
                    if intent_state_id is not None and intent_state_id != G.state_id:
                        await connection_manager.unicast(
                            game_id,
                            intent.get("player_id"),
                            {
                                "type": "error",
                                "code": "STALE_STATE",
                                "message": "Your action was based on an outdated game state. Please retry.",
                            },
                        )
                        continue

                try:
                    G_new = await dispatch_fn(G, intent, redis_client, connection_manager)
                except Exception as e:
                    code = getattr(e, "code", "INTERNAL_ERROR")
                    message = getattr(e, "message", str(e))
                    logger.exception("Intent error: game=%s type=%s", game_id, intent_type)
                    await connection_manager.unicast(
                        game_id,
                        intent.get("player_id"),
                        {"type": "error", "code": code, "message": message},
                    )
                    continue

                G_new.state_id += 1
                await save_game(redis_client, game_id, G_new)
                await connection_manager.broadcast(game_id, G_new)

                # Stop loop if game is over
                from engine.state.enums import Phase
                if G_new.phase == Phase.GAME_OVER:
                    logger.info("Game over — stopping queue: %s", game_id)
                    _queues.pop(game_id, None)
                    # Fire-and-forget: persist outcome to Postgres history
                    from storage.db_writes import record_game_over
                    asyncio.ensure_future(record_game_over(G_new))
                    return

            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Unhandled error in game_queue run_loop: game=%s", self.game_id)


def get_or_create_queue(game_id: str) -> "GameQueue":
    if game_id not in _queues:
        _queues[game_id] = GameQueue(game_id)
    return _queues[game_id]
