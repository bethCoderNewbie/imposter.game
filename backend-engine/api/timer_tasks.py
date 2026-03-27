"""
Server-side phase timers.
One asyncio.Task per active game. Fires phase_timeout intent when the deadline passes.
Server-owned timers guarantee phase synchronization across all devices (ADR-001 §3).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# {game_id: asyncio.Task}
_timers: dict[str, asyncio.Task] = {}


async def start_phase_timer(
    game_id: str,
    phase: str,
    timer_ends_at: str,
    enqueue_fn,  # Callable[[dict], Coroutine]
) -> None:
    """
    Cancel any existing timer for this game, then start a new one.
    When it fires: enqueues {"type": "phase_timeout", "game_id": ..., "phase": ...}.
    The intent handler validates that intent.phase == G.phase to reject stale timeouts.
    """
    cancel_phase_timer(game_id)

    deadline = datetime.fromisoformat(timer_ends_at.replace("Z", "+00:00"))
    now = datetime.now(UTC)
    delay = (deadline - now).total_seconds()
    if delay < 0:
        delay = 0.0

    async def _fire():
        try:
            await asyncio.sleep(delay)
            await enqueue_fn({"type": "phase_timeout", "game_id": game_id, "phase": phase})
            logger.info("Phase timeout fired: game=%s phase=%s", game_id, phase)
        except asyncio.CancelledError:
            pass
        finally:
            _timers.pop(game_id, None)

    task = asyncio.create_task(_fire())
    _timers[game_id] = task
    logger.info("Timer started: game=%s phase=%s delay=%.1fs", game_id, phase, delay)


def cancel_phase_timer(game_id: str) -> None:
    """Cancel the pending timer for a game, if any."""
    task = _timers.pop(game_id, None)
    if task and not task.done():
        task.cancel()
        logger.debug("Timer cancelled: game=%s", game_id)
