"""
Unit tests for generate_hint() in puzzle_bank.py.
Covers vague/specific round progression and all hint categories.
"""
from __future__ import annotations

import pytest

from engine.hint_bank import generate_hint
from engine.setup import setup_game
from engine.state.enums import EliminationCause, Phase, Team
from engine.state.models import EliminationEvent, NightActions, PlayerState


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_player(pid: str, role: str, team: Team, alive: bool = True) -> PlayerState:
    p = PlayerState(player_id=pid, display_name=pid, avatar_id="default_01")
    p.role = role
    p.team = team
    p.is_alive = alive
    return p


def _base_game(round_num: int = 1) -> object:
    """Minimal game state: 2 wolves + 4 villagers, no special roles."""
    G = setup_game("test-seed", "p1", {})
    G = G.model_copy(deep=True)
    G.phase = Phase.NIGHT
    G.round = round_num
    G.players = {
        "p1": _make_player("p1", "werewolf", Team.WEREWOLF),
        "p2": _make_player("p2", "werewolf", Team.WEREWOLF),
        "p3": _make_player("p3", "villager", Team.VILLAGE),
        "p4": _make_player("p4", "villager", Team.VILLAGE),
        "p5": _make_player("p5", "seer", Team.VILLAGE),
        "p6": _make_player("p6", "villager", Team.VILLAGE),
    }
    G.night_actions = NightActions()
    G.lovers_pair = None
    G.elimination_log = []
    return G


def _hint_for(G, player_id: str = "p3") -> dict:
    return generate_hint(G, player_id)


def _all_hints(G, player_id: str = "p3", samples: int = 50) -> list[dict]:
    """Generate hints with varied seeds to collect all possible categories."""
    hints = []
    for i in range(samples):
        G2 = G.model_copy(deep=True)
        G2.seed = f"seed-{i}"
        hints.append(generate_hint(G2, player_id))
    return hints


# ── wolf_count: vague in rounds 1–2, specific in round 3+ ────────────────────


class TestWolfCountProgression:
    def test_vague_round_1(self):
        G = _base_game(round_num=1)
        hint = _hint_for(G)
        # Force wolf_count category by using a game with only baseline roles
        # so the only guaranteed pool entry is wolf_count — collect all samples
        hints = _all_hints(G)
        wolf_hints = [h for h in hints if h["category"] == "wolf_count"]
        assert wolf_hints, "wolf_count should appear in round 1"
        for h in wolf_hints:
            assert "between" in h["text"], f"Round 1 wolf_count should be vague: {h['text']}"
            assert "and" in h["text"]

    def test_vague_round_2(self):
        G = _base_game(round_num=2)
        hints = _all_hints(G)
        wolf_hints = [h for h in hints if h["category"] == "wolf_count"]
        assert wolf_hints
        for h in wolf_hints:
            assert "between" in h["text"], f"Round 2 wolf_count should be vague: {h['text']}"

    def test_specific_round_3(self):
        G = _base_game(round_num=3)
        hints = _all_hints(G)
        wolf_hints = [h for h in hints if h["category"] == "wolf_count"]
        assert wolf_hints
        for h in wolf_hints:
            assert "between" not in h["text"], f"Round 3 wolf_count should be specific: {h['text']}"
            assert "2" in h["text"], "Should contain exact wolf count (2)"

    def test_vague_range_is_correct(self):
        """Vague range should be [max(1, N-1), N+1] for N wolves."""
        G = _base_game(round_num=1)  # 2 wolves → range 1–3
        hints = _all_hints(G)
        wolf_hints = [h for h in hints if h["category"] == "wolf_count"]
        for h in wolf_hints:
            assert "1" in h["text"] and "3" in h["text"], (
                f"Expected range 1–3 for 2 wolves, got: {h['text']}"
            )

    def test_wolf_count_expires_never(self):
        G = _base_game(round_num=3)
        hints = _all_hints(G)
        wolf_hints = [h for h in hints if h["category"] == "wolf_count"]
        for h in wolf_hints:
            assert h["expires_after_round"] is None


# ── no_role_present: vague / specific ────────────────────────────────────────


