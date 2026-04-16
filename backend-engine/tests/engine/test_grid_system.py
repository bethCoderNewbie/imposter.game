"""
Grid system tests: layout generation, hint tiers, stripper isolation, intent handlers.
Covers PRD-013 and RFC-002 security invariants.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from engine.hint_bank import generate_grid_hint, generate_hint
from engine.phases.machine import transition_phase
from engine.puzzle_bank import generate_grid_layout, generate_grid_puzzle, node_to_quadrant
from engine.setup import setup_game
from engine.state.enums import Phase, Team
from engine.state.models import MasterGameState, NightActions, PlayerState
from engine.stripper import player_view
from tests.conftest import _make_player


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_game(round_num: int = 2) -> MasterGameState:
    """6-player game: 2 wolves + 4 villagers. Night phase, grid initialized."""
    G = setup_game("grid-seed", "p1", {})
    G = G.model_copy(deep=True)
    G.phase = Phase.NIGHT
    G.round = round_num
    G.players = {
        "p1": _make_player("p1", "Wolf1",    "werewolf", Team.WEREWOLF),
        "p2": _make_player("p2", "Wolf2",    "werewolf", Team.WEREWOLF),
        "p3": _make_player("p3", "Alice",    "villager", Team.VILLAGE),
        "p4": _make_player("p4", "Bob",      "villager", Team.VILLAGE),
        "p5": _make_player("p5", "Carol",    "seer",     Team.VILLAGE),
        "p6": _make_player("p6", "Dave",     "villager", Team.VILLAGE),
    }
    G.night_actions = NightActions(actions_submitted_count=0, actions_required_count=3)
    G.night_actions.grid_layout = generate_grid_layout(G.seed, G.round)
    G.night_actions.grid_activity = []
    G.night_actions.sonar_pings_used = 0
    G.night_actions.sonar_ping_results = []
    G.night_actions.night_action_change_count = {}
    return G


# ── Grid layout generation ────────────────────────────────────────────────────

class TestGridLayout:
    def test_layout_is_5x5(self):
        layout = generate_grid_layout("seed", 1)
        assert len(layout) == 5
        for row in layout:
            assert len(row) == 5

    def test_tier_distribution(self):
        layout = generate_grid_layout("seed", 1)
        flat = [cell for row in layout for cell in row]
        assert flat.count(1) == 18, f"Expected 18 green nodes, got {flat.count(1)}"
        assert flat.count(2) == 6,  f"Expected 6 yellow nodes, got {flat.count(2)}"
        assert flat.count(3) == 1,  f"Expected 1 red node, got {flat.count(3)}"

    def test_deterministic(self):
        layout_a = generate_grid_layout("test-seed", 2)
        layout_b = generate_grid_layout("test-seed", 2)
        assert layout_a == layout_b

    def test_different_rounds_produce_different_layouts(self):
        layout_r1 = generate_grid_layout("test-seed", 1)
        layout_r2 = generate_grid_layout("test-seed", 2)
        assert layout_r1 != layout_r2

    def test_all_tiers_are_valid(self):
        for seed in ("alpha", "beta", "gamma"):
            layout = generate_grid_layout(seed, 1)
            for row in layout:
                for cell in row:
                    assert cell in (1, 2, 3), f"Invalid tier: {cell}"


# ── node_to_quadrant ──────────────────────────────────────────────────────────

class TestNodeToQuadrant:
    def test_top_left(self):
        assert node_to_quadrant(0, 0) == "top_left"
        assert node_to_quadrant(1, 1) == "top_left"

    def test_top_right(self):
        assert node_to_quadrant(0, 2) == "top_right"
        assert node_to_quadrant(1, 4) == "top_right"

    def test_bottom_left(self):
        assert node_to_quadrant(2, 0) == "bottom_left"
        assert node_to_quadrant(4, 1) == "bottom_left"

    def test_bottom_right(self):
        assert node_to_quadrant(2, 2) == "bottom_right"
        assert node_to_quadrant(4, 4) == "bottom_right"


# ── Grid puzzle generation ────────────────────────────────────────────────────

class TestGridPuzzle:
    def test_tier1_time_limit(self):
        import random
        rng = random.Random("test")
        puzzle = generate_grid_puzzle(1, rng)
        assert puzzle.time_limit_seconds == 5

    def test_tier2_time_limit(self):
        import random
        rng = random.Random("test")
        puzzle = generate_grid_puzzle(2, rng)
        assert puzzle.time_limit_seconds == 10

    def test_tier3_time_limit(self):
        import random
        rng = random.Random("test")
        puzzle = generate_grid_puzzle(3, rng)
        assert puzzle.time_limit_seconds == 20

    def test_correct_index_present(self):
        """correct_index must be present server-side for validation."""
        import random
        for tier in (1, 2, 3):
            rng = random.Random(f"test-{tier}")
            puzzle = generate_grid_puzzle(tier, rng)
            if puzzle.puzzle_type != "sequence":
                assert "correct_index" in puzzle.puzzle_data, \
                    f"Tier {tier} puzzle missing correct_index"


# ── Grid hint generation ──────────────────────────────────────────────────────

class TestGridHintTier1:
    def test_tier1_categories_include_wolf_count(self):
        G = _base_game(round_num=3)
        hints = [generate_grid_hint(G, "p3", 1, r, c) for r in range(3) for c in range(5)]
        categories = {h["category"] for h in hints}
        assert "wolf_count" in categories

    def test_tier1_vague_in_early_rounds(self):
        G = _base_game(round_num=1)
        hints = [generate_grid_hint(G, "p3", 1, r, c) for r in range(5) for c in range(5)]
        wolf_hints = [h for h in hints if h["category"] == "wolf_count"]
        for h in wolf_hints:
            assert "between" in h["text"], f"Expected vague text: {h['text']}"

    def test_tier1_specific_in_late_rounds(self):
        G = _base_game(round_num=3)
        hints = [generate_grid_hint(G, "p3", 1, r, c) for r in range(5) for c in range(5)]
        wolf_hints = [h for h in hints if h["category"] == "wolf_count"]
        for h in wolf_hints:
            assert "between" not in h["text"], f"Expected specific text: {h['text']}"

    def test_night_recap_appears_when_pings_used(self):
        G = _base_game(round_num=3)
        G = G.model_copy(deep=True)
        G.night_actions.sonar_pings_used = 3
        hints = [generate_grid_hint(G, "p3", 1, r, c) for r in range(5) for c in range(5)]
        categories = {h["category"] for h in hints}
        assert "night_recap" in categories

    def test_night_recap_absent_when_no_pings(self):
        G = _base_game(round_num=3)
        assert G.night_actions.sonar_pings_used == 0
        hints = [generate_grid_hint(G, "p3", 1, r, c) for r in range(5) for c in range(5)]
        categories = {h["category"] for h in hints}
        assert "night_recap" not in categories


class TestGridHintTier2:
    def test_tier2_returns_relational_hint(self):
        G = _base_game(round_num=2)
        hint = generate_grid_hint(G, "p3", 2, 0, 2)  # tier 2 node
        assert hint["category"] in {
            "one_of_three", "same_alignment", "diff_alignment", "positional_clue"
        }, f"Unexpected Tier 2 category: {hint['category']}"

    def test_one_of_three_names_exactly_three_players(self):
        G = _base_game(round_num=2)
        hints = [generate_grid_hint(G, "p3", 2, r, c) for r in range(5) for c in range(5)]
        one_of_three = [h for h in hints if h["category"] == "one_of_three"]
        for h in one_of_three:
            # Text format: "At least one Wolf is among A, B, and C."
            assert "and" in h["text"]
            # Verify at least one real player name appears
            player_names = {p.display_name for p in G.players.values()}
            named = [n for n in player_names if n in h["text"]]
            assert len(named) == 3, f"Expected 3 player names: {h['text']}"

    def test_positional_clue_requires_grid_activity(self):
        G = _base_game(round_num=2)
        hints = [generate_grid_hint(G, "p3", 2, r, c) for r in range(5) for c in range(5)]
        pos_clues = [h for h in hints if h["category"] == "positional_clue"]
        # No grid activity → no positional clue
        assert len(pos_clues) == 0

    def test_positional_clue_appears_with_grid_activity(self):
        G = _base_game(round_num=2)
        G = G.model_copy(deep=True)
        G.night_actions.grid_activity = [
            {"row": 0, "col": 0, "quadrant": "top_left", "sequence_idx": 0},
            {"row": 0, "col": 1, "quadrant": "top_left", "sequence_idx": 1},
        ]
        hints = [generate_grid_hint(G, "p3", 2, r, c) for r in range(5) for c in range(5)]
        categories = {h["category"] for h in hints}
        assert "positional_clue" in categories

    def test_tier2_hint_payload_structure(self):
        G = _base_game(round_num=2)
        hint = generate_grid_hint(G, "p3", 2, 0, 2)
        for field in ("type", "hint_id", "category", "text", "round", "expires_after_round"):
            assert field in hint, f"Missing field: {field}"
        assert hint["type"] == "hint_reward"
        assert hint["round"] == G.round


class TestGridHintTier3:
    def test_tier3_returns_innocent_clear_or_action_log(self):
        G = _base_game(round_num=3)
        hint = generate_grid_hint(G, "p3", 3, 2, 2)
        assert hint["category"] in {"innocent_clear", "action_log"}, \
            f"Unexpected Tier 3 category: {hint['category']}"

    def test_innocent_clear_names_non_wolf(self):
        G = _base_game(round_num=3)
        hints = [generate_grid_hint(G, "p3", 3, r, c) for r in range(5) for c in range(5)]
        ic_hints = [h for h in hints if h["category"] == "innocent_clear"]
        wolf_names = {p.display_name for p in G.players.values() if p.team == "werewolf"}
        for h in ic_hints:
            for wn in wolf_names:
                assert wn not in h["text"], \
                    f"innocent_clear named a wolf: {h['text']}"

    def test_action_log_requires_high_change_count(self):
        G = _base_game(round_num=3)
        G = G.model_copy(deep=True)
        # Only 1 change → action_log should NOT appear (threshold is >= 2)
        G.night_actions.night_action_change_count = {"p1": 1}
        hints = [generate_grid_hint(G, "p3", 3, r, c) for r in range(5) for c in range(5)]
        categories = {h["category"] for h in hints}
        assert "action_log" not in categories

    def test_action_log_appears_with_high_change_count(self):
        G = _base_game(round_num=3)
        G = G.model_copy(deep=True)
        G.night_actions.night_action_change_count = {"p1": 4}
        hints = [generate_grid_hint(G, "p3", 3, r, c) for r in range(5) for c in range(5)]
        categories = {h["category"] for h in hints}
        assert "action_log" in categories

    def test_tier3_expires_never_for_innocent_clear(self):
        G = _base_game(round_num=3)
        hints = [generate_grid_hint(G, "p3", 3, r, c) for r in range(5) for c in range(5)]
        ic = [h for h in hints if h["category"] == "innocent_clear"]
        for h in ic:
            assert h["expires_after_round"] is None


# ── Stripper grid isolation (security invariant) ──────────────────────────────

class TestStripperGridIsolation:
    def _game_with_activity(self) -> MasterGameState:
        G = _base_game()
        G = G.model_copy(deep=True)
        G.night_actions.grid_activity = [
            {"row": 0, "col": 0, "quadrant": "top_left", "sequence_idx": 0},
        ]
        G.night_actions.sonar_pings_used = 2
        G.night_actions.sonar_ping_results = [
            {"quadrant": "top_left", "heat": 1, "tier_counts": {"1": 1, "2": 0, "3": 0}},
        ]
        G.night_actions.night_action_change_count = {"p1": 3}
        return G

    def test_wolves_see_grid_activity(self):
        G = self._game_with_activity()
        view = player_view(G, "p1")  # wolf
        assert "grid_activity" in view["night_actions"]
        assert len(view["night_actions"]["grid_activity"]) == 1

    def test_wolves_see_sonar_ping_results(self):
        G = self._game_with_activity()
        view = player_view(G, "p1")  # wolf
        assert "sonar_ping_results" in view["night_actions"]
        assert len(view["night_actions"]["sonar_ping_results"]) == 1

    def test_villagers_do_not_see_grid_activity(self):
        G = self._game_with_activity()
        view = player_view(G, "p3")  # villager
        assert "grid_activity" not in view["night_actions"]

    def test_villagers_do_not_see_sonar_ping_results(self):
        G = self._game_with_activity()
        view = player_view(G, "p3")  # villager
        assert "sonar_ping_results" not in view["night_actions"]

    def test_display_does_not_see_grid_activity(self):
        G = self._game_with_activity()
        view = player_view(G, None)  # display
        assert "grid_activity" not in view["night_actions"]

    def test_display_does_not_see_sonar_ping_results(self):
        G = self._game_with_activity()
        view = player_view(G, None)  # display
        assert "sonar_ping_results" not in view["night_actions"]

    def test_nobody_sees_night_action_change_count(self):
        G = self._game_with_activity()
        for pid in ["p1", "p2", "p3", None]:
            view = player_view(G, pid)
            assert "night_action_change_count" not in view["night_actions"], \
                f"night_action_change_count leaked to {pid!r}"

    def test_all_views_see_grid_layout(self):
        G = self._game_with_activity()
        for pid in ["p1", "p2", "p3", None]:
            view = player_view(G, pid)
            assert "grid_layout" in view["night_actions"], \
                f"grid_layout missing from {pid!r} view"
            assert view["night_actions"]["grid_layout"] is not None

    def test_all_views_see_sonar_pings_used(self):
        G = self._game_with_activity()
        for pid in ["p1", "p2", "p3", None]:
            view = player_view(G, pid)
            assert view["night_actions"]["sonar_pings_used"] == 2

    def test_grid_activity_contains_no_player_ids(self):
        """Security invariant: no player_id in grid_activity entries."""
        G = self._game_with_activity()
        view = player_view(G, "p1")  # wolf view
        for entry in view["night_actions"]["grid_activity"]:
            assert "player_id" not in entry, \
                f"Player ID leaked in grid_activity: {entry}"

    def test_grid_puzzle_state_stripped_from_other_players(self):
        G = _base_game()
        G = G.model_copy(deep=True)
        import random
        rng = random.Random("test")
        G.players["p3"].grid_puzzle_state = generate_grid_puzzle(2, rng)
        # p3's grid puzzle should NOT appear in p4's view
        view = player_view(G, "p4")
        assert view["players"]["p3"]["grid_puzzle_state"] is None

    def test_grid_puzzle_correct_index_stripped(self):
        G = _base_game()
        G = G.model_copy(deep=True)
        import random
        rng = random.Random("test")
        G.players["p3"].grid_puzzle_state = generate_grid_puzzle(2, rng)
        view = player_view(G, "p3")
        gps = view["players"]["p3"]["grid_puzzle_state"]
        assert gps is not None
        assert "correct_index" not in gps.get("puzzle_data", {}), \
            "correct_index leaked to client in grid_puzzle_state"

    def test_wolf_view_grid_puzzle_state_is_null(self):
        """Wolves don't use the grid — grid_puzzle_state must be None."""
        G = _base_game()
        G = G.model_copy(deep=True)
        import random
        # Give a villager a grid puzzle to ensure wolf view isn't confused
        G.players["p3"].grid_puzzle_state = generate_grid_puzzle(1, random.Random("t"))
        view = player_view(G, "p1")  # wolf
        assert view["players"]["p1"]["grid_puzzle_state"] is None


