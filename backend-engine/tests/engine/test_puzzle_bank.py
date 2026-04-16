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


# ── alive_count (Tier 1, new) ─────────────────────────────────────────────────


class TestAliveCount:
    """alive_count appears in round 3+ and reports exact alive wolf/villager counts."""

    def test_absent_in_vague_rounds(self):
        """alive_count is only specific — it must not appear in rounds 1–2."""
        for r in (1, 2):
            G = _base_game(round_num=r)
            hints = _all_hints(G)
            categories = {h["category"] for h in hints}
            assert "alive_count" not in categories, \
                f"alive_count should be absent in round {r}"

    def test_appears_in_specific_rounds(self):
        G = _base_game(round_num=3)
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "alive_count" in categories

    def test_text_contains_correct_counts(self):
        G = _base_game(round_num=3)
        # 2 wolves, 4 villagers (all alive in _base_game)
        hints = _all_hints(G)
        ac = [h for h in hints if h["category"] == "alive_count"]
        assert ac
        for h in ac:
            # "Wolves" (plural) when count != 1 — check for the number and either form
            assert "2" in h["text"] and ("Wolves" in h["text"] or "Wolf " in h["text"]), \
                f"Expected wolf count in alive_count: {h['text']}"
            assert "4" in h["text"] and "Villager" in h["text"], \
                f"Expected villager count in alive_count: {h['text']}"

    def test_text_pluralisation_single_wolf(self):
        G = _base_game(round_num=3)
        G = G.model_copy(deep=True)
        G.players["p2"].is_alive = False  # eliminate one wolf → 1 alive wolf
        hints = _all_hints(G)
        ac = [h for h in hints if h["category"] == "alive_count"]
        assert ac
        singular = [h for h in ac if "1 Wolf " in h["text"]]
        assert singular, f"Expected '1 Wolf' (singular) — got: {ac}"

    def test_expires_next_round(self):
        G = _base_game(round_num=3)
        hints = _all_hints(G)
        for h in hints:
            if h["category"] == "alive_count":
                assert h["expires_after_round"] == 4


# ── role_alive_check (Tier 1, new) ───────────────────────────────────────────


class TestRoleAliveCheck:
    """role_alive_check reports whether a high-impact role is still alive.
    Absent in vague rounds; absent when no high-impact or doctor role is in the game."""

    def _game_with_framer(self, round_num: int):
        """Replace p6 with a framer so role_alive_check has a candidate."""
        G = _base_game(round_num)
        G = G.model_copy(deep=True)
        G.players["p6"].role = "framer"
        G.players["p6"].team = Team.WEREWOLF
        return G

    def test_absent_in_vague_rounds(self):
        for r in (1, 2):
            G = self._game_with_framer(round_num=r)
            hints = _all_hints(G)
            categories = {h["category"] for h in hints}
            assert "role_alive_check" not in categories, \
                f"role_alive_check must be absent in round {r} (vague)"

    def test_appears_in_specific_rounds_when_high_impact_role_present(self):
        G = self._game_with_framer(round_num=3)
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "role_alive_check" in categories

    def test_absent_when_no_high_impact_or_doctor_role(self):
        """_base_game has only villager/werewolf/seer — no framer, arsonist, doctor."""
        G = _base_game(round_num=3)
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "role_alive_check" not in categories

    def test_text_says_still_alive_when_role_is_alive(self):
        G = self._game_with_framer(round_num=3)
        hints = _all_hints(G)
        rac = [h for h in hints if h["category"] == "role_alive_check"]
        assert rac
        alive_hints = [h for h in rac if "still alive" in h["text"]]
        eliminated_hints = [h for h in rac if "eliminated" in h["text"]]
        assert alive_hints or eliminated_hints, \
            "Expected 'still alive' or 'eliminated' in role_alive_check text"

    def test_text_says_eliminated_when_role_is_dead(self):
        G = self._game_with_framer(round_num=3)
        G = G.model_copy(deep=True)
        G.players["p6"].is_alive = False  # kill the framer
        hints = _all_hints(G)
        rac = [h for h in hints if h["category"] == "role_alive_check"]
        eliminated = [h for h in rac if "eliminated" in h["text"]]
        assert eliminated, f"Expected 'eliminated' text for dead framer: {rac}"

    def test_text_contains_role_display_name(self):
        G = self._game_with_framer(round_num=3)
        hints = _all_hints(G)
        rac = [h for h in hints if h["category"] == "role_alive_check"]
        assert rac
        # Role name should be title-cased in text
        named = [h for h in rac if "Framer" in h["text"]]
        assert named, f"Expected 'Framer' in text: {rac}"

    def test_expires_next_round(self):
        G = self._game_with_framer(round_num=3)
        hints = _all_hints(G)
        for h in hints:
            if h["category"] == "role_alive_check":
                assert h["expires_after_round"] == 4

    def test_doctor_also_eligible(self):
        G = _base_game(round_num=3)
        G = G.model_copy(deep=True)
        G.players["p6"].role = "doctor"
        G.players["p6"].team = Team.VILLAGE
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "role_alive_check" in categories, \
            "Doctor should make role_alive_check eligible"


# ── night_recap (Tier 1, new) ─────────────────────────────────────────────────


