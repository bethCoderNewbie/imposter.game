"""
Phase machine: pure functions for transitioning game phases and computing auto-advance.
No I/O — all functions return new MasterGameState instances.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from engine.roles_loader import ROLE_REGISTRY, WAKE_ORDER
from engine.state.enums import Phase
from engine.state.models import MasterGameState, NightActions


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _timer_for_phase(phase: Phase, config) -> str | None:
    """Return ISO8601 UTC timer_ends_at for timed phases, None for untimed."""
    seconds_map = {
        Phase.ROLE_DEAL: config.role_deal_timer_seconds,
        Phase.NIGHT: config.night_timer_seconds,
        Phase.DAY: config.day_timer_seconds,
        Phase.DAY_VOTE: config.vote_timer_seconds,
        Phase.HUNTER_PENDING: config.hunter_pending_timer_seconds,
    }
    seconds = seconds_map.get(phase)
    if seconds is None:
        return None
    deadline = _utcnow() + timedelta(seconds=seconds)
    return deadline.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def compute_actions_required(G: MasterGameState) -> int:
    """
    Count living players who have an active night role this round.
    Villagers (wakeOrder == 0) are excluded — they run a decoy task and never block auto-advance.
    Cupid is excluded after round 1 (actionPhase == "night_one_only" and round > 1).
    """
    count = 0
    for pid, player in G.players.items():
        if not player.is_alive:
            continue
        role_id = player.role
        if role_id is None:
            continue
        role_def = ROLE_REGISTRY.get(role_id, {})
        wake_order = role_def.get("wakeOrder", 0)
        action_phase = role_def.get("actionPhase", "none")
        if wake_order == 0:
            continue
        if action_phase == "night_one_only" and G.round > 1:
            continue
        if action_phase in ("none", "day", "on_death"):
            continue
        count += 1
    return count


def transition_phase(G: MasterGameState, new_phase: Phase) -> MasterGameState:
    """
    Transition to a new phase. Applies all entry side-effects:
    - Sets/clears timer_ends_at
    - Resets per-night fields on NIGHT entry
    - Increments round on NIGHT entry (after round 0)
    - Clears day_votes on DAY entry
    Returns a new MasterGameState. Never mutates in place.
    """
    G = G.model_copy(deep=True)

    if new_phase == Phase.NIGHT:
        # Increment round only when coming from a phase after the initial role_deal
        if G.phase not in (Phase.ROLE_DEAL, Phase.LOBBY):
            G.round += 1
        # Reset all per-night player fields
        for player in G.players.values():
            player.is_protected = False
            player.is_framed_tonight = False
            player.night_action_submitted = False
        # Clear votes from previous round
        G.day_votes = {}
        for player in G.players.values():
            player.vote_target_id = None
        # Reset night actions
        required = compute_actions_required(G)
        G.night_actions = NightActions(
            actions_submitted_count=0,
            actions_required_count=required,
        )
        # Generate a distinct Archive puzzle per wakeOrder==0 player (logic/math/sequence)
        from engine.puzzle_bank import generate_night_puzzle
        for pid, player in G.players.items():
            if not player.is_alive:
                player.puzzle_state = None
                continue
            role_def = ROLE_REGISTRY.get(player.role or "", {})
            if role_def.get("wakeOrder", 0) == 0:
                player.puzzle_state = generate_night_puzzle(G, pid)
            else:
                player.puzzle_state = None

    elif new_phase == Phase.DAY:
        # Clear day votes for fresh discussion phase
        G.day_votes = {}
        for player in G.players.values():
            player.vote_target_id = None

    elif new_phase == Phase.DAY_VOTE:
        # Voting sub-phase: keep day_votes cleared (should be from DAY transition)
        pass

    elif new_phase == Phase.ROLE_DEAL:
        # Reset role confirmations
        for player in G.players.values():
            player.role_confirmed = False

    G.phase = new_phase
    G.timer_ends_at = _timer_for_phase(new_phase, G.config)
    return G


def should_auto_advance(G: MasterGameState) -> bool:
    """
    Return True if the current phase should auto-advance without waiting for the timer.

    Night: True when all active-role players have submitted.
    Day_vote: True when all living players have voted.
    Role_deal: True when all players have confirmed their role.
    """
    if G.phase == Phase.NIGHT:
        required = G.night_actions.actions_required_count
        submitted = G.night_actions.actions_submitted_count
        return required > 0 and submitted >= required

    if G.phase == Phase.DAY_VOTE:
        living = [p for p in G.players.values() if p.is_alive]
        if not living:
            return False
        alive_count = len(living)
        # Check vote_target_id first (set by handler), fall back to day_votes count
        voted_via_field = sum(1 for p in living if p.vote_target_id is not None)
        voted_via_dict = sum(1 for pid in G.day_votes if G.players.get(pid) and G.players[pid].is_alive)
        voted = max(voted_via_field, voted_via_dict)
        return voted >= alive_count

    if G.phase == Phase.ROLE_DEAL:
        return all(p.role_confirmed for p in G.players.values())

    return False