# ── machine.py NIGHT init ──────────────────────────────────────────────────────

class TestNightPhaseGridInit:
    def _game_with_players(self) -> MasterGameState:
        from engine.state.models import GameConfig
        from engine.state.enums import DifficultyLevel
        G = setup_game("init-seed", "p1", {})
        G = G.model_copy(deep=True)
        from engine.roles_loader import ROLE_REGISTRY
        roles = {"werewolf": 2, "villager": 2, "seer": 1}
        for i, (pid, role) in enumerate(zip(
            ["p1", "p2", "p3", "p4", "p5"],
            ["werewolf", "werewolf", "villager", "villager", "seer"]
        )):
            p = PlayerState(player_id=pid, display_name=f"P{i}")
            p.role = role
            p.team = ROLE_REGISTRY[role]["team"]
            G.players[pid] = p
        return G

    def test_grid_layout_set_on_night_entry(self):
        G = self._game_with_players()
        G.phase = Phase.DAY  # come from DAY
        G.round = 1
        G_night = transition_phase(G, Phase.NIGHT)
        assert G_night.night_actions.grid_layout is not None
        assert len(G_night.night_actions.grid_layout) == 5

    def test_grid_activity_cleared_on_night_entry(self):
        G = self._game_with_players()
        G.phase = Phase.DAY
        G.round = 1
        G_night = transition_phase(G, Phase.NIGHT)
        assert G_night.night_actions.grid_activity == []

    def test_sonar_pings_reset_on_night_entry(self):
        G = self._game_with_players()
        G.phase = Phase.DAY
        G.round = 1
        G_night = transition_phase(G, Phase.NIGHT)
        assert G_night.night_actions.sonar_pings_used == 0

    def test_player_grid_state_cleared_on_night_entry(self):
        G = self._game_with_players()
        G.phase = Phase.DAY
        G.round = 1
        # Pre-set grid state on a player
        G.players["p3"].grid_node_row = 2
        G.players["p3"].grid_node_col = 3
        import random
        G.players["p3"].grid_puzzle_state = generate_grid_puzzle(1, random.Random("t"))
        G_night = transition_phase(G, Phase.NIGHT)
        p3 = G_night.players["p3"]
        assert p3.grid_node_row is None
        assert p3.grid_node_col is None
        assert p3.grid_puzzle_state is None