class TestNoRolePresent:
    def _game_with_absent_role(self, round_num: int) -> object:
        """Game without alpha_wolf — ensures no_role_present pool entry exists."""
        G = _base_game(round_num)
        # No alpha_wolf in default _base_game — so alpha_wolf is absent
        return G

    def test_vague_does_not_reveal_role_name(self):
        G = self._game_with_absent_role(round_num=1)
        hints = _all_hints(G)
        no_role_hints = [h for h in hints if h["category"] == "no_role_present"]
        assert no_role_hints, "no_role_present should appear in round 1"
        for h in no_role_hints:
            # Vague text should not contain any specific role name
            for role in ["Alpha Wolf", "Framer", "Infector", "Serial Killer", "Arsonist"]:
                assert role not in h["text"], (
                    f"Round 1 no_role_present should not name role '{role}': {h['text']}"
                )

    def test_specific_reveals_role_name(self):
        G = self._game_with_absent_role(round_num=3)
        hints = _all_hints(G)
        no_role_hints = [h for h in hints if h["category"] == "no_role_present"]
        assert no_role_hints, "no_role_present should appear in round 3"
        # At least one should name a role (alpha_wolf → "Alpha Wolf")
        named = [h for h in no_role_hints if "NO" in h["text"]]
        assert named, f"Round 3 no_role_present should name the absent role: {no_role_hints}"

    def test_expires_never(self):
        G = self._game_with_absent_role(round_num=3)
        hints = _all_hints(G)
        for h in hints:
            if h["category"] == "no_role_present":
                assert h["expires_after_round"] is None


# ── role_present: vague / specific ───────────────────────────────────────────


class TestRolePresent:
    def _game_with_special_role(self, round_num: int) -> object:
        """Add a doctor (non-baseline special role) to ensure role_present pool entry."""
        G = _base_game(round_num)
        G.players["p6"] = _make_player("p6", "doctor", Team.VILLAGE)
        return G

    def test_vague_does_not_reveal_role_name(self):
        G = self._game_with_special_role(round_num=2)
        hints = _all_hints(G)
        role_hints = [h for h in hints if h["category"] == "role_present"]
        assert role_hints, "role_present should appear in round 2"
        for h in role_hints:
            assert "Doctor" not in h["text"] and "Tracker" not in h["text"], (
                f"Round 2 role_present should not name role: {h['text']}"
            )

    def test_specific_reveals_role_name(self):
        G = self._game_with_special_role(round_num=3)
        hints = _all_hints(G)
        role_hints = [h for h in hints if h["category"] == "role_present"]
        assert role_hints
        named = [h for h in role_hints if "IS a" in h["text"]]
        assert named, f"Round 3 role_present should name the role: {role_hints}"

    def test_expires_never(self):
        G = self._game_with_special_role(round_num=3)
        hints = _all_hints(G)
        for h in hints:
            if h["category"] == "role_present":
                assert h["expires_after_round"] is None


# ── non_wolf_kill ─────────────────────────────────────────────────────────────


