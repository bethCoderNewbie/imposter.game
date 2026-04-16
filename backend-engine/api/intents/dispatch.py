"""
Intent dispatcher: routes intent type to the correct handler.
All handlers return a new MasterGameState (pure — no direct Redis/WS I/O).
"""

from __future__ import annotations

from typing import Any

from engine.state.models import MasterGameState
from api.intents.errors import IntentError
from api.intents.handlers import (
    handle_advance_phase,
    handle_confirm_role_reveal,
    handle_extend_timer,
    handle_force_next,
    handle_grid_defend,
    handle_hunter_revenge,
    handle_pause_timer,
    handle_phase_timeout,
    handle_player_disconnected,
    handle_resume_timer,
    handle_select_grid_node,
    handle_sonar_ping,
    handle_start_game,
    handle_submit_day_vote,
    handle_submit_grid_answer,
    handle_submit_night_action,
    handle_submit_puzzle_answer,
    handle_wolf_charge_update,
)

# Re-export IntentError so callers can import from dispatch as before
__all__ = ["dispatch_intent", "IntentError"]

_HANDLERS = {
    "start_game": handle_start_game,
    "confirm_role_reveal": handle_confirm_role_reveal,
    "submit_night_action": handle_submit_night_action,
    "submit_day_vote": handle_submit_day_vote,
    "hunter_revenge": handle_hunter_revenge,
    "submit_puzzle_answer": handle_submit_puzzle_answer,
    "select_grid_node": handle_select_grid_node,
    "submit_grid_answer": handle_submit_grid_answer,
    "sonar_ping": handle_sonar_ping,
    "wolf_charge_update": handle_wolf_charge_update,
    "grid_defend": handle_grid_defend,
    "advance_phase": handle_advance_phase,
    "pause_timer":   handle_pause_timer,
    "resume_timer":  handle_resume_timer,
    "extend_timer":  handle_extend_timer,
    "force_next":    handle_force_next,
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
