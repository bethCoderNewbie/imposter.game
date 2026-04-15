"""
Night resolver tests — 13-step deterministic engine.
"""

from __future__ import annotations

import pytest

from engine.resolver.night import resolve_night
from engine.state.enums import EliminationCause, InvestigationResult, Phase, Team
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

    def test_roleblock_clears_consecutive_protect_memory(self):
        """Roleblocked doctor should have last_protected_player_id cleared so the
        following night they are not falsely locked out of the same target."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        # Doctor (p4) protected p3 on night 1
        G.players["p4"].last_protected_player_id = "p3"
        # Night 2: doctor is roleblocked by wolf shaman
        G.night_actions.roleblocked_player_id = "p4"
        G.night_actions.doctor_target_id = "p3"
        G.night_actions.wolf_votes = {"p1": "p3", "p2": "p3"}
        G_new = resolve_night(G)
        # Protection did not apply (roleblocked) → wolf kill succeeds
        assert not G_new.players["p3"].is_alive
        # But last_protected_player_id is cleared so night 3 is unrestricted
        assert G_new.players["p4"].last_protected_player_id is None

    def test_after_roleblock_doctor_can_protect_previous_target(self):
        """After a roleblock night, doctor can protect the same player they last
        protected, because the consecutive-protect memory was cleared."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        # Simulate: doctor was roleblocked last night → last_protected cleared
        G.players["p4"].last_protected_player_id = None
        # Night 3: doctor protects p3, wolves try to kill p3
        G.night_actions.doctor_target_id = "p3"
        G.night_actions.wolf_votes = {"p1": "p3", "p2": "p3"}
        G_new = resolve_night(G)
        # Protection applied — p3 survives
        assert G_new.players["p3"].is_alive


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



# ── Witch ──────────────────────────────────────────────────────────────────────

class TestWitch:
    def _witch_game(self):
        """Eight-player game with p6 as the Witch."""
        G, pids = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p6"].role = "witch"
        G.players["p6"].team = Team.VILLAGE
        return G

    def test_witch_heal_saves_wolf_target(self):
        G = self._witch_game()
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.witch_action = "heal"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert G_new.players["p7"].is_alive

    def test_witch_kill_eliminates_target(self):
        G = self._witch_game()
        G.night_actions.witch_action = "kill"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert not G_new.players["p7"].is_alive
        causes = [e.cause for e in G_new.elimination_log]
        assert EliminationCause.WITCH_KILL in causes

    def test_witch_kill_bypasses_protection(self):
        G = self._witch_game()
        G.night_actions.doctor_target_id = "p7"   # doctor protects p7
        G.night_actions.witch_action = "kill"
        G.night_actions.witch_target_id = "p7"    # witch kills p7 anyway
        G_new = resolve_night(G)
        # Witch kill resolved before Doctor (step 4b < step 5) — p7 dead when
        # Doctor runs, so protection is set but irrelevant; kill already logged.
        assert not G_new.players["p7"].is_alive

    def test_witch_heal_stacks_with_doctor_no_crash(self):
        G = self._witch_game()
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.doctor_target_id = "p7"
        G.night_actions.witch_action = "heal"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert G_new.players["p7"].is_alive  # saved by at least one of them

    def test_witch_roleblock_prevents_action(self):
        G = self._witch_game()
        G.night_actions.roleblocked_player_id = "p6"
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.witch_action = "heal"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert not G_new.players["p7"].is_alive  # wolf kill succeeds; witch was blocked

    def test_witch_marks_heal_potion_used(self):
        G = self._witch_game()
        G.night_actions.witch_action = "heal"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert G_new.players["p6"].witch_heal_used is True
        assert G_new.players["p6"].witch_kill_used is False

    def test_witch_marks_kill_potion_used(self):
        G = self._witch_game()
        G.night_actions.witch_action = "kill"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert G_new.players["p6"].witch_kill_used is True
        assert G_new.players["p6"].witch_heal_used is False


# ── Lunatic ────────────────────────────────────────────────────────────────────

