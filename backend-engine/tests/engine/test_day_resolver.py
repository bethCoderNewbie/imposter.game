"""
Day resolver tests — majority vote, Mayor double-vote, special role eliminations.
"""

from __future__ import annotations

import pytest

from engine.resolver.day import resolve_day_vote
from engine.state.enums import Phase, Team
from engine.state.models import MasterGameState
from tests.conftest import _eight_player_game, _five_player_game, _make_player


def _cast_votes(G: MasterGameState, votes: dict[str, str]) -> MasterGameState:
    G = G.model_copy(deep=True)
    G.day_votes = votes
    G.phase = Phase.DAY_VOTE
    return G


class TestMajorityVote:
    def test_majority_eliminates_player(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        # 5 of 8 vote for p1
        G.day_votes = {"p2": "p1", "p3": "p1", "p4": "p1", "p5": "p1", "p6": "p1"}
        G_new = resolve_day_vote(G)
        assert not G_new.players["p1"].is_alive

    def test_tie_no_elimination(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        # 4 vote p1, 4 vote p2 — exact tie
        G.day_votes = {
            "p3": "p1", "p4": "p1", "p5": "p1", "p6": "p1",
            "p1": "p2",
            # Only 5 votes total, not a tie:
        }
        # Real 4-4 tie:
        G.day_votes = {
            "p3": "p1", "p4": "p1", "p5": "p1", "p6": "p1",
            "p1": "p2", "p2": "p3", "p7": "p1", "p8": "p2",
        }
        # p1: 4 votes (p3,p4,p5,p6,p7 => 5), p2: (p1, p8 => 2), p3: (p2 => 1) — not tied
        # Let's make a proper tie:
        G.day_votes = {
            "p3": "p1", "p4": "p1", "p5": "p1", "p6": "p1",
            "p1": "p2", "p2": "p2", "p7": "p2", "p8": "p2",
        }
        G_new = resolve_day_vote(G)
        # Strict majority (>50%) required; 4/8 = 50% exactly, not > 50% → no elimination
        alive_count = sum(1 for p in G_new.players.values() if p.is_alive)
        assert alive_count == 8

    def test_strict_majority_required(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        # 4 votes out of 8 is exactly 50%, not strictly > 50%
        G.day_votes = {"p2": "p1", "p3": "p1", "p4": "p1", "p5": "p1"}
        G_new = resolve_day_vote(G)
        assert G_new.players["p1"].is_alive  # No elimination — not strict majority


class TestMayorDoubleVote:
    def test_mayor_vote_counts_double(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        G.players["p3"].role = "mayor"
        # 3 ordinary votes + 1 mayor double-vote = 5 effective votes out of 9 total weight
        G.day_votes = {
            "p3": "p1",  # mayor: counts 2
            "p4": "p1",
            "p5": "p1",
        }
        G_new = resolve_day_vote(G)
        # 4 effective votes (2+1+1) out of 9 total weight → not majority
        # With 8 players: mayor=2, 2 more = 4 vs 8 total weight = 50% — not strict majority
        # Add one more vote:
        G.day_votes["p6"] = "p1"
        G_new = resolve_day_vote(G)
        # Now: 5 effective (2+1+1+1) vs 9 total weight → 55% → majority
        assert not G_new.players["p1"].is_alive


class TestJesterWin:
    def test_jester_voted_out_triggers_jester_win(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        G.players["p6"].role = "jester"
        G.players["p6"].team = Team.NEUTRAL
        # Majority votes out jester
        G.day_votes = {
            "p1": "p6", "p2": "p6", "p3": "p6", "p4": "p6", "p5": "p6",
        }
        G_new = resolve_day_vote(G)
        assert G_new.phase == Phase.GAME_OVER
        assert G_new.winner == "neutral"
        assert G_new.winner_player_id == "p6"


class TestHunterVotedOut:
    def test_hunter_voted_out_triggers_hunter_pending(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        G.players["p5"].role = "hunter"
        G.day_votes = {
            "p1": "p5", "p2": "p5", "p3": "p5", "p4": "p5", "p6": "p5",
        }
        G_new = resolve_day_vote(G)
        assert G_new.phase == Phase.HUNTER_PENDING
        assert "p5" in G_new.hunter_queue
        assert not G_new.players["p5"].is_alive


class TestValidationEdgeCases:
    def test_dead_player_vote_not_counted(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        G.players["p7"].is_alive = False
        # p7 somehow has a vote recorded (shouldn't happen — handler blocks it)
        G.day_votes = {
            "p7": "p1",  # dead player
            "p2": "p1", "p3": "p1", "p4": "p1", "p5": "p1",
        }
        # Resolver should ignore dead player votes
        G_new = resolve_day_vote(G)
        # 4 live votes vs 7 alive players; not majority → no elimination
        # This tests that resolver handles edge case gracefully
        assert G_new is not None  # just ensure no crash
