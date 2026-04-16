"""
Wolf Charge / Villager Defend unit tests.
Covers PRD-015: charge mechanics, defend mechanics, night resolution, and stripper isolation.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from api.intents.errors import IntentError
from api.intents.handlers import handle_grid_defend, handle_wolf_charge_update
from engine.phases.machine import transition_phase
from engine.resolver.night import resolve_night
from engine.setup import setup_game
from engine.state.enums import EliminationCause, Phase, Team
from engine.state.models import MasterGameState, NightActions, PuzzleState
from engine.stripper import player_view
from tests.conftest import _make_player

# ── Shared helpers ────────────────────────────────────────────────────────────

_CM = MagicMock()
_CM.unicast = AsyncMock()

_THRESHOLD = 5000  # must match handlers._CHARGE_THRESHOLD_MS


def _charge_game() -> MasterGameState:
    """
    NIGHT-phase game:
      p1 = wolf (werewolf)
      p2 = villager, actively solving top_left (row=0, col=0)
      p3 = doctor
    """
    G = setup_game("charge-seed", "p1", {})
    G = G.model_copy(deep=True)
    G.phase = Phase.NIGHT
    G.round = 1
    G.host_player_id = "p1"
    G.players = {
        "p1": _make_player("p1", "Wolf",     "werewolf", Team.WEREWOLF),
        "p2": _make_player("p2", "Villager", "villager", Team.VILLAGE),
        "p3": _make_player("p3", "Doctor",   "doctor",   Team.VILLAGE),
    }
    G.players["p2"].grid_node_row = 0
    G.players["p2"].grid_node_col = 0  # top_left quadrant
    G.night_actions = NightActions()
    return G


def _intent(player_id: str, quadrant: str, accumulated_ms: int, is_active: bool) -> dict:
    return {
        "type": "wolf_charge_update",
        "player_id": player_id,
        "quadrant": quadrant,
        "accumulated_ms": accumulated_ms,
        "is_active": is_active,
    }


# ── TestWolfChargeUpdate ──────────────────────────────────────────────────────

class TestWolfChargeUpdate:

    @pytest.mark.asyncio
    async def test_charge_stored_for_wolf(self):
        G = _charge_game()
        G_new = await handle_wolf_charge_update(G, _intent("p1", "top_left", 200, False), None, _CM)
        assert G_new.night_actions.wolf_charges["p1"]["top_left"] == 200

    @pytest.mark.asyncio
    async def test_partial_charge_no_fire(self):
        G = _charge_game()
        G_new = await handle_wolf_charge_update(G, _intent("p1", "top_left", 2000, False), None, _CM)
        assert G_new.night_actions.charge_kill_target_id is None

    @pytest.mark.asyncio
    async def test_full_charge_fires(self):
        G = _charge_game()
        G_new = await handle_wolf_charge_update(G, _intent("p1", "top_left", _THRESHOLD, False), None, _CM)
        assert G_new.night_actions.charge_kill_target_id == "p2"

    @pytest.mark.asyncio
    async def test_full_charge_disrupts_puzzle(self):
        G = _charge_game()
        G.players["p2"].grid_puzzle_state = PuzzleState(
            puzzle_type="math",
            puzzle_data={"expression": "1+1", "answer_options": ["1", "2", "3", "4"]},
            time_limit_seconds=5,
        )
        G_new = await handle_wolf_charge_update(G, _intent("p1", "top_left", _THRESHOLD, False), None, _CM)
        assert G_new.players["p2"].grid_node_row is None
        assert G_new.players["p2"].grid_node_col is None
        # Puzzle state object is kept but deactivated (not nulled out)
        assert G_new.players["p2"].grid_puzzle_state is not None
        assert G_new.players["p2"].grid_puzzle_state.active is False
        assert G_new.players["p2"].grid_puzzle_state.solved is False

    @pytest.mark.asyncio
    async def test_full_charge_resets_wolf_charges(self):
        G = _charge_game()
        await handle_wolf_charge_update(G, _intent("p1", "top_left", _THRESHOLD, False), None, _CM)
        # fire happened in _apply_charge_fire — original G is unchanged; test on returned state
        G_new = await handle_wolf_charge_update(G, _intent("p1", "top_left", _THRESHOLD, False), None, _CM)
        assert G_new.night_actions.wolf_charges["p1"]["top_left"] == 0

    @pytest.mark.asyncio
    async def test_is_active_true_sets_under_attack(self):
        G = _charge_game()
        G_new = await handle_wolf_charge_update(G, _intent("p1", "top_left", 1000, True), None, _CM)
        assert G_new.players["p2"].under_attack is True

    @pytest.mark.asyncio
    async def test_is_active_false_clears_under_attack(self):
        G = _charge_game()
        G.players["p2"].under_attack = True
        G_new = await handle_wolf_charge_update(G, _intent("p1", "top_left", 1000, False), None, _CM)
        assert G_new.players["p2"].under_attack is False

    @pytest.mark.asyncio
    async def test_no_under_attack_if_no_one_in_quadrant(self):
        G = _charge_game()
        G.players["p2"].grid_node_row = None  # p2 not in any quadrant
        G.players["p2"].grid_node_col = None
        G_new = await handle_wolf_charge_update(G, _intent("p1", "top_left", 1000, True), None, _CM)
        assert G_new.players["p2"].under_attack is False

    @pytest.mark.asyncio
    async def test_non_wolf_raises(self):
        G = _charge_game()
        with pytest.raises(IntentError) as exc_info:
            await handle_wolf_charge_update(G, _intent("p2", "top_left", 1000, False), None, _CM)
        assert exc_info.value.code == "NOT_WOLF"

    @pytest.mark.asyncio
    async def test_wrong_phase_raises(self):
        G = _charge_game()
        G.phase = Phase.DAY
        with pytest.raises(IntentError):
            await handle_wolf_charge_update(G, _intent("p1", "top_left", 1000, False), None, _CM)

    @pytest.mark.asyncio
    async def test_invalid_quadrant_raises(self):
        G = _charge_game()
        intent = {"type": "wolf_charge_update", "player_id": "p1",
                  "quadrant": "banana", "accumulated_ms": 1000, "is_active": False}
        with pytest.raises(IntentError) as exc_info:
            await handle_wolf_charge_update(G, intent, None, _CM)
        assert exc_info.value.code == "INVALID_QUADRANT"

    @pytest.mark.asyncio
    async def test_negative_accumulated_raises(self):
        G = _charge_game()
        with pytest.raises(IntentError) as exc_info:
            await handle_wolf_charge_update(G, _intent("p1", "top_left", -1, False), None, _CM)
        assert exc_info.value.code == "INVALID_CHARGE"

    @pytest.mark.asyncio
    async def test_accumulated_capped_at_threshold(self):
        G = _charge_game()
        G_new = await handle_wolf_charge_update(G, _intent("p1", "top_left", 9_999_999, False), None, _CM)
        # Capped, so stored == threshold and fire triggered
        assert G_new.night_actions.wolf_charges["p1"]["top_left"] == 0  # reset after fire
        assert G_new.night_actions.charge_kill_target_id == "p2"

    @pytest.mark.asyncio
    async def test_roleblocked_wolf_raises(self):
        G = _charge_game()
        G.night_actions.roleblocked_player_id = "p1"
        with pytest.raises(IntentError) as exc_info:
            await handle_wolf_charge_update(G, _intent("p1", "top_left", 1000, False), None, _CM)
        assert exc_info.value.code == "ROLEBLOCKED"

    @pytest.mark.asyncio
    async def test_two_wolves_coop_fires(self):
        G = _charge_game()
        G.players["p4"] = _make_player("p4", "Wolf2", "werewolf", Team.WEREWOLF)
        # Wolf1 banks 2500ms
        G = await handle_wolf_charge_update(G, _intent("p1", "top_left", 2500, False), None, _CM)
        assert G.night_actions.charge_kill_target_id is None
        # Wolf2 adds 2500ms — pack total reaches 5000 → fire
        G = await handle_wolf_charge_update(G, _intent("p4", "top_left", 2500, False), None, _CM)
        assert G.night_actions.charge_kill_target_id == "p2"

    @pytest.mark.asyncio
    async def test_second_quadrant_fire_no_extra_kill(self):
        G = _charge_game()
        # Put p3 in bottom_right quadrant
        G.players["p3"].grid_node_row = 4
        G.players["p3"].grid_node_col = 4
        # First fire: top_left → kills p2
        G = await handle_wolf_charge_update(G, _intent("p1", "top_left", _THRESHOLD, False), None, _CM)
        first_target = G.night_actions.charge_kill_target_id
        assert first_target == "p2"
        # Reset wolf's charges manually so second quadrant can fire
        G.night_actions.wolf_charges["p1"] = {}
        # Second fire: bottom_right → should NOT overwrite charge_kill_target_id
        G = await handle_wolf_charge_update(G, _intent("p1", "bottom_right", _THRESHOLD, False), None, _CM)
        assert G.night_actions.charge_kill_target_id == first_target  # still p2

    @pytest.mark.asyncio
    async def test_second_quadrant_fire_still_disrupts(self):
        G = _charge_game()
        G.players["p3"].grid_node_row = 4
        G.players["p3"].grid_node_col = 4  # bottom_right
        # First fire sets charge_kill_target_id to p2
        G = await handle_wolf_charge_update(G, _intent("p1", "top_left", _THRESHOLD, False), None, _CM)
        G.night_actions.wolf_charges["p1"] = {}
        # Second fire on bottom_right — p3 should be disrupted even though kill not recorded
        G = await handle_wolf_charge_update(G, _intent("p1", "bottom_right", _THRESHOLD, False), None, _CM)
        assert G.players["p3"].grid_node_row is None

    @pytest.mark.asyncio
    async def test_fire_with_no_target_in_quadrant(self):
        G = _charge_game()
        # p2 is in top_left; fire on bottom_right where no one is
        G_new = await handle_wolf_charge_update(G, _intent("p1", "bottom_right", _THRESHOLD, False), None, _CM)
        assert G_new.night_actions.charge_kill_target_id is None
        # Charges for bottom_right should still be reset
        assert G_new.night_actions.wolf_charges.get("p1", {}).get("bottom_right", 0) == 0

    @pytest.mark.asyncio
    async def test_state_id_incremented(self):
        G = _charge_game()
        old_id = G.state_id
        G_new = await handle_wolf_charge_update(G, _intent("p1", "top_left", 200, False), None, _CM)
        assert G_new.state_id == old_id + 1


# ── TestGridDefend ────────────────────────────────────────────────────────────

class TestGridDefend:

    def _defend_intent(self, player_id: str) -> dict:
        return {"type": "grid_defend", "player_id": player_id}

    @pytest.mark.asyncio
    async def test_defend_clears_under_attack(self):
        G = _charge_game()
        G.players["p2"].under_attack = True
        G_new = await handle_grid_defend(G, self._defend_intent("p2"), None, _CM)
        assert G_new.players["p2"].under_attack is False

    @pytest.mark.asyncio
    async def test_defend_resets_wolf_charges(self):
        G = _charge_game()
        G.players["p2"].under_attack = True
        G.night_actions.wolf_charges["p1"] = {"top_left": 3000}
        G_new = await handle_grid_defend(G, self._defend_intent("p2"), None, _CM)
        assert G_new.night_actions.wolf_charges["p1"]["top_left"] == 0

    @pytest.mark.asyncio
    async def test_defend_resets_all_wolves_charges(self):
        G = _charge_game()
        G.players["p4"] = _make_player("p4", "Wolf2", "werewolf", Team.WEREWOLF)
        G.players["p2"].under_attack = True
        G.night_actions.wolf_charges["p1"] = {"top_left": 2000}
        G.night_actions.wolf_charges["p4"] = {"top_left": 1500}
        G_new = await handle_grid_defend(G, self._defend_intent("p2"), None, _CM)
        assert G_new.night_actions.wolf_charges["p1"]["top_left"] == 0
        assert G_new.night_actions.wolf_charges["p4"]["top_left"] == 0

    @pytest.mark.asyncio
    async def test_wolf_cannot_defend(self):
        G = _charge_game()
        with pytest.raises(IntentError) as exc_info:
            await handle_grid_defend(G, self._defend_intent("p1"), None, _CM)
        assert exc_info.value.code == "INVALID_ACTION"

    @pytest.mark.asyncio
    async def test_not_under_attack_raises(self):
        G = _charge_game()
        G.players["p2"].under_attack = False
        with pytest.raises(IntentError) as exc_info:
            await handle_grid_defend(G, self._defend_intent("p2"), None, _CM)
        assert exc_info.value.code == "NOT_UNDER_ATTACK"

    @pytest.mark.asyncio
    async def test_defend_with_no_grid_node_clears_flag_only(self):
        G = _charge_game()
        G.players["p2"].under_attack = True
        G.players["p2"].grid_node_row = None  # not on any node
        G.players["p2"].grid_node_col = None
        G.night_actions.wolf_charges["p1"] = {"top_left": 3000}
        G_new = await handle_grid_defend(G, self._defend_intent("p2"), None, _CM)
        assert G_new.players["p2"].under_attack is False
        # No quadrant to clear — wolf charges unchanged
        assert G_new.night_actions.wolf_charges["p1"]["top_left"] == 3000

    @pytest.mark.asyncio
    async def test_defend_only_resets_defending_quadrant(self):
        G = _charge_game()
        G.players["p2"].under_attack = True
        # Wolf charged both top_left (p2's quadrant) and bottom_right
        G.night_actions.wolf_charges["p1"] = {"top_left": 2000, "bottom_right": 3000}
        G_new = await handle_grid_defend(G, self._defend_intent("p2"), None, _CM)
        assert G_new.night_actions.wolf_charges["p1"]["top_left"] == 0
        assert G_new.night_actions.wolf_charges["p1"]["bottom_right"] == 3000  # untouched

    @pytest.mark.asyncio
    async def test_defend_state_id_incremented(self):
        G = _charge_game()
        G.players["p2"].under_attack = True
        old_id = G.state_id
        G_new = await handle_grid_defend(G, self._defend_intent("p2"), None, _CM)
        assert G_new.state_id == old_id + 1


# ── TestChargeKillResolution ──────────────────────────────────────────────────

class TestChargeKillResolution:

    def _resolve_game(self) -> MasterGameState:
        """Game ready for resolve_night with charge_kill_target_id set to p2."""
        G = _charge_game()
        G.night_actions.charge_kill_target_id = "p2"
        return G

    def test_charge_kill_eliminates_target(self):
        G = self._resolve_game()
        G_new = resolve_night(G)
        assert G_new.players["p2"].is_alive is False

    def test_charge_kill_cause_is_grid_charge_kill(self):
        G = self._resolve_game()
        G_new = resolve_night(G)
        causes = [e.cause for e in G_new.elimination_log]
        assert EliminationCause.GRID_CHARGE_KILL in causes

    def test_charge_kill_consumes_target_id(self):
        G = self._resolve_game()
        G_new = resolve_night(G)
        assert G_new.night_actions.charge_kill_target_id is None

    def test_charge_kill_priority_over_wolf_vote(self):
        G = self._resolve_game()
        G.night_actions.wolf_votes = {"p1": "p3"}  # wolf voted for p3
        G_new = resolve_night(G)
        # charge target p2 dies, vote target p3 survives
        assert G_new.players["p2"].is_alive is False
        assert G_new.players["p3"].is_alive is True

    def test_charge_kill_blocked_by_doctor(self):
        G = self._resolve_game()
        G.night_actions.doctor_target_id = "p2"  # doctor protects p2
        G_new = resolve_night(G)
        assert G_new.players["p2"].is_alive is True
        assert G_new.night_actions.charge_kill_target_id is None  # consumed regardless

    def test_charge_kill_blocked_by_wise_shield(self):
        G = self._resolve_game()
        G.players["p2"].role = "wise"
        G.players["p2"].wise_shield_used = False
        G_new = resolve_night(G)
        assert G_new.players["p2"].is_alive is True
        assert G_new.players["p2"].wise_shield_used is True

    def test_charge_kill_blocked_by_bodyguard(self):
        G = self._resolve_game()
        G.players["p4"] = _make_player("p4", "Bodyguard", "bodyguard", Team.VILLAGE)
        G.night_actions.bodyguard_target_id = "p2"
        G_new = resolve_night(G)
        # Target always survives when Bodyguard intervenes
        assert G_new.players["p2"].is_alive is True

    def test_charge_kill_blocked_for_serial_killer(self):
        """SK immunity applies to charge kills too (goes through _apply_wolf_kill)."""
        G = self._resolve_game()
        G.players["p2"].role = "serial_killer"
        G_new = resolve_night(G)
        assert G_new.players["p2"].is_alive is True

    def test_no_charge_kill_if_target_id_none(self):
        G = _charge_game()
        G.night_actions.charge_kill_target_id = None
        G.night_actions.wolf_votes = {}  # no votes either
        G_new = resolve_night(G)
        # All villagers survive
        assert all(p.is_alive for p in G_new.players.values())

    def test_charge_kill_falls_through_to_votes_when_none(self):
        G = _charge_game()
        G.night_actions.charge_kill_target_id = None
        G.night_actions.wolf_votes = {"p1": "p2"}  # majority vote on p2
        G_new = resolve_night(G)
        assert G_new.players["p2"].is_alive is False


# ── TestStripperChargeFields ──────────────────────────────────────────────────

class TestStripperChargeFields:

    def _game_with_charge(self) -> MasterGameState:
        G = _charge_game()
        G.night_actions.wolf_charges["p1"] = {"top_left": 2000}
        G.night_actions.charge_kill_target_id = "p2"
        G.players["p2"].under_attack = True
        return G

    def test_wolf_charges_stripped_from_wolf_view(self):
        G = self._game_with_charge()
        view = player_view(G, "p1")
        assert "wolf_charges" not in view["night_actions"]

    def test_wolf_charges_stripped_from_villager_view(self):
        G = self._game_with_charge()
        view = player_view(G, "p2")
        assert "wolf_charges" not in view["night_actions"]

    def test_wolf_charges_stripped_from_display_view(self):
        G = self._game_with_charge()
        view = player_view(G, None)
        assert "wolf_charges" not in view["night_actions"]

    def test_charge_kill_target_stripped_from_wolf_view(self):
        G = self._game_with_charge()
        view = player_view(G, "p1")
        assert "charge_kill_target_id" not in view["night_actions"]

    def test_charge_kill_target_stripped_from_villager_view(self):
        G = self._game_with_charge()
        view = player_view(G, "p2")
        assert "charge_kill_target_id" not in view["night_actions"]

    def test_charge_kill_target_stripped_from_display_view(self):
        G = self._game_with_charge()
        view = player_view(G, None)
        assert "charge_kill_target_id" not in view["night_actions"]

    def test_under_attack_true_for_own_villager(self):
        G = self._game_with_charge()
        view = player_view(G, "p2")
        assert view["players"]["p2"]["under_attack"] is True

    def test_under_attack_false_for_other_villager(self):
        G = self._game_with_charge()
        view = player_view(G, "p3")
        assert view["players"]["p2"]["under_attack"] is False

    def test_under_attack_always_false_for_wolf_view(self):
        G = self._game_with_charge()
        G.players["p1"].under_attack = True  # should never happen, but test the guard
        view = player_view(G, "p1")
        assert view["players"]["p1"]["under_attack"] is False