class TestLunatic:
    def _lunatic_game(self):
        """Eight-player game with p6 as Lunatic, p1+p2 as wolves."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p6"].role = "lunatic"
        G.players["p6"].team = "neutral"
        return G

    def test_redirect_lunatic_dies_in_place_of_target(self):
        G = self._lunatic_game()
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.lunatic_redirect = True
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive            # lunatic died
        assert G_new.players["p7"].is_alive                # original wolf target saved
        causes = [e.cause for e in G_new.elimination_log]
        assert EliminationCause.LUNATIC_SACRIFICE in causes

    def test_redirect_curses_lead_wolf(self):
        G = self._lunatic_game()
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.lunatic_redirect = True
        G_new = resolve_night(G)
        # First wolf who voted for p7 is cursed
        assert G_new.lunatic_cursed_wolf_id in ("p1", "p2")

    def test_cursed_wolf_dies_next_night(self):
        G = self._lunatic_game()
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.lunatic_redirect = True
        G_after_night1 = resolve_night(G)
        cursed = G_after_night1.lunatic_cursed_wolf_id
        assert cursed is not None

        # Simulate night 2 — no other actions
        G2 = G_after_night1.model_copy(deep=True)
        G2.round = 2
        from engine.state.models import NightActions
        G2.night_actions = NightActions(actions_required_count=0)
        G2_new = resolve_night(G2)
        assert not G2_new.players[cursed].is_alive
        causes = [e.cause for e in G2_new.elimination_log]
        assert EliminationCause.LUNATIC_CURSE in causes

    def test_redirect_no_op_when_wolves_have_no_majority(self):
        G = self._lunatic_game()
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p8"}  # tie
        G.night_actions.lunatic_redirect = True
        G_new = resolve_night(G)
        assert G_new.players["p6"].is_alive   # lunatic lives — no kill to redirect
        assert G_new.lunatic_cursed_wolf_id is None

    def test_redirect_blocked_by_roleblock(self):
        G = self._lunatic_game()
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.lunatic_redirect = True
        G.night_actions.roleblocked_player_id = "p6"  # lunatic is roleblocked
        G_new = resolve_night(G)
        assert G_new.players["p6"].is_alive   # redirect failed
        assert not G_new.players["p7"].is_alive  # wolf kill proceeds normally

    def test_redirect_marks_redirect_used(self):
        G = self._lunatic_game()
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.lunatic_redirect = True
        G_new = resolve_night(G)
        assert G_new.players["p6"].lunatic_redirect_used is True


# ── Wise ───────────────────────────────────────────────────────────────────────

class TestWise:
    def _wise_game(self):
        """Eight-player game with p6 as Wise."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p6"].role = "wise"
        return G

    def test_wise_deflects_first_wolf_kill(self):
        G = self._wise_game()
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        assert G_new.players["p6"].is_alive
        assert G_new.players["p6"].wise_shield_used is True

    def test_wise_dies_on_second_wolf_kill(self):
        G = self._wise_game()
        G.players["p6"].wise_shield_used = True  # shield already spent
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive

    def test_wise_shield_disabled_when_village_cursed(self):
        G = self._wise_game()
        G.village_powers_cursed = True
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive  # shield doesn't fire

    def test_wise_shield_does_not_block_serial_killer(self):
        """Wise shield only deflects wolf kills — SK bypasses it."""
        G = self._wise_game()
        G.players["p5"].role = "serial_killer"
        G.players["p5"].team = "neutral"
        G.night_actions.serial_killer_target_id = "p6"
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive

    def test_village_cursed_disables_doctor(self):
        G = self._wise_game()
        G.village_powers_cursed = True
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.doctor_target_id = "p7"
        G_new = resolve_night(G)
        assert not G_new.players["p7"].is_alive  # doctor blocked by curse

    def test_village_cursed_disables_seer(self):
        G = self._wise_game()
        G.village_powers_cursed = True
        G.night_actions.seer_target_id = "p1"
        G_new = resolve_night(G)
        assert G_new.night_actions.seer_result is None  # seer blocked by curse

    def test_village_cursed_disables_tracker(self):
        G = self._wise_game()
        G.village_powers_cursed = True
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.tracker_target_id = "p7"
        G_new = resolve_night(G)
        assert G_new.night_actions.tracker_result == []  # tracker blocked by curse