# ── Intent handler: select_grid_node ─────────────────────────────────────────

class TestSelectGridNode:
    def _make_cm(self):
        cm = MagicMock()
        cm.unicast = AsyncMock()
        return cm

    @pytest.mark.asyncio
    async def test_assigns_grid_puzzle_to_player(self):
        from api.intents.handlers import handle_select_grid_node
        G = _base_game()
        intent = {"type": "select_grid_node", "player_id": "p3", "row": 0, "col": 0}
        G_new = await handle_select_grid_node(G, intent, None, self._make_cm())
        assert G_new.players["p3"].grid_puzzle_state is not None
        assert G_new.players["p3"].grid_node_row == 0
        assert G_new.players["p3"].grid_node_col == 0

    @pytest.mark.asyncio
    async def test_rejects_wolf_player(self):
        from api.intents.handlers import handle_select_grid_node
        from api.intents.errors import IntentError
        G = _base_game()
        intent = {"type": "select_grid_node", "player_id": "p1", "row": 0, "col": 0}
        with pytest.raises(IntentError) as exc_info:
            await handle_select_grid_node(G, intent, None, self._make_cm())
        assert exc_info.value.code == "NOT_YOUR_TURN"

    @pytest.mark.asyncio
    async def test_rejects_already_completed_node(self):
        from api.intents.handlers import handle_select_grid_node
        from api.intents.errors import IntentError
        G = _base_game()
        G = G.model_copy(deep=True)
        G.night_actions.grid_activity = [
            {"row": 0, "col": 0, "quadrant": "top_left", "sequence_idx": 0}
        ]
        intent = {"type": "select_grid_node", "player_id": "p3", "row": 0, "col": 0}
        with pytest.raises(IntentError) as exc_info:
            await handle_select_grid_node(G, intent, None, self._make_cm())
        assert exc_info.value.code == "NODE_OCCUPIED"

    @pytest.mark.asyncio
    async def test_rejects_out_of_range_coords(self):
        from api.intents.handlers import handle_select_grid_node
        from api.intents.errors import IntentError
        G = _base_game()
        intent = {"type": "select_grid_node", "player_id": "p3", "row": 5, "col": 0}
        with pytest.raises(IntentError) as exc_info:
            await handle_select_grid_node(G, intent, None, self._make_cm())
        assert exc_info.value.code == "INVALID_GRID_COORDS"

    @pytest.mark.asyncio
    async def test_increments_change_count(self):
        from api.intents.handlers import handle_select_grid_node
        G = _base_game()
        intent = {"type": "select_grid_node", "player_id": "p3", "row": 0, "col": 0}
        G_new = await handle_select_grid_node(G, intent, None, self._make_cm())
        assert G_new.night_actions.night_action_change_count.get("p3", 0) == 1


