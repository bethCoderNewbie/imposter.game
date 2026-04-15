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

    # Total eligible vote weight = alive players + dead Ghost (can vote while dead)
    total_eligible_weight: float = sum(
        _voter_weight(pid, G)
        for pid, p in G.players.items()
        if p.is_alive or (not p.is_alive and p.role == "ghost")
    )

    # Build weighted vote tally from actual votes cast
    vote_weight: dict[str, float] = {}

    for voter_pid, target_pid in G.day_votes.items():
        voter = G.players.get(voter_pid)
        if not voter:
            continue
        if not voter.is_alive and voter.role != "ghost":
            continue  # only Ghost can vote while dead
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

    # Wise: burned at the stake disables all village role powers permanently
    if target.role == "wise":
        G.village_powers_cursed = True

    # Priority 1: Jester win check (before generic win check)
    if target.role == "jester":
        G = check_win_condition(G, jester_voted_out_id=top_target)
        return G

    # Lovers death-chain — runs BEFORE hunter check so a Hunter-lover's partner is killed
    partner_id: str | None = None
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

    # Hunter check: both the voted-out player AND their just-killed lover-partner may be Hunters
    hunter_triggered = False
    for hunter_pid in (top_target, partner_id):
        if not hunter_pid:
            continue
        h = G.players.get(hunter_pid)
        if not h or h.hunter_fired or h.role != "hunter":
            continue
        if G.village_powers_cursed and h.team == "village":
            continue
        if hunter_pid not in G.hunter_queue:
            G.hunter_queue.append(hunter_pid)
        hunter_triggered = True

    if hunter_triggered:
        G.phase = Phase.HUNTER_PENDING
        G.timer_ends_at = None
        return G

    G = check_win_condition(G)
    return G


def _voter_weight(voter_pid: str, G: MasterGameState) -> float:
    """Return the vote weight for a voter. Mayor has weight 2, everyone else 1.
    Mayor's double-vote is disabled when village powers are cursed."""
    player = G.players.get(voter_pid)
    if player and player.role == "mayor":
        if G.village_powers_cursed and player.team == "village":
            return 1.0
        role_def = ROLE_REGISTRY.get("mayor", {})
        return float(role_def.get("voteWeight", 2))
    return 1.0
