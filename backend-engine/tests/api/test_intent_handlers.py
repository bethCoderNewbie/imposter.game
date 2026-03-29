"""
Intent handler tests — validation guards, phase checks, business rule enforcement.
"""

from __future__ import annotations

import pytest

from api.intents.dispatch import IntentError, dispatch_intent
from engine.phases.machine import transition_phase
from engine.state.enums import Phase, Team
from tests.conftest import _eight_player_game, _make_player


class _NullCM:
    """Null connection manager — swallows all broadcasts in unit tests."""
    async def unicast(self, game_id, player_id, payload): ...
    async def broadcast(self, game_id, G): ...


class _NullRedis:
    """Null redis — unit tests don't need storage."""


_cm = _NullCM()
_redis = _NullRedis()


async def _dispatch(G, intent):
    return await dispatch_intent(G, intent, _redis, _cm)


# ── Phase guards ──────────────────────────────────────────────────────────────

class TestPhaseGuards:
    @pytest.mark.asyncio
    async def test_wrong_phase_rejected(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.LOBBY  # Not DAY_VOTE
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {"type": "submit_day_vote", "player_id": "p3", "target_id": "p1"})
        assert exc.value.code == "WRONG_PHASE"

    @pytest.mark.asyncio
    async def test_night_action_in_day_rejected(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {"type": "submit_night_action", "player_id": "p3", "target_id": "p1"})
        assert exc.value.code == "WRONG_PHASE"


# ── Dead player guard ─────────────────────────────────────────────────────────

class TestDeadPlayerGuard:
    @pytest.mark.asyncio
    async def test_dead_player_action_rejected(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.players["p3"].is_alive = False
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "submit_night_action",
                "player_id": "p3",
                "target_id": "p1",
            })
        assert exc.value.code == "DEAD_PLAYER_ACTION"

    @pytest.mark.asyncio
    async def test_dead_player_day_vote_rejected(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        G.players["p3"].is_alive = False
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "submit_day_vote",
                "player_id": "p3",
                "target_id": "p1",
            })
        assert exc.value.code == "DEAD_PLAYER_ACTION"


# ── Stale state_id ────────────────────────────────────────────────────────────

class TestStaleStateId:
    """state_id fence is enforced in the game_queue run_loop, not the handler.
    Handler tests verify the intent payload is processed correctly when state_id matches."""

    @pytest.mark.asyncio
    async def test_valid_intent_accepted(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.night_actions.actions_required_count = 3
        G_new = await _dispatch(G, {
            "type": "submit_night_action",
            "player_id": "p3",  # seer
            "target_id": "p1",
        })
        assert G_new.players["p3"].night_action_submitted


# ── Duplicate night action ────────────────────────────────────────────────────

class TestDuplicateNightAction:
    @pytest.mark.asyncio
    async def test_duplicate_night_action_rejected(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.players["p3"].night_action_submitted = True
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "submit_night_action",
                "player_id": "p3",
                "target_id": "p1",
            })
        assert exc.value.code == "DUPLICATE_ACTION"


# ── Consecutive protect ───────────────────────────────────────────────────────

class TestConsecutiveProtect:
    @pytest.mark.asyncio
    async def test_consecutive_protect_rejected(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.players["p4"].last_protected_player_id = "p3"  # doctor protected p3 last round
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "submit_night_action",
                "player_id": "p4",  # doctor
                "target_id": "p3",  # same target
            })
        assert exc.value.code == "CONSECUTIVE_PROTECT_FORBIDDEN"


# ── Self-target ───────────────────────────────────────────────────────────────

class TestSelfTarget:
    @pytest.mark.asyncio
    async def test_seer_cannot_inspect_self(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "submit_night_action",
                "player_id": "p3",  # seer
                "target_id": "p3",  # self
            })
        assert exc.value.code == "SELF_TARGET"

    @pytest.mark.asyncio
    async def test_day_vote_self_not_allowed(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY_VOTE
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "submit_day_vote",
                "player_id": "p3",
                "target_id": "p3",
            })
        assert exc.value.code == "SELF_VOTE_NOT_ALLOWED"


# ── Host-only actions ─────────────────────────────────────────────────────────

class TestHostOnlyActions:
    @pytest.mark.asyncio
    async def test_non_host_cannot_start_game(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.LOBBY
        # Add enough players
        for i in range(9, 14):
            G.players[f"p{i}"] = _make_player(f"p{i}", f"Player{i}", "villager", Team.VILLAGE)
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "start_game",
                "player_id": "p3",  # not host
            })
        assert exc.value.code == "NOT_HOST"

    @pytest.mark.asyncio
    async def test_non_host_cannot_advance_phase(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "advance_phase",
                "player_id": "p3",  # not host (p1 is host)
            })
        assert exc.value.code == "NOT_HOST"


# ── Wolf team restrictions ────────────────────────────────────────────────────

class TestWolfRestrictions:
    @pytest.mark.asyncio
    async def test_wolf_cannot_vote_to_kill_teammate(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "submit_night_action",
                "player_id": "p1",  # wolf
                "target_id": "p2",  # fellow wolf
            })
        assert exc.value.code == "INVALID_TARGET"


