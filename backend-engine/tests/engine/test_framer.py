"""
Framer integration tests — false hint delivery pipeline (ADR-002).

Covers:
  - hack_archives queues false hint when payload is present
  - hack_archives is a no-op when payload is missing (defensive guard)
  - Roleblocked framer fires neither path
  - frame action sets is_framed_tonight on target
  - strip_fabricated_flag removes is_fabricated from a typed FalseHintPayload
"""

from __future__ import annotations

import pytest

from engine.resolver.night import _step2_framer
from engine.state.enums import Team
from engine.state.models import FalseHintPayload, NightActions
from engine.stripper import strip_fabricated_flag
from tests.conftest import _eight_player_game


def _game_with_framer():
    """8-player game with p1 set to framer (wolf team)."""
    G, _ = _eight_player_game()
    G = G.model_copy(deep=True)
    G.players["p1"].role = "framer"
    G.players["p1"].team = Team.WEREWOLF
    return G


def _sample_payload(round_: int = 1) -> FalseHintPayload:
    return FalseHintPayload(
        hint_id="test-hint-uuid",
        category="role_present",
        text="There is NO Seer in this game.",
        round=round_,
    )


# ── hack_archives path ──────────────────────────────────────────────────────────

class TestHackArchives:
    def test_queues_false_hint_when_payload_present(self):
        G = _game_with_framer()
        G.night_actions.framer_action = "hack_archives"
        G.night_actions.false_hint_payload = _sample_payload()

        G2 = _step2_framer(G)

        assert G2.night_actions.false_hint_queued is True

    def test_no_op_when_payload_missing(self):
        """Defensive guard: missing payload must not set the queue flag."""
        G = _game_with_framer()
        G.night_actions.framer_action = "hack_archives"
        G.night_actions.false_hint_payload = None

        G2 = _step2_framer(G)

        assert G2.night_actions.false_hint_queued is False

    def test_roleblocked_framer_does_not_queue(self):
        G = _game_with_framer()
        G.night_actions.framer_action = "hack_archives"
        G.night_actions.false_hint_payload = _sample_payload()
        G.night_actions.roleblocked_player_id = "p1"  # framer is hexed

        G2 = _step2_framer(G)

        assert G2.night_actions.false_hint_queued is False

    def test_payload_round_preserved(self):
        G = _game_with_framer()
        G.night_actions.framer_action = "hack_archives"
        G.night_actions.false_hint_payload = _sample_payload(round_=3)

        G2 = _step2_framer(G)

        assert G2.night_actions.false_hint_payload.round == 3


# ── frame path ──────────────────────────────────────────────────────────────────

class TestFrameAction:
    def test_frame_sets_is_framed_tonight(self):
        G = _game_with_framer()
        G.night_actions.framer_action = "frame"
        G.night_actions.framer_target_id = "p3"  # seer

        G2 = _step2_framer(G)

        assert G2.players["p3"].is_framed_tonight is True

    def test_frame_does_not_set_false_hint_queued(self):
        G = _game_with_framer()
        G.night_actions.framer_action = "frame"
        G.night_actions.framer_target_id = "p3"

        G2 = _step2_framer(G)

        assert G2.night_actions.false_hint_queued is False

    def test_roleblocked_framer_does_not_frame(self):
        G = _game_with_framer()
        G.night_actions.framer_action = "frame"
        G.night_actions.framer_target_id = "p3"
        G.night_actions.roleblocked_player_id = "p1"

        G2 = _step2_framer(G)

        assert G2.players["p3"].is_framed_tonight is False


# ── strip_fabricated_flag ───────────────────────────────────────────────────────

class TestStripFabricatedFlagWithModel:
    def test_removes_is_fabricated(self):
        payload = _sample_payload()
        result = strip_fabricated_flag(payload.model_dump(mode="json"))
        assert "is_fabricated" not in result

    def test_preserves_all_other_fields(self):
        payload = _sample_payload()
        result = strip_fabricated_flag(payload.model_dump(mode="json"))
        assert result["hint_id"] == "test-hint-uuid"
        assert result["category"] == "role_present"
        assert result["text"] == "There is NO Seer in this game."
        assert result["round"] == 1
        assert result["expires_after_round"] is None