# ── Intent handler: submit_grid_answer ───────────────────────────────────────

class TestSubmitGridAnswer:
    def _make_cm(self):
        cm = MagicMock()
        cm.unicast = AsyncMock()
        return cm

    def _game_with_active_grid_puzzle(self, player_id: str, tier: int = 2):
        import random
        G = _base_game()
        G = G.model_copy(deep=True)
        rng = random.Random("test")
        puzzle = generate_grid_puzzle(tier, rng)
        G.players[player_id].grid_puzzle_state = puzzle
        G.players[player_id].grid_node_row = 0
        G.players[player_id].grid_node_col = 2
        return G

    @pytest.mark.asyncio
    async def test_correct_answer_records_activity(self):
        from api.intents.handlers import handle_submit_grid_answer
        G = self._game_with_active_grid_puzzle("p3")
        correct_idx = G.players["p3"].grid_puzzle_state.puzzle_data["correct_index"]
        intent = {"type": "submit_grid_answer", "player_id": "p3", "answer_index": correct_idx}
        G_new = await handle_submit_grid_answer(G, intent, None, self._make_cm())
        assert len(G_new.night_actions.grid_activity) == 1
        entry = G_new.night_actions.grid_activity[0]
        assert entry["row"] == 0
        assert entry["col"] == 2
        assert "player_id" not in entry  # security invariant

    @pytest.mark.asyncio
    async def test_correct_answer_clears_position(self):
        from api.intents.handlers import handle_submit_grid_answer
        G = self._game_with_active_grid_puzzle("p3")
        correct_idx = G.players["p3"].grid_puzzle_state.puzzle_data["correct_index"]
        intent = {"type": "submit_grid_answer", "player_id": "p3", "answer_index": correct_idx}
        G_new = await handle_submit_grid_answer(G, intent, None, self._make_cm())
        assert G_new.players["p3"].grid_node_row is None
        assert G_new.players["p3"].grid_node_col is None

    @pytest.mark.asyncio
    async def test_correct_answer_unicasts_hint_and_ripple(self):
        from api.intents.handlers import handle_submit_grid_answer
        G = self._game_with_active_grid_puzzle("p3")
        correct_idx = G.players["p3"].grid_puzzle_state.puzzle_data["correct_index"]
        cm = self._make_cm()
        intent = {"type": "submit_grid_answer", "player_id": "p3", "answer_index": correct_idx}
        await handle_submit_grid_answer(G, intent, None, cm)
        # At least 2 unicast calls: hint + ripple per wolf
        assert cm.unicast.call_count >= 2
        call_payloads = [str(call) for call in cm.unicast.call_args_list]
        assert any("hint_reward" in p for p in call_payloads)
        assert any("grid_ripple" in p for p in call_payloads)

    @pytest.mark.asyncio
    async def test_wrong_answer_clears_puzzle(self):
        from api.intents.handlers import handle_submit_grid_answer
        G = self._game_with_active_grid_puzzle("p3")
        correct_idx = G.players["p3"].grid_puzzle_state.puzzle_data["correct_index"]
        wrong_idx = (correct_idx + 1) % 4
        intent = {"type": "submit_grid_answer", "player_id": "p3", "answer_index": wrong_idx}
        G_new = await handle_submit_grid_answer(G, intent, None, self._make_cm())
        assert len(G_new.night_actions.grid_activity) == 0  # no activity recorded
        assert G_new.players["p3"].grid_node_row is None

    @pytest.mark.asyncio
    async def test_no_active_puzzle_raises(self):
        from api.intents.handlers import handle_submit_grid_answer
        from api.intents.errors import IntentError
        G = _base_game()
        intent = {"type": "submit_grid_answer", "player_id": "p3", "answer_index": 0}
        with pytest.raises(IntentError) as exc_info:
            await handle_submit_grid_answer(G, intent, None, self._make_cm())
        assert exc_info.value.code == "NO_ACTIVE_PUZZLE"