# ── Bodyguard ──────────────────────────────────────────────────────────────────

class TestBodyguard:
    def _bg_game(self, seed: str = "test-bg-0"):
        """Eight-player game with p6 as Bodyguard. p5 becomes a plain villager."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p6"].role = "bodyguard"
        G.players["p6"].team = "village"
        G.seed = seed
        G.round = 1
        return G

    def test_guarded_player_always_survives(self):
        """Protected target never dies — regardless of 50/50 outcome."""
        G = self._bg_game("test-bg-0")
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.bodyguard_target_id = "p7"
        G_new = resolve_night(G)
        assert G_new.players["p7"].is_alive

    def test_attacker_dies_outcome(self):
        # seed 'test-bg-0' → random < 0.5 → attacker dies
        G = self._bg_game("test-bg-0")
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.bodyguard_target_id = "p7"
        G_new = resolve_night(G)
        # First wolf who voted for p7 = p1 → p1 dies
        assert not G_new.players["p1"].is_alive
        assert G_new.players["p6"].is_alive   # bodyguard lives
        causes = [e.cause for e in G_new.elimination_log]
        assert EliminationCause.BODYGUARD_KILL in causes

    def test_bodyguard_sacrifice_outcome(self):
        # seed 'test-bg-2' → random >= 0.5 → bodyguard dies
        G = self._bg_game("test-bg-2")
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.bodyguard_target_id = "p7"
        G_new = resolve_night(G)
        assert G_new.players["p7"].is_alive   # guarded player lives
        assert not G_new.players["p6"].is_alive  # bodyguard died
        causes = [e.cause for e in G_new.elimination_log]
        assert EliminationCause.BODYGUARD_SACRIFICE in causes

    def test_doctor_saves_bodyguard_from_sacrifice(self):
        # seed 'test-bg-2' → bodyguard sacrifice outcome, BUT doctor protects bodyguard
        G = self._bg_game("test-bg-2")
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.bodyguard_target_id = "p7"
        G.night_actions.doctor_target_id = "p6"  # doctor protects the bodyguard
        G_new = resolve_night(G)
        assert G_new.players["p7"].is_alive   # guarded player lives
        assert G_new.players["p6"].is_alive   # bodyguard also saved by doctor

    def test_roleblock_disables_bodyguard(self):
        G = self._bg_game("test-bg-0")
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.bodyguard_target_id = "p7"
        G.night_actions.roleblocked_player_id = "p6"  # bodyguard blocked
        G_new = resolve_night(G)
        assert not G_new.players["p7"].is_alive  # wolf kill lands normally

    def test_bodyguard_not_triggered_when_wolves_target_unguarded(self):
        G = self._bg_game("test-bg-0")
        G.night_actions.wolf_votes = {"p1": "p8", "p2": "p8"}  # wolves target p8
        G.night_actions.bodyguard_target_id = "p7"              # bodyguard guards p7
        G_new = resolve_night(G)
        assert not G_new.players["p8"].is_alive  # p8 dies normally
        assert G_new.players["p7"].is_alive       # guarded but not attacked

    def test_village_cursed_disables_bodyguard(self):
        G = self._bg_game("test-bg-0")
        G.village_powers_cursed = True
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.bodyguard_target_id = "p7"
        G_new = resolve_night(G)
        assert not G_new.players["p7"].is_alive  # bodyguard blocked by curse


# ── Cupid / Lovers (expanded) ──────────────────────────────────────────────────

class TestCupidLovers:
    """Comprehensive coverage of the Cupid link and all lovers death-chain scenarios."""

    def _linked_game(self, lover_a: str = "p6", lover_b: str = "p7"):
        """Eight-player game with a pre-established lovers pair."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.lovers_pair = [lover_a, lover_b]
        G.players[lover_a].lovers_partner_id = lover_b
        G.players[lover_b].lovers_partner_id = lover_a
        return G

    # ── death-chain basics ────────────────────────────────────────────────────

    def test_broken_heart_cause_logged(self):
        """Elimination event for the surviving partner has cause BROKEN_HEART."""
        G = self._linked_game("p6", "p7")
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        causes = [e.cause for e in G_new.elimination_log]
        assert EliminationCause.BROKEN_HEART in causes

    def test_chain_does_not_fire_when_both_die_simultaneously(self):
        """If both lovers die in the same night (wolf + SK), no broken_heart event."""
        G = self._linked_game("p6", "p7")
        G.players["p5"].role = "serial_killer"
        G.players["p5"].team = Team.NEUTRAL
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}   # wolves kill p6
        G.night_actions.serial_killer_target_id = "p7"            # SK kills p7
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive
        assert not G_new.players["p7"].is_alive
        causes = [e.cause for e in G_new.elimination_log]
        assert EliminationCause.BROKEN_HEART not in causes

    def test_chain_does_not_fire_when_both_already_dead(self):
        """No broken_heart if the surviving partner is also already dead."""
        G = self._linked_game("p6", "p7")
        G.players["p7"].is_alive = False  # p7 already dead before this night
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        causes = [e.cause for e in G_new.elimination_log]
        assert EliminationCause.BROKEN_HEART not in causes

    def test_death_chain_only_kills_direct_partner(self):
        """Only the linked partner dies — unrelated players are unaffected."""
        G = self._linked_game("p6", "p7")
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        assert G_new.players["p3"].is_alive  # seer — unlinked, survives
        assert G_new.players["p8"].is_alive  # villager — survives

    def test_lover_survives_if_wolf_target_is_protected(self):
        """Doctor saves the wolf target — neither lover dies."""
        G = self._linked_game("p6", "p7")
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G.night_actions.doctor_target_id = "p6"  # doctor protects p6
        G_new = resolve_night(G)
        assert G_new.players["p6"].is_alive   # doctor saved p6
        assert G_new.players["p7"].is_alive   # no chain triggered

    # ── Hunter partner queued after broken heart ──────────────────────────────

    def test_lover_partner_hunter_queued_after_night_death(self):
        """When Lover A dies at night, Lover B (Hunter) is queued for revenge."""
        G = self._linked_game("p6", "p7")
        G.players["p7"].role = "hunter"  # p7 is Hunter and Lover B
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive   # wolf kill
        assert not G_new.players["p7"].is_alive   # broken heart
        assert "p7" in G_new.hunter_queue          # Hunter queued for revenge

    # ── Wolf-team lovers ──────────────────────────────────────────────────────

    def test_wolf_lover_dies_triggers_partner(self):
        """A wolf in a lovers pair dying causes their partner to die."""
        G = self._linked_game("p1", "p7")  # p1 is wolf, p7 is villager
        G.players["p5"].role = "serial_killer"
        G.players["p5"].team = Team.NEUTRAL
        G.night_actions.serial_killer_target_id = "p1"  # SK kills wolf p1
        G_new = resolve_night(G)
        assert not G_new.players["p1"].is_alive   # SK kill
        assert not G_new.players["p7"].is_alive   # broken heart

    def test_two_wolves_linked_one_dies_other_follows(self):
        """Cupid can link two wolves; if one dies the other dies from broken heart."""
        G = self._linked_game("p1", "p2")  # both wolves
        G.players["p5"].role = "serial_killer"
        G.players["p5"].team = Team.NEUTRAL
        G.night_actions.serial_killer_target_id = "p1"  # SK kills wolf p1
        G_new = resolve_night(G)
        assert not G_new.players["p1"].is_alive
        assert not G_new.players["p2"].is_alive  # broken heart kills the other wolf

    # ── Cupid link mechanics ──────────────────────────────────────────────────

    def test_cupid_link_round1_establishes_lovers_pair(self):
        """Cupid's round-1 link sets both lovers_pair and partners on both players."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p5"].role = "cupid"
        G.round = 1
        G.night_actions.cupid_link = ["p6", "p7"]
        G_new = resolve_night(G)
        assert G_new.lovers_pair == ["p6", "p7"]
        assert G_new.players["p6"].lovers_partner_id == "p7"
        assert G_new.players["p7"].lovers_partner_id == "p6"

    def test_cupid_link_round2_is_noop(self):
        """Cupid submitting a link on round 2 has no effect on lovers_pair."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p5"].role = "cupid"
        G.round = 2
        G.night_actions.cupid_link = ["p6", "p7"]
        G_new = resolve_night(G)
        assert G_new.lovers_pair is None   # round > 1: link silently ignored

    def test_cupid_unblockable_by_wolf_shaman(self):
        """Roleblocking Cupid does not prevent the lovers link from forming."""
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p5"].role = "cupid"
        G.round = 1
        G.night_actions.roleblocked_player_id = "p5"   # Cupid is 'blocked'
        G.night_actions.cupid_link = ["p6", "p7"]
        G_new = resolve_night(G)
        # Cupid is canBeBlocked=false — link must fire despite roleblock
        assert G_new.lovers_pair == ["p6", "p7"]


