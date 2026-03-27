"""
Night resolver tests — 13-step deterministic engine.
"""

from __future__ import annotations

import pytest

from engine.resolver.night import resolve_night
from engine.state.enums import InvestigationResult, Phase, Team
from engine.state.models import MasterGameState, NightActions, PlayerState
from tests.conftest import _eight_player_game, _five_player_game, _make_player


def _set_wolf_vote(G: MasterGameState, wolf_pid: str, target_pid: str) -> MasterGameState:
    G = G.model_copy(deep=True)
    G.night_actions.wolf_votes[wolf_pid] = target_pid
    return G


# ── Wolf kill ─────────────────────────────────────────────────────────────────

class TestWolfKill:
    def test_wolf_majority_kills_unprotected_target(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.wolf_votes = {"p1": "p3", "p2": "p3"}
        G_new = resolve_night(G)
        assert not G_new.players["p3"].is_alive

    def test_wolf_tie_no_kill(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.wolf_votes = {"p1": "p3", "p2": "p4"}
        G_new = resolve_night(G)
        # Tie = no elimination
        alive_count = sum(1 for p in G_new.players.values() if p.is_alive)
        assert alive_count == 8

    def test_doctor_saves_wolf_target(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.wolf_votes = {"p1": "p3", "p2": "p3"}
        G.night_actions.doctor_target_id = "p3"
        G_new = resolve_night(G)
        assert G_new.players["p3"].is_alive

    def test_consecutive_protect_ban(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        # Doctor protected p3 last round
        G.players["p4"].last_protected_player_id = "p3"
        # But handler prevents consecutive protect — if somehow set, doctor protect on same target
        # should be voided (or handler rejects it). Resolver ignores consecutive target:
        G.night_actions.doctor_target_id = "p3"
        G.night_actions.wolf_votes = {"p1": "p3", "p2": "p3"}
        G_new = resolve_night(G)
        # Doctor consecutive-protect is blocked in handler; in resolver, if it slips through,
        # the resolver checks last_protected. Wolf kill should succeed.
        assert not G_new.players["p3"].is_alive


# ── Seer ──────────────────────────────────────────────────────────────────────

class TestSeerInspect:
    def test_seer_uses_investigation_result_from_registry(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.seer_target_id = "p1"  # wolf
        G_new = resolve_night(G)
        assert G_new.night_actions.seer_result == InvestigationResult.WOLF

    def test_seer_gets_village_for_villager(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.seer_target_id = "p6"  # villager
        G_new = resolve_night(G)
        assert G_new.night_actions.seer_result == InvestigationResult.VILLAGE

    def test_framed_player_appears_as_wolf_to_seer(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p6"].is_framed_tonight = True
        G.night_actions.seer_target_id = "p6"  # villager but framed
        G_new = resolve_night(G)
        assert G_new.night_actions.seer_result == InvestigationResult.WOLF

    def test_roleblock_nullifies_seer(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.roleblocked_player_id = "p3"  # seer blocked
        G.night_actions.seer_target_id = "p1"
        G_new = resolve_night(G)
        # Seer result should be None if blocked
        assert G_new.night_actions.seer_result is None

    def test_roleblock_does_not_affect_cupid(self):
        """Cupid is unblockable (canBeBlocked=false)."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p5"].role = "cupid"
        G.players["p5"].team = Team.VILLAGE
        G.night_actions.roleblocked_player_id = "p5"  # try to block cupid
        G.night_actions.cupid_link = ["p3", "p4"]
        G.round = 1
        G_new = resolve_night(G)
        # Cupid link should still be applied
        assert G_new.lovers_pair == ["p3", "p4"]

    def test_seer_knowledge_accumulated(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.seer_knowledge = {"p6": "village"}
        G.night_actions.seer_target_id = "p1"
        G_new = resolve_night(G)
        assert "p1" in G_new.seer_knowledge
        assert "p6" in G_new.seer_knowledge  # preserved


# ── Framer ────────────────────────────────────────────────────────────────────

class TestFramer:
    def test_framer_frame_sets_is_framed_tonight(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p2"].role = "framer"
        G.night_actions.framer_action = "frame"
        G.night_actions.framer_target_id = "p6"
        G_new = resolve_night(G)
        assert G_new.players["p6"].is_framed_tonight

    def test_framer_hack_archives_sets_false_hint_queued(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p2"].role = "framer"
        G.night_actions.framer_action = "hack_archives"
        G.night_actions.false_hint_payload = {"hint_id": "fake", "is_fabricated": True}
        G_new = resolve_night(G)
        assert G_new.night_actions.false_hint_queued

    def test_framer_hack_tracker_sees_empty_result(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p2"].role = "framer"
        G.night_actions.framer_action = "hack_archives"
        G.night_actions.tracker_target_id = "p1"
        G_new = resolve_night(G)
        # Tracker result should be empty when archives hacked
        assert G_new.night_actions.tracker_result == [] or G_new.night_actions.tracker_result == [""]


# ── Infector ──────────────────────────────────────────────────────────────────

class TestInfector:
    def test_infector_convert_cancels_wolf_kill(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p2"].role = "infector"
        G.night_actions.infector_target_id = "p6"  # convert p6
        G.night_actions.wolf_votes = {"p1": "p6"}  # wolf also targeting p6
        G_new = resolve_night(G)
        # Infect cancels wolf kill — p6 survives and joins werewolf team
        assert G_new.players["p6"].is_alive
        assert G_new.players["p6"].team == Team.WEREWOLF

    def test_infector_converts_target(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p2"].role = "infector"
        G.night_actions.infector_target_id = "p6"
        G_new = resolve_night(G)
        assert G_new.players["p6"].team == Team.WEREWOLF


# ── Arsonist ──────────────────────────────────────────────────────────────────

class TestArsonist:
    def test_arsonist_douse_adds_to_doused(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p2"].role = "arsonist"
        G.players["p2"].team = Team.NEUTRAL
        G.night_actions.arsonist_action = "douse"
        G.night_actions.arsonist_douse_target_id = "p3"
        G_new = resolve_night(G)
        assert "p3" in G_new.players["p2"].doused_player_ids

    def test_arsonist_ignite_kills_doused_players(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p2"].role = "arsonist"
        G.players["p2"].team = Team.NEUTRAL
        G.players["p2"].doused_player_ids = ["p3", "p4"]
        G.night_actions.arsonist_action = "ignite"
        G_new = resolve_night(G)
        assert not G_new.players["p3"].is_alive
        assert not G_new.players["p4"].is_alive


# ── Serial Killer ─────────────────────────────────────────────────────────────

class TestSerialKiller:
    def test_sk_kills_independently(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p2"].role = "serial_killer"
        G.players["p2"].team = Team.NEUTRAL
        G.night_actions.serial_killer_target_id = "p6"
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive

    def test_sk_is_immune_to_wolf_kill(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p2"].role = "serial_killer"
        G.players["p2"].team = Team.NEUTRAL
        G.night_actions.wolf_votes = {"p1": "p2"}
        G.night_actions.serial_killer_target_id = "p6"
        G_new = resolve_night(G)
        assert G_new.players["p2"].is_alive


# ── Lovers death-chain ─────────────────────────────────────────────────────────

class TestLoversDeathChain:
    def test_lover_dies_when_partner_killed(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.lovers_pair = ["p3", "p4"]
        G.players["p3"].lovers_partner_id = "p4"
        G.players["p4"].lovers_partner_id = "p3"
        G.night_actions.wolf_votes = {"p1": "p3", "p2": "p3"}
        G_new = resolve_night(G)
        # p3 killed by wolves; p4 dies in death-chain
        assert not G_new.players["p3"].is_alive
        assert not G_new.players["p4"].is_alive


# ── Tracker ───────────────────────────────────────────────────────────────────

class TestTracker:
    def test_tracker_observes_who_visited_target(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.tracker_target_id = "p3"  # track seer
        G.night_actions.wolf_votes = {"p1": "p3"}  # wolf visits seer
        G_new = resolve_night(G)
        # Tracker should see p1 visited p3
        assert "p1" in G_new.night_actions.tracker_result


# ── Hunter queue ─────────────────────────────────────────────────────────────

class TestHunterQueue:
    def test_hunter_added_to_queue_when_killed(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p5"].role = "hunter"
        G.night_actions.wolf_votes = {"p1": "p5", "p2": "p5"}
        G_new = resolve_night(G)
        assert not G_new.players["p5"].is_alive
        assert G_new.phase == Phase.HUNTER_PENDING
        assert "p5" in G_new.hunter_queue


# ── Win condition checks ──────────────────────────────────────────────────────

class TestWinConditions:
    def test_all_wolves_dead_village_wins(self):
        G, _ = _five_player_game()
        G = G.model_copy(deep=True)
        G.players["p1"].is_alive = False  # only wolf dead
        G_new = resolve_night(G)
        assert G_new.phase == Phase.GAME_OVER
        assert G_new.winner == "village"

    def test_wolves_equal_village_wolves_win(self):
        G, _ = _five_player_game()
        G = G.model_copy(deep=True)
        # p2(seer) and p3(doctor) dead — 1 wolf vs 2 villagers = tie → wolf wins
        G.players["p2"].is_alive = False
        G.players["p3"].is_alive = False
        G.night_actions.wolf_votes = {"p1": "p4"}
        G_new = resolve_night(G)
        assert G_new.phase == Phase.GAME_OVER
        assert G_new.winner == "werewolf"

    def test_step_ordering_roleblock_before_seer(self):
        """Roleblock (step 1) fires before seer inspect (step 6)."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        # Wolf Shaman roleblocks seer directly in step 1
        G.night_actions.roleblock_target_id = "p3"
        # Step 1 should mark p3 as roleblocked, so seer result = None
        G.night_actions.seer_target_id = "p1"
        G_new = resolve_night(G)
        assert G_new.night_actions.seer_result is None
