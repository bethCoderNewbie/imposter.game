"""
Day vote resolver: tallies votes, handles Mayor double-vote, Jester win, Hunter trigger.
Pure function — no I/O.
"""

from __future__ import annotations

from engine.resolver._win import check_win_condition
from engine.roles_loader import ROLE_REGISTRY
from engine.state.enums import EliminationCause, Phase
from engine.state.models import EliminationEvent, MasterGameState


def resolve_day_vote(G: MasterGameState) -> MasterGameState:
    """
    Tally day_votes with Mayor double-vote weighting.
    Strict majority (> 50% of weighted votes cast) required for elimination.
    Tie = no elimination.
    Jester priority-1 win if eliminated.
    Hunter triggers hunter_pending if eliminated.
    Returns new MasterGameState.
    """
    G = G.model_copy(deep=True)

    if not G.day_votes:
        # No votes cast — no elimination, move on
        return G

    # Total eligible vote weight = sum of all alive players' weights
    total_eligible_weight: float = sum(
        _voter_weight(pid, G)
        for pid, p in G.players.items()
        if p.is_alive
    )

    # Build weighted vote tally from actual votes cast
    vote_weight: dict[str, float] = {}

    for voter_pid, target_pid in G.day_votes.items():
        voter = G.players.get(voter_pid)
        if not voter or not voter.is_alive:
            continue  # dead players cannot vote
        if voter_pid == target_pid:
            continue  # self-vote not allowed

        weight = _voter_weight(voter_pid, G)
        vote_weight[target_pid] = vote_weight.get(target_pid, 0.0) + weight

    total_weight = total_eligible_weight

    if not vote_weight or total_weight == 0:
        return G

    # Find the player with the most weighted votes
    top_target = max(vote_weight, key=lambda t: vote_weight[t])
    top_votes = vote_weight[top_target]

    # Strict majority: top candidate must have > 50% of total weight
    if top_votes <= total_weight / 2:
        return G  # tie or no majority — no elimination

    target = G.players.get(top_target)
    if not target or not target.is_alive:
        return G

    # Eliminate the target
    target.is_alive = False
    G.elimination_log.append(EliminationEvent(
        round=G.round,
        phase="day",
        player_id=top_target,
        cause=EliminationCause.VILLAGE_VOTE,
    ))

    # Priority 1: Jester win check (before generic win check)
    if target.role == "jester":
        G = check_win_condition(G, jester_voted_out_id=top_target)
        return G

    # Hunter: trigger hunter_pending
    if target.role == "hunter" and not target.hunter_fired:
        G.hunter_queue.append(top_target)
        G.phase = Phase.HUNTER_PENDING
        G.timer_ends_at = None
        return G

    # Lovers death-chain
    if G.lovers_pair and top_target in G.lovers_pair:
        partner_id = G.lovers_pair[1] if G.lovers_pair[0] == top_target else G.lovers_pair[0]
        partner = G.players.get(partner_id)
        if partner and partner.is_alive:
            partner.is_alive = False
            G.elimination_log.append(EliminationEvent(
                round=G.round,
                phase="day",
                player_id=partner_id,
                cause=EliminationCause.BROKEN_HEART,
            ))
            # Broken-heart death may also trigger Hunter
            if partner.role == "hunter" and not partner.hunter_fired:
                G.hunter_queue.append(partner_id)
                G.phase = Phase.HUNTER_PENDING
                G.timer_ends_at = None
                return G

    G = check_win_condition(G)
    return G


def _voter_weight(voter_pid: str, G: MasterGameState) -> float:
    """Return the vote weight for a voter. Mayor has weight 2, everyone else 1."""
    player = G.players.get(voter_pid)
    if player and player.role == "mayor":
        role_def = ROLE_REGISTRY.get("mayor", {})
        return float(role_def.get("voteWeight", 2))
    return 1.0