# ── Intent handler: sonar_ping ────────────────────────────────────────────────

class TestSonarPing:
    def _make_cm(self):
        cm = MagicMock()
        cm.unicast = AsyncMock()
        return cm

    @pytest.mark.asyncio
    async def test_wolf_can_ping(self):
        from api.intents.handlers import handle_sonar_ping
        G = _base_game()
        intent = {"type": "sonar_ping", "player_id": "p1", "quadrant": "top_left"}
        G_new = await handle_sonar_ping(G, intent, None, self._make_cm())
        assert G_new.night_actions.sonar_pings_used == 1
        assert len(G_new.night_actions.sonar_ping_results) == 1

    @pytest.mark.asyncio
    async def test_ping_result_has_correct_fields(self):
        from api.intents.handlers import handle_sonar_ping
        G = _base_game()
        intent = {"type": "sonar_ping", "player_id": "p1", "quadrant": "top_right"}
        G_new = await handle_sonar_ping(G, intent, None, self._make_cm())
        result = G_new.night_actions.sonar_ping_results[0]
        assert result["quadrant"] == "top_right"
        assert "heat" in result
        assert "tier_counts" in result

    @pytest.mark.asyncio
    async def test_ping_reflects_grid_activity(self):
        from api.intents.handlers import handle_sonar_ping
        G = _base_game()
        G = G.model_copy(deep=True)
        G.night_actions.grid_activity = [
            {"row": 0, "col": 0, "quadrant": "top_left", "sequence_idx": 0},
            {"row": 0, "col": 1, "quadrant": "top_left", "sequence_idx": 1},
        ]
        intent = {"type": "sonar_ping", "player_id": "p1", "quadrant": "top_left"}
        G_new = await handle_sonar_ping(G, intent, None, self._make_cm())
        result = G_new.night_actions.sonar_ping_results[0]
        assert result["heat"] == 2

    @pytest.mark.asyncio
    async def test_villager_cannot_ping(self):
        from api.intents.handlers import handle_sonar_ping
        from api.intents.errors import IntentError
        G = _base_game()
        intent = {"type": "sonar_ping", "player_id": "p3", "quadrant": "top_left"}
        with pytest.raises(IntentError) as exc_info:
            await handle_sonar_ping(G, intent, None, self._make_cm())
        assert exc_info.value.code == "NOT_WOLF"

    @pytest.mark.asyncio
    async def test_invalid_quadrant_raises(self):
        from api.intents.handlers import handle_sonar_ping
        from api.intents.errors import IntentError
        G = _base_game()
        intent = {"type": "sonar_ping", "player_id": "p1", "quadrant": "invalid_zone"}
        with pytest.raises(IntentError) as exc_info:
            await handle_sonar_ping(G, intent, None, self._make_cm())
        assert exc_info.value.code == "INVALID_QUADRANT"

    @pytest.mark.asyncio
    async def test_ping_limit_enforced(self):
        """Pack budget of 4 pings; 5th ping is rejected."""
        from api.intents.handlers import handle_sonar_ping
        from api.intents.errors import IntentError
        G = _base_game()
        G = G.model_copy(deep=True)
        G.night_actions.sonar_pings_used = 4  # budget exhausted

        intent = {"type": "sonar_ping", "player_id": "p1", "quadrant": "top_left"}
        with pytest.raises(IntentError) as exc_info:
            await handle_sonar_ping(G, intent, None, self._make_cm())
        assert exc_info.value.code == "SONAR_PING_LIMIT_REACHED"

    @pytest.mark.asyncio
    async def test_fourth_ping_succeeds_fifth_fails(self):
        """Exactly 4 pings are permitted; the 5th raises the limit error."""
        from api.intents.handlers import handle_sonar_ping
        from api.intents.errors import IntentError
        quadrants = ["top_left", "top_right", "bottom_left", "bottom_right"]
        G = _base_game()

        # Fire 4 pings — all must succeed
        for q in quadrants:
            G = await handle_sonar_ping(
                G, {"type": "sonar_ping", "player_id": "p1", "quadrant": q},
                None, self._make_cm()
            )
        assert G.night_actions.sonar_pings_used == 4

        # 5th ping must fail
        with pytest.raises(IntentError) as exc_info:
            await handle_sonar_ping(
                G, {"type": "sonar_ping", "player_id": "p1", "quadrant": "top_left"},
                None, self._make_cm()
            )
        assert exc_info.value.code == "SONAR_PING_LIMIT_REACHED"

    @pytest.mark.asyncio
    async def test_framer_can_ping(self):
        """Framer is wolf-team — backend allows them to fire sonar pings."""
        from api.intents.handlers import handle_sonar_ping
        G = _base_game()
        G = G.model_copy(deep=True)
        # p2 is wolf; give them framer role (team stays werewolf)
        G.players["p2"].role = "framer"
        G.players["p2"].team = Team.WEREWOLF

        intent = {"type": "sonar_ping", "player_id": "p2", "quadrant": "bottom_right"}
        G_new = await handle_sonar_ping(G, intent, None, self._make_cm())
        assert G_new.night_actions.sonar_pings_used == 1

    @pytest.mark.asyncio
    async def test_multiple_wolves_pings_accumulate(self):
        """Two wolves pinging the same quadrant produces 2 entries."""
        from api.intents.handlers import handle_sonar_ping
        G = _base_game()

        G = await handle_sonar_ping(
            G, {"type": "sonar_ping", "player_id": "p1", "quadrant": "top_left"},
            None, self._make_cm()
        )
        G = await handle_sonar_ping(
            G, {"type": "sonar_ping", "player_id": "p2", "quadrant": "top_left"},
            None, self._make_cm()
        )
        assert G.night_actions.sonar_pings_used == 2
        assert len(G.night_actions.sonar_ping_results) == 2