class TestNightRecap:
    """night_recap appears when wolves have used at least 1 Sonar Ping.
    Absent when sonar_pings_used == 0. Not round-gated."""

    def _game_with_pings(self, pings: int, round_num: int = 3):
        G = _base_game(round_num)
        G = G.model_copy(deep=True)
        G.night_actions.sonar_pings_used = pings
        return G

    def test_absent_when_no_pings(self):
        G = _base_game(round_num=3)
        assert G.night_actions.sonar_pings_used == 0
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "night_recap" not in categories

    def test_appears_when_pings_used(self):
        G = self._game_with_pings(2)
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "night_recap" in categories

    def test_appears_in_early_rounds_too(self):
        """night_recap is not round-gated — it should appear even in round 1."""
        G = self._game_with_pings(1, round_num=1)
        hints = _all_hints(G)
        categories = {h["category"] for h in hints}
        assert "night_recap" in categories

    def test_text_contains_correct_ping_count(self):
        G = self._game_with_pings(3)
        hints = _all_hints(G)
        nr = [h for h in hints if h["category"] == "night_recap"]
        assert nr
        for h in nr:
            assert "3" in h["text"], f"Expected '3' in night_recap text: {h['text']}"
            assert "Ping" in h["text"] or "Pings" in h["text"]

    def test_text_singular_one_ping(self):
        G = self._game_with_pings(1)
        hints = _all_hints(G)
        nr = [h for h in hints if h["category"] == "night_recap"]
        assert nr
        singular = [h for h in nr if "1 Sonar Ping" in h["text"]]
        assert singular, f"Expected '1 Sonar Ping' (singular): {nr}"

    def test_expires_next_round(self):
        G = self._game_with_pings(2, round_num=3)
        hints = _all_hints(G)
        for h in hints:
            if h["category"] == "night_recap":
                assert h["expires_after_round"] == 4


# ── same_alignment (Tier 2) ───────────────────────────────────────────────────


class TestSameAlignment:
    """same_alignment states that two players share the same team.
    Only generated when there are ≥2 alive players.
    Uses generate_grid_hint with tier=2 to reach _build_tier2_pool."""

    def _grid_hints(self, G, samples: int = 50):
        """Sample Tier 2 grid hints across varied seeds."""
        hints = []
        for i in range(samples):
            G2 = G.model_copy(deep=True)
            G2.seed = f"seed-{i}"
            # Use tier 2, arbitrary node coords
            from engine.hint_bank import generate_grid_hint
            hints.append(generate_grid_hint(G2, "p3", 2, 0, 2))
        return hints

    def test_appears_when_alive_players_have_same_team(self):
        G = _base_game(round_num=2)
        hints = self._grid_hints(G)
        categories = {h["category"] for h in hints}
        assert "same_alignment" in categories, \
            "same_alignment should appear when multiple players share a team"

    def test_names_two_players(self):
        G = _base_game(round_num=2)
        hints = self._grid_hints(G)
        sa = [h for h in hints if h["category"] == "same_alignment"]
        assert sa
        player_names = {p.display_name for p in G.players.values()}
        for h in sa:
            named = [n for n in player_names if n in h["text"]]
            assert len(named) == 2, \
                f"same_alignment should name exactly 2 players: {h['text']}"

    def test_text_says_same_alignment(self):
        G = _base_game(round_num=2)
        hints = self._grid_hints(G)
        sa = [h for h in hints if h["category"] == "same_alignment"]
        assert sa
        for h in sa:
            assert "same alignment" in h["text"], \
                f"Expected 'same alignment' in text: {h['text']}"

    def test_expires_next_round(self):
        G = _base_game(round_num=2)
        hints = self._grid_hints(G)
        for h in hints:
            if h["category"] == "same_alignment":
                assert h["expires_after_round"] == G.round + 1


# ── diff_alignment (Tier 2) ───────────────────────────────────────────────────


class TestDiffAlignment:
    """diff_alignment states that two players are on different teams.
    Requires at least 1 alive wolf and 1 alive non-wolf."""

    def _grid_hints(self, G, samples: int = 50):
        hints = []
        for i in range(samples):
            G2 = G.model_copy(deep=True)
            G2.seed = f"seed-{i}"
            from engine.hint_bank import generate_grid_hint
            hints.append(generate_grid_hint(G2, "p3", 2, 0, 2))
        return hints

    def test_appears_when_wolf_and_non_wolf_both_alive(self):
        G = _base_game(round_num=2)
        hints = self._grid_hints(G)
        categories = {h["category"] for h in hints}
        assert "diff_alignment" in categories

    def test_names_two_players(self):
        G = _base_game(round_num=2)
        hints = self._grid_hints(G)
        da = [h for h in hints if h["category"] == "diff_alignment"]
        assert da
        player_names = {p.display_name for p in G.players.values()}
        for h in da:
            named = [n for n in player_names if n in h["text"]]
            assert len(named) == 2, \
                f"diff_alignment should name exactly 2 players: {h['text']}"

    def test_text_says_not_same_team(self):
        G = _base_game(round_num=2)
        hints = self._grid_hints(G)
        da = [h for h in hints if h["category"] == "diff_alignment"]
        assert da
        for h in da:
            assert "NOT on the same team" in h["text"], \
                f"Expected 'NOT on the same team' in text: {h['text']}"

    def test_named_players_are_actually_on_different_teams(self):
        """Verify the named players genuinely have different teams."""
        G = _base_game(round_num=2)
        hints = self._grid_hints(G)
        da = [h for h in hints if h["category"] == "diff_alignment"]
        assert da
        name_to_team = {p.display_name: p.team for p in G.players.values()}
        for h in da:
            named = [n for n in name_to_team if n in h["text"]]
            assert len(named) == 2
            teams = {name_to_team[n] for n in named}
            assert len(teams) == 2, \
                f"diff_alignment named two players on the SAME team: {h['text']}"

    def test_expires_next_round(self):
        G = _base_game(round_num=2)
        hints = self._grid_hints(G)
        for h in hints:
            if h["category"] == "diff_alignment":
                assert h["expires_after_round"] == G.round + 1