# ── Unknown intent ────────────────────────────────────────────────────────────

class TestUnknownIntent:
    @pytest.mark.asyncio
    async def test_unknown_intent_raises_error(self):
        G, _ = _eight_player_game()
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {"type": "do_something_weird", "player_id": "p1"})
        assert exc.value.code == "UNKNOWN_INTENT"


# ── ADR-011: new role intents and hunter_revenge ───────────────────────────────

class TestADR011NightIntents:
    """Covers the four new role UIs and hunter_revenge added in ADR-011."""

    @pytest.mark.asyncio
    async def test_tracker_submit_night_action(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.night_actions.actions_required_count = 5  # prevent auto-advance
        # p5 is already the tracker in _eight_player_game
        G_new = await _dispatch(G, {
            "type": "submit_night_action",
            "player_id": "p5",  # tracker
            "target_id": "p1",
        })
        assert G_new.players["p5"].night_action_submitted is True
        assert G_new.night_actions.tracker_target_id == "p1"

    @pytest.mark.asyncio
    async def test_tracker_cannot_track_self(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "submit_night_action",
                "player_id": "p5",  # tracker
                "target_id": "p5",
            })
        assert exc.value.code == "SELF_TARGET"

    @pytest.mark.asyncio
    async def test_serial_killer_submit_night_action(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.night_actions.actions_required_count = 5
        G.players["p5"] = _make_player("p5", "SK", "serial_killer", Team.NEUTRAL)
        G_new = await _dispatch(G, {
            "type": "submit_night_action",
            "player_id": "p5",  # serial_killer
            "target_id": "p3",
        })
        assert G_new.players["p5"].night_action_submitted is True

    @pytest.mark.asyncio
    async def test_cupid_submit_night_action_round_1(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.round = 1
        G.night_actions.actions_required_count = 5
        G.players["p5"] = _make_player("p5", "Cupid", "cupid", Team.VILLAGE)
        G_new = await _dispatch(G, {
            "type": "submit_night_action",
            "player_id": "p5",  # cupid
            "link_target_a": "p3",
            "link_target_b": "p4",
        })
        assert G_new.players["p5"].night_action_submitted is True
        assert G_new.night_actions.cupid_link == ["p3", "p4"]

    @pytest.mark.asyncio
    async def test_cupid_link_targets_must_differ(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.round = 1
        G.players["p5"] = _make_player("p5", "Cupid", "cupid", Team.VILLAGE)
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "submit_night_action",
                "player_id": "p5",
                "link_target_a": "p3",
                "link_target_b": "p3",  # same as A
            })
        assert exc.value.code == "INVALID_TARGET"

    @pytest.mark.asyncio
    async def test_arsonist_douse_action(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.night_actions.actions_required_count = 5
        G.players["p5"] = _make_player("p5", "Arsonist", "arsonist", Team.NEUTRAL)
        G_new = await _dispatch(G, {
            "type": "submit_night_action",
            "player_id": "p5",  # arsonist
            "arsonist_action": "douse",
            "target_id": "p3",
        })
        assert G_new.players["p5"].night_action_submitted is True
        assert G_new.night_actions.arsonist_douse_target_id == "p3"

    @pytest.mark.asyncio
    async def test_arsonist_ignite_action(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.night_actions.actions_required_count = 5
        G.players["p5"] = _make_player("p5", "Arsonist", "arsonist", Team.NEUTRAL)
        G.players["p5"].doused_player_ids = ["p3"]  # p3 already doused
        G_new = await _dispatch(G, {
            "type": "submit_night_action",
            "player_id": "p5",
            "arsonist_action": "ignite",
        })
        assert G_new.players["p5"].night_action_submitted is True

    @pytest.mark.asyncio
    async def test_arsonist_ignite_requires_doused_players(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT
        G.players["p5"] = _make_player("p5", "Arsonist", "arsonist", Team.NEUTRAL)
        # doused_player_ids is empty (default)
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "submit_night_action",
                "player_id": "p5",
                "arsonist_action": "ignite",
            })
        assert exc.value.code == "NO_DOUSED_PLAYERS"

    @pytest.mark.asyncio
    async def test_hunter_revenge_eliminates_target(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.HUNTER_PENDING
        # Promote p5 to hunter (dead, pending revenge)
        G.players["p5"] = _make_player("p5", "Hunter", "hunter", Team.VILLAGE, alive=False)
        G.hunter_queue = ["p5"]
        G_new = await _dispatch(G, {
            "type": "hunter_revenge",
            "player_id": "p5",
            "target_id": "p3",
        })
        assert G_new.players["p3"].is_alive is False
        assert "p5" not in G_new.hunter_queue

    @pytest.mark.asyncio
    async def test_hunter_revenge_wrong_phase_rejected(self):
        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.NIGHT  # Not HUNTER_PENDING
        with pytest.raises(IntentError) as exc:
            await _dispatch(G, {
                "type": "hunter_revenge",
                "player_id": "p5",
                "target_id": "p3",
            })
        assert exc.value.code == "WRONG_PHASE"