# ── Intent handler + resolver: wolf charge kill ───────────────────────────────

class TestWolfChargeKill:
    def _make_cm(self):
        cm = MagicMock()
        cm.unicast = AsyncMock()
        cm.broadcast = AsyncMock()
        return cm

    def _base_charge_game(self) -> MasterGameState:
        """6-player game with p3 actively solving a node in top_left quadrant."""
        import random
        G = _base_game()
        G = G.model_copy(deep=True)
        G.players["p3"].grid_node_row = 0
        G.players["p3"].grid_node_col = 0
        G.players["p3"].grid_puzzle_state = generate_grid_puzzle(1, random.Random("test"))
        return G

    @pytest.mark.asyncio
    async def test_pack_pool_fires_at_threshold(self):
        """Two wolves' combined ms >= 5000 sets charge_kill_target_id."""
        from api.intents.handlers import handle_wolf_charge_update
        G = self._base_charge_game()

        # p1 contributes 3000 ms — below threshold alone
        G = await handle_wolf_charge_update(
            G,
            {"type": "wolf_charge_update", "player_id": "p1", "quadrant": "top_left",
             "accumulated_ms": 3000, "is_active": True},
            None, self._make_cm(),
        )
        assert G.night_actions.charge_kill_target_id is None

        # p2 pushes pack total to 5500 ms — auto-fires
        G = await handle_wolf_charge_update(
            G,
            {"type": "wolf_charge_update", "player_id": "p2", "quadrant": "top_left",
             "accumulated_ms": 2500, "is_active": True},
            None, self._make_cm(),
        )
        assert G.night_actions.charge_kill_target_id == "p3"

    @pytest.mark.asyncio
    async def test_single_wolf_fires_alone(self):
        """One wolf accumulating 5000 ms alone fires the charge."""
        from api.intents.handlers import handle_wolf_charge_update
        G = self._base_charge_game()
        G = G.model_copy(deep=True)
        del G.players["p2"]  # only p1 is a wolf

        G = await handle_wolf_charge_update(
            G,
            {"type": "wolf_charge_update", "player_id": "p1", "quadrant": "top_left",
             "accumulated_ms": 5000, "is_active": True},
            None, self._make_cm(),
        )
        assert G.night_actions.charge_kill_target_id == "p3"

    def test_charge_kill_overrides_vote_in_resolve_night(self):
        """charge_kill_target_id set → charge target dies; wolf_votes target survives."""
        from engine.resolver.night import resolve_night
        G = _base_game()
        G = G.model_copy(deep=True)
        G.night_actions.charge_kill_target_id = "p3"
        G.night_actions.wolf_votes = {"p1": "p4", "p2": "p4"}

        G = resolve_night(G)

        assert not G.players["p3"].is_alive
        assert G.players["p4"].is_alive

    def test_charge_kill_cause_is_grid_charge_kill(self):
        """EliminationEvent.cause is GRID_CHARGE_KILL for charge-killed player."""
        from engine.resolver.night import resolve_night
        from engine.state.enums import EliminationCause
        G = _base_game()
        G = G.model_copy(deep=True)
        G.night_actions.charge_kill_target_id = "p3"

        G = resolve_night(G)

        charge_kills = [e for e in G.elimination_log if e.cause == EliminationCause.GRID_CHARGE_KILL]
        assert len(charge_kills) == 1
        assert charge_kills[0].player_id == "p3"

    def test_charge_kill_respects_doctor_protection(self):
        """Doctor-protected charge target survives; no elimination logged."""
        from engine.resolver.night import resolve_night
        G = _base_game()
        G = G.model_copy(deep=True)
        G.night_actions.charge_kill_target_id = "p3"
        G.players["p3"].is_protected = True

        G = resolve_night(G)

        assert G.players["p3"].is_alive
        charge_kills = [e for e in G.elimination_log if e.cause.value == "grid_charge_kill"]
        assert len(charge_kills) == 0

    @pytest.mark.asyncio
    async def test_charge_miss_on_empty_quadrant(self):
        """Pack total >= 5000 ms but no active solver → charge_kill_target_id stays None."""
        from api.intents.handlers import handle_wolf_charge_update
        G = _base_game()  # no villagers on grid nodes

        G = await handle_wolf_charge_update(
            G,
            {"type": "wolf_charge_update", "player_id": "p1", "quadrant": "top_left",
             "accumulated_ms": 5000, "is_active": True},
            None, self._make_cm(),
        )
        assert G.night_actions.charge_kill_target_id is None

    @pytest.mark.asyncio
    async def test_full_5000ms_kills_first_solver(self):
        """
        Full E2E: handler auto-fires at 5000 ms → charge_kill_target_id set →
        resolve_night() eliminates the target with cause GRID_CHARGE_KILL.
        Covers the gap between the handler and resolver tests.
        """
        from api.intents.handlers import handle_wolf_charge_update
        from engine.resolver.night import resolve_night
        from engine.state.enums import EliminationCause
        G = self._base_charge_game()
        G = G.model_copy(deep=True)
        del G.players["p2"]  # single wolf so threshold requires all 5000 ms from p1

        # Handler fires the charge
        G = await handle_wolf_charge_update(
            G,
            {"type": "wolf_charge_update", "player_id": "p1", "quadrant": "top_left",
             "accumulated_ms": 5000, "is_active": True},
            None, self._make_cm(),
        )
        assert G.night_actions.charge_kill_target_id == "p3"

        # Resolver eliminates the target
        G = resolve_night(G)
        assert not G.players["p3"].is_alive
        causes = [e.cause for e in G.elimination_log]
        assert EliminationCause.GRID_CHARGE_KILL in causes

    @pytest.mark.asyncio
    async def test_defend_resets_all_wolves_charges(self):
        """grid_defend breaks the entire pack's accumulated charge for that quadrant."""
        from api.intents.handlers import handle_wolf_charge_update, handle_grid_defend
        G = self._base_charge_game()

        # Both wolves charge top_left below the threshold
        G = await handle_wolf_charge_update(
            G,
            {"type": "wolf_charge_update", "player_id": "p1", "quadrant": "top_left",
             "accumulated_ms": 1000, "is_active": True},
            None, self._make_cm(),
        )
        G = await handle_wolf_charge_update(
            G,
            {"type": "wolf_charge_update", "player_id": "p2", "quadrant": "top_left",
             "accumulated_ms": 1000, "is_active": True},
            None, self._make_cm(),
        )

        # Villager defends
        G = await handle_grid_defend(
            G,
            {"type": "grid_defend", "player_id": "p3"},
            None, self._make_cm(),
        )

        # All wolves' charges for top_left must be 0
        for wolf_pid in ("p1", "p2"):
            assert G.night_actions.wolf_charges.get(wolf_pid, {}).get("top_left", 0) == 0
