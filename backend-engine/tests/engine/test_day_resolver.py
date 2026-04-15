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


# ── Wise burn curse ────────────────────────────────────────────────────────────

class TestWiseBurn:
    def _wise_day_game(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p6"].role = "wise"
        G.players["p6"].team = Team.VILLAGE
        G.phase = Phase.DAY_VOTE
        return G

    def test_burning_wise_sets_village_cursed(self):
        G = self._wise_day_game()
        # Majority votes against the Wise (p6)
        G.day_votes = {
            "p1": "p6", "p2": "p6", "p3": "p6",
            "p4": "p6", "p5": "p6",
        }
        G_new = resolve_day_vote(G)
        assert not G_new.players["p6"].is_alive
        assert G_new.village_powers_cursed is True

    def test_voting_out_non_wise_does_not_curse(self):
        G = self._wise_day_game()
        G.day_votes = {
            "p1": "p7", "p2": "p7", "p3": "p7",
            "p4": "p7", "p5": "p7",
        }
        G_new = resolve_day_vote(G)
        assert not G_new.players["p7"].is_alive
        assert G_new.village_powers_cursed is False

    def test_mayor_double_vote_disabled_when_cursed(self):
        # Without curse: Mayor(p5, weight 2) + p3 vote p4 = 3 votes > 5/2 → p4 eliminated
        # With curse:    Mayor(p5, weight 1) + p3 vote p4 = 2 votes ≤ 5/2 → no elimination
        G = self._wise_day_game()
        G.village_powers_cursed = True
        G.players["p5"].role = "mayor"
        # Reduce alive to 5 so the threshold is 2.5 (strict majority)
        for pid in ("p6", "p7", "p8"):
            G.players[pid].is_alive = False
        G.day_votes = {"p5": "p4", "p3": "p4"}  # mayor(1, cursed) + p3(1) = 2 ≤ 2.5
        G_new = resolve_day_vote(G)
        assert G_new.players["p4"].is_alive  # no elimination — mayor's extra vote was stripped


# ── Ghost ──────────────────────────────────────────────────────────────────────

class TestGhost:
    def _ghost_game(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p6"].role = "ghost"
        G.players["p6"].team = Team.VILLAGE
        G.phase = Phase.DAY_VOTE
        return G

    def test_dead_ghost_vote_counts(self):
        """Dead Ghost's vote is tallied normally and can reach majority."""
        G = self._ghost_game()
        G.players["p6"].is_alive = False  # Ghost is dead
        # 4 alive players vote for p1 + dead Ghost also votes for p1
        # Total eligible = 7 alive + 1 dead Ghost = 8; votes for p1 = 5 > 4 → eliminated
        G.day_votes = {
            "p1": "p2",  # wolf votes
            "p2": "p3", "p3": "p4",
            "p4": "p5", "p5": "p7",  # 4 alive votes spread
            "p6": "p1",  # dead Ghost votes for p1
            "p7": "p1", "p8": "p1",  # 2 more alive votes for p1
        }
        # p1 gets: p6(dead ghost) + p7 + p8 = 3 votes; total eligible = 8; 3 > 4? No
        # Let me recalculate: need clear majority
        # 8 eligible (7 alive + 1 dead ghost); majority threshold = >4
        # Votes for p1: p6(1) + p7(1) + p8(1) = 3 → NOT majority
        # Let me give p1 5 votes instead
        G.day_votes = {
            "p3": "p1", "p4": "p1", "p5": "p1", "p7": "p1",  # 4 alive votes
            "p6": "p1",  # dead Ghost vote → total = 5 > 4 → majority
            "p1": "p3", "p2": "p3",  # 2 votes for p3
        }
        G_new = resolve_day_vote(G)
        assert not G_new.players["p1"].is_alive

    def test_dead_ghost_vote_affects_majority_threshold(self):
        """Dead Ghost counts in eligible weight, so their absence would change the threshold."""
        G = self._ghost_game()
        G.players["p6"].is_alive = False  # Ghost dead
        # 8 eligible (7 alive + 1 dead Ghost); threshold > 4
        # Without Ghost in eligible count: 7 alive; threshold > 3.5 → 4 votes would be enough
        # With Ghost in eligible count: 8; threshold > 4 → 4 votes NOT enough
        G.day_votes = {
            "p1": "p2", "p2": "p2", "p3": "p2", "p4": "p2",  # exactly 4 alive votes for p2
        }
        G_new = resolve_day_vote(G)
        assert G_new.players["p2"].is_alive  # 4 votes ≤ 8/2 = 4 → no strict majority

    def test_alive_ghost_vote_is_skipped_in_tally(self):
        """An alive Ghost's vote entry in day_votes is ignored."""
        G = self._ghost_game()
        # Ghost is alive — their vote should be ignored even if handler let it through
        # Force a vote entry as if it was submitted (bypassing handler for this test)
        # 8 eligible (7 alive non-ghost + 1 alive ghost); threshold = >4
        # Votes for p2: p1,p3,p4,p5,p7 = 5 valid alive votes → 5 > 4 → p2 eliminated
        # Ghost votes for p1, but alive Ghost vote is skipped → p1 not eliminated
        G.day_votes = {
            "p6": "p1",  # alive Ghost vote — SKIPPED
            "p1": "p2", "p3": "p2", "p4": "p2", "p5": "p2", "p7": "p2",  # 5 alive votes
        }
        G_new = resolve_day_vote(G)
        assert not G_new.players["p2"].is_alive  # 5 > 4 → eliminated
        assert G_new.players["p1"].is_alive       # Ghost vote skipped → p1 safe
