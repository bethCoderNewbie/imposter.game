"""
Phase machine tests — transitions, timers, auto-advance, round increments.
"""

from __future__ import annotations

import pytest

from engine.phases.machine import (
    compute_actions_required,
    should_auto_advance,
    transition_phase,
)
from engine.state.enums import Phase, Team
from engine.state.models import MasterGameState, NightActions
from tests.conftest import _eight_player_game, _five_player_game


class TestTransitionPhase:
    def test_transition_sets_timer_for_night(self):
        G, _ = _eight_player_game()
        G_new = transition_phase(G, Phase.NIGHT)
        assert G_new.timer_ends_at is not None

    def test_transition_sets_timer_for_day(self):
        G, _ = _eight_player_game()
        G_new = transition_phase(G, Phase.DAY)
        assert G_new.timer_ends_at is not None

    def test_transition_clears_timer_for_game_over(self):
        G, _ = _eight_player_game()
        G_new = transition_phase(G, Phase.GAME_OVER)
        assert G_new.timer_ends_at is None

    def test_transition_clears_timer_for_lobby(self):
        G, _ = _eight_player_game()
        G_new = transition_phase(G, Phase.LOBBY)
        assert G_new.timer_ends_at is None

    def test_night_entry_resets_night_action_submitted(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY
        for p in G.players.values():
            p.night_action_submitted = True
        G_new = transition_phase(G, Phase.NIGHT)
        for p in G_new.players.values():
            assert not p.night_action_submitted

    def test_night_entry_resets_is_framed_tonight(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY
        for p in G.players.values():
            p.is_framed_tonight = True
        G_new = transition_phase(G, Phase.NIGHT)
        for p in G_new.players.values():
            assert not p.is_framed_tonight

    def test_night_entry_resets_is_protected(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY
        G.players["p3"].is_protected = True
        G_new = transition_phase(G, Phase.NIGHT)
        assert not G_new.players["p3"].is_protected

    def test_round_increments_on_night_entry_after_round1(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY
        G.round = 1
        G_new = transition_phase(G, Phase.NIGHT)
        assert G_new.round == 2

    def test_round_does_not_increment_on_first_night(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.ROLE_DEAL
        G.round = 1
        G_new = transition_phase(G, Phase.NIGHT)
        # Round 1 entry from role_deal: round stays 1 (already set)
        assert G_new.round == 1

    def test_night_entry_clears_night_actions(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY
        G.night_actions.wolf_votes = {"p1": "p3"}
        G.night_actions.seer_target_id = "p1"
        G_new = transition_phase(G, Phase.NIGHT)
        assert G_new.night_actions.wolf_votes == {}
        assert G_new.night_actions.seer_target_id is None

    def test_night_entry_clears_day_votes(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        G.day_votes = {"p1": "p3", "p2": "p3"}
        G_new = transition_phase(G, Phase.NIGHT)
        assert G_new.day_votes == {}


class TestShouldAutoAdvance:
    def test_auto_advance_when_all_wakeorder_gt0_submitted(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        # Required: seer, doctor, tracker (wakeOrder > 0)
        G.night_actions.actions_required_count = 3
        G.night_actions.actions_submitted_count = 3
        assert should_auto_advance(G)

    def test_no_auto_advance_when_pending_submissions(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.night_actions.actions_required_count = 3
        G.night_actions.actions_submitted_count = 2
        assert not should_auto_advance(G)

    def test_auto_advance_day_vote_when_all_voted(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        # All 8 alive players voted
        G.day_votes = {
            "p1": "p2", "p2": "p3", "p3": "p4", "p4": "p5",
            "p5": "p6", "p6": "p7", "p7": "p8", "p8": "p1",
        }
        assert should_auto_advance(G)

    def test_no_auto_advance_day_vote_not_all_voted(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        G.day_votes = {"p1": "p2", "p2": "p3"}  # only 2 of 8
        assert not should_auto_advance(G)

    def test_auto_advance_role_deal_all_confirmed(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.ROLE_DEAL
        for p in G.players.values():
            p.role_confirmed = True
        assert should_auto_advance(G)

    def test_no_auto_advance_role_deal_pending_confirms(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.ROLE_DEAL
        for p in G.players.values():
            p.role_confirmed = True
        G.players["p1"].role_confirmed = False
        assert not should_auto_advance(G)


class TestComputeActionsRequired:
    def test_villager_never_blocks_auto_advance(self):
        G, _ = _eight_player_game()
        count = compute_actions_required(G)
        # wakeOrder > 0: wolf(p1), wolf(p2), seer(p3), doctor(p4), tracker(p5) = 5
        # villagers (p6,p7,p8) have wakeOrder=0 and are excluded
        assert count == 5

    def test_cupid_excluded_after_round1(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p5"].role = "cupid"
        G.round = 2  # after round 1
        count = compute_actions_required(G)
        # Cupid excluded after round 1
        # wolf(p1), wolf(p2), seer(p3), doctor(p4) = 4
        assert count == 4

    def test_cupid_included_in_round1(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p5"].role = "cupid"
        G.round = 1
        count = compute_actions_required(G)
        # wolf(p1), wolf(p2), seer(p3), doctor(p4), cupid(p5) = 5
        assert count == 5

    def test_dead_players_excluded(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p3"].is_alive = False  # seer dead
        count = compute_actions_required(G)
        # wolf(p1), wolf(p2), doctor(p4), tracker(p5) = 4
        assert count == 4