class TestNonWolfKill:
    def _add_sk_kill(self, G, kill_round: int) -> object:
        G = G.model_copy(deep=True)
        G.elimination_log = [
            EliminationEvent(
                round=kill_round,
                phase="night",
                player_id="p4",
                cause=EliminationCause.SERIAL_KILLER,
            )
        ]
        return G

    def test_appears_in_round_2_after_sk_kill(self):
        G = _base_game(round_num=2)
        G = self._add_sk_kill(G, kill_round=1)
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "non_wolf_kill" in categories, (
            "non_wolf_kill should appear when last night had SK kill"
        )

    def test_text_content(self):
        G = _base_game(round_num=2)
        G = self._add_sk_kill(G, kill_round=1)
        hints = _all_hints(G)
        nwk = [h for h in hints if h["category"] == "non_wolf_kill"]
        assert nwk
        assert "not the wolves" in nwk[0]["text"]

    def test_expires_next_round(self):
        G = _base_game(round_num=2)
        G = self._add_sk_kill(G, kill_round=1)
        hints = _all_hints(G)
        nwk = [h for h in hints if h["category"] == "non_wolf_kill"]
        for h in nwk:
            assert h["expires_after_round"] == 3  # round 2 + 1

    def test_absent_in_round_1(self):
        G = _base_game(round_num=1)
        G = self._add_sk_kill(G, kill_round=0)
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "non_wolf_kill" not in categories, (
            "non_wolf_kill should not appear in round 1"
        )

    def test_absent_when_only_wolf_kill(self):
        G = _base_game(round_num=2)
        G = G.model_copy(deep=True)
        G.elimination_log = [
            EliminationEvent(
                round=1,
                phase="night",
                player_id="p4",
                cause=EliminationCause.WOLF_KILL,
            )
        ]
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "non_wolf_kill" not in categories

    def test_triggers_on_arsonist_ignite(self):
        G = _base_game(round_num=3)
        G = G.model_copy(deep=True)
        G.elimination_log = [
            EliminationEvent(
                round=2,
                phase="night",
                player_id="p4",
                cause=EliminationCause.ARSONIST_IGNITE,
            )
        ]
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "non_wolf_kill" in categories

    def test_triggers_on_broken_heart(self):
        G = _base_game(round_num=3)
        G = G.model_copy(deep=True)
        G.elimination_log = [
            EliminationEvent(
                round=2,
                phase="night",
                player_id="p4",
                cause=EliminationCause.BROKEN_HEART,
            )
        ]
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "non_wolf_kill" in categories


# ── lovers_exist ──────────────────────────────────────────────────────────────


def _lovers_only_game(round_num: int) -> object:
    """Game with lovers_pair set and only baseline roles so lovers_exist is the
    only non-wolf_count pool entry — makes it reliably sampled."""
    G = _base_game(round_num)
    # Remove seer so present_special is empty (no role_present pool entry)
    G.players["p5"] = _make_player("p5", "villager", Team.VILLAGE)
    G.lovers_pair = ["p3", "p5"]
    return G


class TestLoversExist:
    def test_appears_when_lovers_pair_set(self):
        G = _lovers_only_game(round_num=1)
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "lovers_exist" in categories

    def test_absent_when_no_lovers_pair(self):
        G = _base_game(round_num=1)
        assert G.lovers_pair is None
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "lovers_exist" not in categories

    def test_vague_text_round_1(self):
        G = _lovers_only_game(round_num=1)
        hints = _all_hints(G)
        lovers = [h for h in hints if h["category"] == "lovers_exist"]
        assert lovers
        for h in lovers:
            assert "bond" in h["text"], f"Round 1 should use vague text: {h['text']}"
            assert "falls" not in h["text"]

    def test_vague_text_round_2(self):
        G = _lovers_only_game(round_num=2)
        hints = _all_hints(G)
        lovers = [h for h in hints if h["category"] == "lovers_exist"]
        assert lovers
        for h in lovers:
            assert "bond" in h["text"]

    def test_specific_text_round_3(self):
        G = _lovers_only_game(round_num=3)
        hints = _all_hints(G)
        lovers = [h for h in hints if h["category"] == "lovers_exist"]
        assert lovers
        for h in lovers:
            assert "falls" in h["text"], f"Round 3 should use specific text: {h['text']}"
            assert "bond" not in h["text"]

    def test_expires_never(self):
        G = _lovers_only_game(round_num=3)
        hints = _all_hints(G)
        for h in hints:
            if h["category"] == "lovers_exist":
                assert h["expires_after_round"] is None


# ── Payload structure ─────────────────────────────────────────────────────────


class TestHintPayloadStructure:
    def test_required_fields_present(self):
        G = _base_game(round_num=1)
        hint = _hint_for(G)
        for field in ("type", "hint_id", "category", "text", "round", "expires_after_round"):
            assert field in hint, f"Missing field: {field}"

    def test_type_is_hint_reward(self):
        G = _base_game(round_num=1)
        hint = _hint_for(G)
        assert hint["type"] == "hint_reward"

    def test_round_matches_game_round(self):
        for r in (1, 2, 3, 5):
            G = _base_game(round_num=r)
            hint = _hint_for(G)
            assert hint["round"] == r

    def test_hint_id_is_unique(self):
        G = _base_game(round_num=1)
        ids = {_hint_for(G)["hint_id"] for _ in range(20)}
        assert len(ids) == 20, "hint_id should be unique per call"
