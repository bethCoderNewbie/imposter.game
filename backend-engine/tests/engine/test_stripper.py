"""
State Stripper tests — the security boundary of the entire system.
Zero role leaks permitted. Every test here prevents a cheat vector.
"""

from __future__ import annotations

import pytest

from engine.state.enums import Phase, Team, InvestigationResult
from engine.state.models import MasterGameState, NightActions, PlayerState, PuzzleState
from engine.stripper import player_view, strip_fabricated_flag
from tests.conftest import _eight_player_game, _make_player


# ── Helper ─────────────────────────────────────────────────────────────────────

def _view(G: MasterGameState, pid: str | None) -> dict:
    return player_view(G, pid)


# ── Display view (pid=None) ────────────────────────────────────────────────────

class TestDisplayView:
    def test_display_never_receives_role(self):
        G, _ = _eight_player_game()
        view = _view(G, None)
        for pid, p in view["players"].items():
            assert p["role"] is None, f"Display leaked role for {pid}"

    def test_display_never_receives_team(self):
        G, _ = _eight_player_game()
        view = _view(G, None)
        for pid, p in view["players"].items():
            assert p["team"] is None, f"Display leaked team for {pid}"

    def test_display_never_receives_wolf_votes(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.wolf_votes = {"p1": "p3"}
        view = _view(G, None)
        assert "wolf_votes" not in view.get("night_actions", {})

    def test_display_never_receives_seer_knowledge(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.seer_knowledge = {"p1": "wolf"}
        view = _view(G, None)
        assert view.get("seer_knowledge", {}) == {}

    def test_display_night_actions_only_counts(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.actions_submitted_count = 2
        G.night_actions.actions_required_count = 3
        view = _view(G, None)
        na = view["night_actions"]
        assert na["actions_submitted_count"] == 2
        assert na["actions_required_count"] == 3
        # Should not contain sensitive fields
        assert "seer_target_id" not in na
        assert "doctor_target_id" not in na

    def test_display_lovers_pair_null_during_live_play(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.lovers_pair = ["p3", "p4"]
        view = _view(G, None)
        assert view.get("lovers_pair") is None

    def test_display_reveals_lovers_at_game_over(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.GAME_OVER
        G.lovers_pair = ["p3", "p4"]
        view = _view(G, None)
        assert view.get("lovers_pair") == ["p3", "p4"]


# ── Server-only fields — never sent to any client ─────────────────────────────

class TestAlwaysStripped:
    def test_is_protected_never_sent(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p4"].is_protected = True
        view = _view(G, "p4")
        assert "is_protected" not in view["players"]["p4"]

    def test_session_token_never_in_broadcast(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p3"].session_token = "supersecrettoken"
        for pid in ["p3", "p1", None]:
            view = _view(G, pid)
            for _, p in view["players"].items():
                assert "session_token" not in p, "session_token leaked!"

    def test_hunter_fired_never_sent(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p5"].hunter_fired = True
        for pid in [None, "p5", "p1"]:
            view = _view(G, pid)
            for _, p in view["players"].items():
                assert "hunter_fired" not in p

    def test_is_framed_tonight_never_sent(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p6"].is_framed_tonight = True
        view = _view(G, None)
        for _, p in view["players"].items():
            assert "is_framed_tonight" not in p

    def test_last_protected_never_sent(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p4"].last_protected_player_id = "p3"
        view = _view(G, "p4")
        assert "last_protected_player_id" not in view["players"]["p4"]

    def test_false_hint_queued_never_sent(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.false_hint_queued = True
        for pid in [None, "p3", "p1"]:
            view = _view(G, pid)
            assert "false_hint_queued" not in view.get("night_actions", {})

    def test_infect_used_never_sent(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p1"].infect_used = True
        for pid in [None, "p1"]:
            view = _view(G, pid)
            for _, p in view["players"].items():
                assert "infect_used" not in p

    def test_puzzle_correct_index_stripped(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.puzzle_state = PuzzleState(
            puzzle_type="math",
            puzzle_data={"options": [1, 2, 3], "correct_index": 1},
            time_limit_seconds=30,
        )
        view = _view(G, "p6")  # villager sees puzzle
        na = view.get("night_actions", {})
        if na.get("puzzle_state"):
            pd = na["puzzle_state"].get("puzzle_data", {})
            assert "correct_index" not in pd, "correct_index leaked to client!"


# ── Wolf team view ─────────────────────────────────────────────────────────────

class TestWolfTeamView:
    def test_wolf_sees_own_role(self):
        G, _ = _eight_player_game()
        view = _view(G, "p1")
        assert view["players"]["p1"]["role"] == "werewolf"

    def test_wolf_sees_teammate_role(self):
        G, _ = _eight_player_game()
        view = _view(G, "p1")
        assert view["players"]["p2"]["role"] == "werewolf"

    def test_wolf_cannot_see_village_roles(self):
        G, _ = _eight_player_game()
        view = _view(G, "p1")
        for pid in ["p3", "p4", "p5", "p6", "p7", "p8"]:
            assert view["players"][pid]["role"] is None, f"Wolf leaked village role for {pid}"

    def test_wolf_sees_wolf_votes(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.wolf_votes = {"p1": "p3"}
        view = _view(G, "p1")
        assert view["night_actions"]["wolf_votes"] == {"p1": "p3"}

    def test_wolf_does_not_see_seer_target(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.seer_target_id = "p2"
        view = _view(G, "p1")
        assert view["night_actions"].get("seer_target_id") is None


# ── Seer view ──────────────────────────────────────────────────────────────────

class TestSeerView:
    def test_seer_sees_own_role(self):
        G, _ = _eight_player_game()
        view = _view(G, "p3")
        assert view["players"]["p3"]["role"] == "seer"

    def test_seer_sees_seer_target_and_result(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.seer_target_id = "p1"
        G.night_actions.seer_result = InvestigationResult.WOLF
        view = _view(G, "p3")
        na = view["night_actions"]
        assert na["seer_target_id"] == "p1"
        assert na["seer_result"] == "wolf"

    def test_seer_receives_accumulated_seer_knowledge(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.seer_knowledge = {"p1": "wolf", "p4": "village"}
        view = _view(G, "p3")
        assert view["seer_knowledge"] == {"p1": "wolf", "p4": "village"}

    def test_seer_cannot_see_wolf_votes(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.night_actions.wolf_votes = {"p1": "p4"}
        view = _view(G, "p3")
        assert view["night_actions"].get("wolf_votes", {}) == {}

    def test_seer_cannot_see_other_player_roles(self):
        G, _ = _eight_player_game()
        view = _view(G, "p3")
        # Seer should not see wolf/doctor/tracker roles for other players
        for pid in ["p1", "p2", "p4", "p5", "p6", "p7", "p8"]:
            assert view["players"][pid]["role"] is None


# ── Villager/baseline alive view ───────────────────────────────────────────────

class TestBaselineAliveView:
    def test_villager_sees_only_own_role(self):
        G, _ = _eight_player_game()
        view = _view(G, "p6")
        assert view["players"]["p6"]["role"] == "villager"
        for pid in ["p1", "p2", "p3", "p4", "p5", "p7", "p8"]:
            assert view["players"][pid]["role"] is None

    def test_doctor_sees_own_role(self):
        G, _ = _eight_player_game()
        view = _view(G, "p4")
        assert view["players"]["p4"]["role"] == "doctor"

    def test_villager_cannot_see_seer_knowledge(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.seer_knowledge = {"p1": "wolf"}
        view = _view(G, "p6")
        assert view.get("seer_knowledge", {}) == {}


# ── Dead spectator view ────────────────────────────────────────────────────────

class TestDeadSpectatorView:
    def test_dead_player_sees_all_roles_at_game_over(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.GAME_OVER
        G.players["p6"].is_alive = False
        view = _view(G, "p6")
        # At game_over, dead spectator should see roles
        for pid in ["p1", "p2", "p3", "p4"]:
            assert view["players"][pid]["role"] is not None, f"Dead spectator missing role for {pid}"

    def test_dead_player_during_live_play_sees_all_roles(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p6"].is_alive = False
        # Dead players see all roles (they are spectators — can't affect game)
        view = _view(G, "p6")
        assert view["players"]["p1"]["role"] == "werewolf"
        assert view["players"]["p3"]["role"] == "seer"
        # But night_actions sensitive fields are stripped
        na = view.get("night_actions", {})
        assert "wolf_votes" not in na or na.get("wolf_votes") == {}


# ── Role-specific private fields ───────────────────────────────────────────────

class TestRoleSpecificFields:
    def test_arsonist_sees_own_doused_players(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p1"].role = "arsonist"
        G.players["p1"].team = Team.NEUTRAL
        G.players["p1"].doused_player_ids = ["p3", "p4"]
        view = _view(G, "p1")
        assert view["players"]["p1"]["doused_player_ids"] == ["p3", "p4"]

    def test_non_arsonist_cannot_see_doused_players(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p1"].doused_player_ids = ["p3", "p4"]
        view = _view(G, "p3")  # seer view
        assert view["players"]["p1"].get("doused_player_ids", []) == []

    def test_lovers_see_own_partner(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p3"].lovers_partner_id = "p4"
        G.players["p4"].lovers_partner_id = "p3"
        G.lovers_pair = ["p3", "p4"]
        view_p3 = _view(G, "p3")
        assert view_p3["players"]["p3"]["lovers_partner_id"] == "p4"

    def test_non_lover_cannot_see_partner(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.players["p3"].lovers_partner_id = "p4"
        G.players["p4"].lovers_partner_id = "p3"
        G.lovers_pair = ["p3", "p4"]
        view_p6 = _view(G, "p6")
        assert view_p6["players"]["p3"].get("lovers_partner_id") is None


# ── Alpha Wolf investigation result ────────────────────────────────────────────

class TestAlphaWolfSeerResult:
    def test_alpha_wolf_investigation_result_is_village(self):
        """Alpha Wolf appears as 'village' to Seer — never 'wolf'."""
        from engine.roles_loader import ROLE_REGISTRY
        if "alpha_wolf" in ROLE_REGISTRY:
            alpha = ROLE_REGISTRY["alpha_wolf"]
            assert alpha["investigationResult"] == "village", \
                "Alpha Wolf must appear as 'village' to Seer"


# ── strip_fabricated_flag ──────────────────────────────────────────────────────

class TestStripFabricatedFlag:
    def test_removes_is_fabricated_field(self):
        payload = {
            "hint_id": "abc123",
            "category": "role_present",
            "text": "A wolf lurks nearby.",
            "round": 2,
            "expires_after_round": None,
            "is_fabricated": True,
        }
        result = strip_fabricated_flag(payload)
        assert "is_fabricated" not in result

    def test_preserves_other_fields(self):
        payload = {
            "hint_id": "abc123",
            "category": "role_present",
            "text": "A wolf lurks nearby.",
            "round": 2,
            "expires_after_round": None,
            "is_fabricated": True,
        }
        result = strip_fabricated_flag(payload)
        assert result["hint_id"] == "abc123"
        assert result["text"] == "A wolf lurks nearby."

    def test_no_error_if_not_present(self):
        payload = {"hint_id": "xyz", "text": "hint"}
        result = strip_fabricated_flag(payload)
        assert "is_fabricated" not in result
