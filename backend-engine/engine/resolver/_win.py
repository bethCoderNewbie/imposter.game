"""
Win condition checker. Called after every elimination.
Priority 1: Jester (voted_out_by_village) — checked before team wins.
Priority 2: team wins (wolves_win, village_wins) and neutral solos.
"""

from __future__ import annotations

from engine.state.enums import Phase
from engine.state.models import MasterGameState


def check_win_condition(G: MasterGameState, jester_voted_out_id: str | None = None) -> MasterGameState:
    """
    Returns G with winner/phase set if a win condition is met, else returns G unchanged.
    jester_voted_out_id: set when a Jester was just eliminated via village vote.
    """
    # Priority 1: Jester wins when voted out by the village
    if jester_voted_out_id is not None:
        player = G.players.get(jester_voted_out_id)
        if player and player.role == "jester":
            G = G.model_copy(deep=True)
            G.winner = "neutral"
            G.winner_player_id = jester_voted_out_id
            G.phase = Phase.GAME_OVER
            G.timer_ends_at = None
            return _reveal_roles_on_game_over(G)

    living = [p for p in G.players.values() if p.is_alive]
    wolves_alive = [p for p in living if p.team == "werewolf"]
    sk_alive = [p for p in living if p.role == "serial_killer"]
    arsonist_alive = [p for p in living if p.role == "arsonist"]
    neutral_killers_alive = sk_alive + arsonist_alive

    # Village wins: all wolves AND all neutral killers eliminated
    if len(wolves_alive) == 0 and len(neutral_killers_alive) == 0:
        G = G.model_copy(deep=True)
        G.winner = "village"
        G.phase = Phase.GAME_OVER
        G.timer_ends_at = None
        return _reveal_roles_on_game_over(G)

    # Wolves win: wolves equal or outnumber ALL non-wolf living players (village + neutrals)
    # SK and Arsonist oppose wolves at the vote, so they count toward opposition for parity
    non_wolf_alive = [p for p in living if p.team != "werewolf"]
    if len(wolves_alive) >= len(non_wolf_alive):
        G = G.model_copy(deep=True)
        G.winner = "werewolf"
        G.phase = Phase.GAME_OVER
        G.timer_ends_at = None
        return _reveal_roles_on_game_over(G)

    # Neutral killer win: only neutral killers remain (all wolves and village dead)
    non_killer_alive = [p for p in living if p not in neutral_killers_alive]
    if neutral_killers_alive and len(non_killer_alive) == 0:
        G = G.model_copy(deep=True)
        if sk_alive and arsonist_alive:
            # Simultaneous last-standing — draw (per roles.json note, line 673)
            G.winner = "draw"
            G.winner_player_id = None
        elif sk_alive:
            G.winner = "neutral"
            G.winner_player_id = sk_alive[0].player_id
        else:  # arsonist alone
            G.winner = "neutral"
            G.winner_player_id = arsonist_alive[0].player_id
        G.phase = Phase.GAME_OVER
        G.timer_ends_at = None
        return _reveal_roles_on_game_over(G)

    return G


def _reveal_roles_on_game_over(G: MasterGameState) -> MasterGameState:
    """Populate elimination_log[*].role and saved_by_doctor for the game_over broadcast."""
    for event in G.elimination_log:
        if event.role is None:
            player = G.players.get(event.player_id)
            if player and player.role != "ghost":  # Ghost identity is never revealed
                event.role = player.role
    return G
