"""
Intent dispatcher: routes intent type to the correct handler.
All handlers return a new MasterGameState (pure — no direct Redis/WS I/O).
"""

from __future__ import annotations

from typing import Any

from engine.state.models import MasterGameState
from api.intents.handlers import (
    handle_advance_phase,
    handle_confirm_role_reveal,
    handle_hunter_revenge,
    handle_phase_timeout,
    handle_player_disconnected,
    handle_start_game,
    handle_submit_day_vote,
    handle_submit_night_action,
    handle_submit_puzzle_answer,
)


class IntentError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


_HANDLERS = {
    "start_game": handle_start_game,
    "confirm_role_reveal": handle_confirm_role_reveal,
    "submit_night_action": handle_submit_night_action,
    "submit_day_vote": handle_submit_day_vote,
    "hunter_revenge": handle_hunter_revenge,
    "submit_puzzle_answer": handle_submit_puzzle_answer,
    "advance_phase": handle_advance_phase,
    "phase_timeout": handle_phase_timeout,
    "player_disconnected": handle_player_disconnected,
}


async def dispatch_intent(
    G: MasterGameState,
    intent: dict[str, Any],
    redis_client,
    connection_manager,
) -> MasterGameState:
    """
    Route an intent to its handler.
    Raises IntentError on validation failures.
    """
    intent_type = intent.get("type")
    handler = _HANDLERS.get(intent_type)

    if handler is None:
        raise IntentError("UNKNOWN_INTENT", f"Unknown intent type: {intent_type!r}")

    return await handler(G, intent, redis_client, connection_manager)
