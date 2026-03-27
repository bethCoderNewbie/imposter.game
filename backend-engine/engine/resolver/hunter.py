"""
Hunter revenge resolver: validates and applies the Hunter's post-death revenge kill.
Pure function — no I/O.
"""

from __future__ import annotations

from engine.resolver._win import check_win_condition
from engine.state.enums import EliminationCause, Phase
from engine.state.models import EliminationEvent, MasterGameState


class HunterError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def resolve_hunter_revenge(
    G: MasterGameState,
    hunter_id: str,
    target_id: str,
) -> MasterGameState:
    """
    Apply Hunter's revenge kill.
    Validates hunter_id is in hunter_queue and hunter has not already fired.
    Eliminates target, pops hunter from queue.
    Re-runs win check when queue is empty.
    Returns new MasterGameState.
    """
    G = G.model_copy(deep=True)

    if hunter_id not in G.hunter_queue:
        raise HunterError("HUNTER_NOT_PENDING", f"Player {hunter_id} is not in the hunter queue.")

    hunter = G.players.get(hunter_id)
    if not hunter:
        raise HunterError("HUNTER_NOT_FOUND", f"Hunter player {hunter_id} not found.")
    if hunter.hunter_fired:
        raise HunterError("HUNTER_ALREADY_FIRED", "Hunter has already used their revenge kill.")

    target = G.players.get(target_id)
    if not target:
        raise HunterError("INVALID_TARGET", f"Target player {target_id} not found.")
    if not target.is_alive:
        raise HunterError("TARGET_ALREADY_DEAD", f"Target player {target_id} is already eliminated.")
    if target_id == hunter_id:
        raise HunterError("SELF_TARGET", "Hunter cannot target themselves.")

    # Apply revenge kill
    hunter.hunter_fired = True
    target.is_alive = False
    G.elimination_log.append(EliminationEvent(
        round=G.round,
        phase=G.phase,  # could be "night" or "day" depending on when Hunter was eliminated
        player_id=target_id,
        cause=EliminationCause.HUNTER_REVENGE,
    ))

    # Pop this hunter from the queue
    G.hunter_queue.remove(hunter_id)

    # If another Hunter was in queue, still pending
    if G.hunter_queue:
        return G

    # All hunters resolved — check win condition and advance phase
    G = check_win_condition(G)
    if G.phase not in (Phase.GAME_OVER, Phase.HUNTER_PENDING):
        # Return to appropriate post-night phase
        # If we came from night resolution: go to DAY
        # If we came from day vote: go to NIGHT (next round)
        # Phase tracking is handled by the intent handler based on pre-hunter phase
        pass

    return G


def resolve_hunter_timeout(G: MasterGameState, hunter_id: str) -> MasterGameState:
    """
    Auto-resolve Hunter pending when timer expires: Hunter's revenge is skipped.
    Pops hunter from queue and continues.
    """
    G = G.model_copy(deep=True)
    if hunter_id in G.hunter_queue:
        hunter = G.players.get(hunter_id)
        if hunter:
            hunter.hunter_fired = True  # mark as used (skipped)
        G.hunter_queue.remove(hunter_id)

    if not G.hunter_queue:
        G = check_win_condition(G)

    return G