# ── Doctor (extended) ──────────────────────────────────────────────────────────

class TestDoctorExtended:
    def _doctor_game(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        return G  # p4 = doctor in conftest

    def test_doctor_can_protect_themselves(self):
        G = self._doctor_game()
        G.night_actions.wolf_votes = {"p1": "p4", "p2": "p4"}
        G.night_actions.doctor_target_id = "p4"
        G_new = resolve_night(G)
        assert G_new.players["p4"].is_alive

    def test_doctor_protection_does_not_stop_serial_killer(self):
        G = self._doctor_game()
        G.players["p5"].role = "serial_killer"
        G.players["p5"].team = Team.NEUTRAL
        G.night_actions.doctor_target_id = "p6"
        G.night_actions.serial_killer_target_id = "p6"
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive

    def test_doctor_protection_does_not_stop_arsonist_ignite(self):
        G = self._doctor_game()
        G.players["p5"].role = "arsonist"
        G.players["p5"].team = Team.NEUTRAL
        G.players["p5"].doused_player_ids = ["p6"]
        G.night_actions.doctor_target_id = "p6"
        G.night_actions.arsonist_action = "ignite"
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive

    def test_doctor_non_consecutive_can_reprotect_same_target(self):
        G = self._doctor_game()
        G.players["p4"].last_protected_player_id = "p7"
        G.night_actions.doctor_target_id = "p6"
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        assert G_new.players["p6"].is_alive

    def test_doctor_consecutive_protect_rejected_by_resolver(self):
        G = self._doctor_game()
        G.players["p4"].last_protected_player_id = "p6"
        G.night_actions.doctor_target_id = "p6"
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive

    def test_doctor_can_set_protection_on_wolf(self):
        G = self._doctor_game()
        G.night_actions.doctor_target_id = "p1"
        G_new = resolve_night(G)
        assert G_new.players["p1"].is_alive
        assert G_new.players["p1"].is_protected

    def test_doctor_protection_step_runs_before_wolf_kill(self):
        G = self._doctor_game()
        G.night_actions.doctor_target_id = "p6"
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        assert G_new.players["p6"].is_alive


# ── Tracker (extended) ────────────────────────────────────────────────────────

class TestTrackerExtended:
    def _tracker_game(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        return G  # p5 = tracker in conftest

    def test_tracker_sees_seer_visit(self):
        G = self._tracker_game()
        G.night_actions.tracker_target_id = "p1"
        G.night_actions.seer_target_id = "p1"
        G_new = resolve_night(G)
        assert "p3" in G_new.night_actions.tracker_result  # p3 = seer

    def test_tracker_sees_doctor_visit(self):
        G = self._tracker_game()
        G.night_actions.tracker_target_id = "p6"
        G.night_actions.doctor_target_id = "p6"
        G_new = resolve_night(G)
        assert "p4" in G_new.night_actions.tracker_result  # p4 = doctor

    def test_tracker_sees_sk_visit(self):
        G = self._tracker_game()
        G.players["p6"].role = "serial_killer"
        G.players["p6"].team = Team.NEUTRAL
        G.night_actions.tracker_target_id = "p7"
        G.night_actions.serial_killer_target_id = "p7"
        G_new = resolve_night(G)
        assert "p6" in G_new.night_actions.tracker_result

    def test_tracker_sees_arsonist_douse(self):
        G = self._tracker_game()
        G.players["p6"].role = "arsonist"
        G.players["p6"].team = Team.NEUTRAL
        G.night_actions.tracker_target_id = "p7"
        G.night_actions.arsonist_action = "douse"
        G.night_actions.arsonist_douse_target_id = "p7"
        G_new = resolve_night(G)
        assert "p6" in G_new.night_actions.tracker_result

    def test_tracker_sees_witch_visit(self):
        G = self._tracker_game()
        G.players["p6"].role = "witch"
        G.players["p6"].team = Team.VILLAGE
        G.night_actions.tracker_target_id = "p7"
        G.night_actions.witch_action = "heal"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert "p6" in G_new.night_actions.tracker_result

    def test_tracker_does_not_see_bodyguard(self):
        G = self._tracker_game()
        G.players["p6"].role = "bodyguard"
        G.players["p6"].team = Team.VILLAGE
        G.night_actions.tracker_target_id = "p7"
        G.night_actions.bodyguard_target_id = "p7"
        G_new = resolve_night(G)
        assert "p6" not in G_new.night_actions.tracker_result

    def test_tracker_empty_when_nobody_visits(self):
        G = self._tracker_game()
        G.night_actions.tracker_target_id = "p8"
        G_new = resolve_night(G)
        assert G_new.night_actions.tracker_result == []

    def test_tracker_roleblocked_result_is_empty_list(self):
        G = self._tracker_game()
        G.night_actions.roleblocked_player_id = "p5"
        G.night_actions.tracker_target_id = "p1"
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        assert G_new.night_actions.tracker_result == []
        assert G_new.tracker_knowledge.get(str(G.round), []) == []

    def test_tracker_result_deduplicates_wolf_votes(self):
        G = self._tracker_game()
        G.night_actions.tracker_target_id = "p6"
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G_new = resolve_night(G)
        result = G_new.night_actions.tracker_result
        assert result.count("p1") == 1
        assert result.count("p2") == 1

    def test_tracker_knowledge_accumulated_by_round(self):
        G = self._tracker_game()
        G.round = 2
        G.night_actions.tracker_target_id = "p1"
        G.night_actions.seer_target_id = "p1"
        G_new = resolve_night(G)
        assert "2" in G_new.tracker_knowledge
        assert "p3" in G_new.tracker_knowledge["2"]


# ── Witch (extended) ────────────────────────────────────────────────────────��─

class TestWitchExtended:
    def _witch_game(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p6"].role = "witch"
        G.players["p6"].team = Team.VILLAGE
        return G

    def test_witch_kill_triggers_lovers_death_chain(self):
        G = self._witch_game()
        G.lovers_pair = ["p7", "p8"]
        G.players["p7"].lovers_partner_id = "p8"
        G.players["p8"].lovers_partner_id = "p7"
        G.night_actions.witch_action = "kill"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert not G_new.players["p7"].is_alive
        assert not G_new.players["p8"].is_alive
        causes = [e.cause for e in G_new.elimination_log]
        assert EliminationCause.BROKEN_HEART in causes

    def test_witch_kill_triggers_hunter_queue(self):
        from engine.state.enums import Phase
        G = self._witch_game()
        G.players["p7"].role = "hunter"
        G.night_actions.witch_action = "kill"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert not G_new.players["p7"].is_alive
        assert "p7" in G_new.hunter_queue
        assert G_new.phase == Phase.HUNTER_PENDING

    def test_witch_heal_protects_against_wolf_kill(self):
        G = self._witch_game()
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.witch_action = "heal"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert G_new.players["p7"].is_alive

    def test_witch_kill_bypasses_bodyguard_protection(self):
        G = self._witch_game()
        G.players["p7"].role = "bodyguard"
        G.players["p7"].team = Team.VILLAGE
        G.night_actions.bodyguard_target_id = "p8"
        G.night_actions.witch_action = "kill"
        G.night_actions.witch_target_id = "p8"
        G_new = resolve_night(G)
        assert not G_new.players["p8"].is_alive

    def test_witch_can_heal_themselves(self):
        G = self._witch_game()
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}
        G.night_actions.witch_action = "heal"
        G.night_actions.witch_target_id = "p6"
        G_new = resolve_night(G)
        assert G_new.players["p6"].is_alive

    def test_witch_kill_bypasses_wise_shield(self):
        G = self._witch_game()
        G.players["p7"].role = "wise"
        G.players["p7"].team = Team.VILLAGE
        G.night_actions.witch_action = "kill"
        G.night_actions.witch_target_id = "p7"
        G_new = resolve_night(G)
        assert not G_new.players["p7"].is_alive
        assert not G_new.players["p7"].wise_shield_used

    def test_witch_heal_and_doctor_both_protect_same_player(self):
        G = self._witch_game()
        G.night_actions.wolf_votes = {"p1": "p7", "p2": "p7"}
        G.night_actions.witch_action = "heal"
        G.night_actions.witch_target_id = "p7"
        G.night_actions.doctor_target_id = "p7"
        G_new = resolve_night(G)
        assert G_new.players["p7"].is_alive

    def test_witch_heal_used_flag_persists_across_rounds(self):
        # Resolver does not gate on witch_heal_used (that is the handler job).
        # This confirms the flag survives deep-copy into the next round.
        G = self._witch_game()
        G.night_actions.witch_action = "heal"
        G.night_actions.witch_target_id = "p7"
        G_after = resolve_night(G)
        assert G_after.players["p6"].witch_heal_used is True
        G2 = G_after.model_copy(deep=True)
        G2.round = 2
        from engine.state.models import NightActions
        G2.night_actions = NightActions(actions_required_count=0)
        G2_new = resolve_night(G2)
        assert G2_new.players["p6"].witch_heal_used is True  # persists; handler enforces POTION_SPENT

    def test_witch_skip_does_not_consume_potions(self):
        G = self._witch_game()
        G.night_actions.witch_action = None
        G.night_actions.witch_target_id = None
        G_new = resolve_night(G)
        assert not G_new.players["p6"].witch_heal_used
        assert not G_new.players["p6"].witch_kill_used


# ── Alpha Wolf ────────────────────────────────────────────────────────────────

class TestAlphaWolf:
    def _alpha_wolf_game(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p1"].role = "alpha_wolf"
        return G

    def test_alpha_wolf_seer_sees_village(self):
        G = self._alpha_wolf_game()
        G.night_actions.seer_target_id = "p1"
        G_new = resolve_night(G)
        assert G_new.night_actions.seer_result == InvestigationResult.VILLAGE

    def test_alpha_wolf_framed_seer_sees_wolf(self):
        G = self._alpha_wolf_game()
        G.players["p1"].is_framed_tonight = True
        G.night_actions.seer_target_id = "p1"
        G_new = resolve_night(G)
        assert G_new.night_actions.seer_result == InvestigationResult.WOLF

    def test_alpha_wolf_vote_counts_in_kill(self):
        G = self._alpha_wolf_game()
        G.night_actions.wolf_votes = {"p1": "p6"}
        G_new = resolve_night(G)
        assert not G_new.players["p6"].is_alive

    def test_alpha_wolf_seer_knowledge_stores_village(self):
        G = self._alpha_wolf_game()
        G.night_actions.seer_target_id = "p1"
        G_new = resolve_night(G)
        assert G_new.seer_knowledge.get("p1") == "village"

    def test_alpha_wolf_can_be_killed_by_sk(self):
        G = self._alpha_wolf_game()
        G.players["p6"].role = "serial_killer"
        G.players["p6"].team = Team.NEUTRAL
        G.night_actions.serial_killer_target_id = "p1"
        G_new = resolve_night(G)
        assert not G_new.players["p1"].is_alive

    def test_regular_wolf_seer_sees_wolf(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.seer_target_id = "p1"
        G_new = resolve_night(G)
        assert G_new.night_actions.seer_result == InvestigationResult.WOLF
