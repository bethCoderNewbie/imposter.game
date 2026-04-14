"""
Tests that verify narrate() / narrate_sequence() is triggered at the correct
handler call sites.

Pattern for single-narrate sites (game_start, night_open, vote_open):
  1. Mock `narrate` as AsyncMock — create_task records the call synchronously.
  2. Enable narrator via monkeypatching get_settings.
  3. Dispatch the relevant intent.
  4. await asyncio.sleep(0) to let the event loop run scheduled tasks.
  5. Assert mock_narrate was called with the expected trigger_id.

Pattern for narrate_sequence sites (night_close+day_open, vote_elimination, etc.):
  1. Install a _SeqSpy coroutine that records the specs list explicitly.
  2. Enable narrator via monkeypatching get_settings.
  3. Dispatch and sleep.
  4. Assert the expected trigger_ids appear in the captured specs.

asyncio_mode = "auto" (see pyproject.toml) — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.intents.dispatch import dispatch_intent
from engine.setup import setup_game
from engine.state.enums import Phase, Team
from engine.state.models import NightActions
from tests.conftest import _eight_player_game, _make_player


# ── Shared helpers ────────────────────────────────────────────────────────────


class _NullCM:
    """Null connection manager — swallows all broadcasts in unit tests."""

    async def unicast(self, game_id, player_id, payload):
        pass

    async def broadcast(self, game_id, G):
        pass


class _NullRedis:
    pass


_cm = _NullCM()
_redis = _NullRedis()


async def _dispatch(G, intent):
    return await dispatch_intent(G, intent, _redis, _cm)


def _narrator_enabled():
    """SimpleNamespace that looks like Settings with narrator_enabled=True."""
    return SimpleNamespace(narrator_enabled=True)


def _narrator_disabled():
    """SimpleNamespace that looks like Settings with narrator_enabled=False."""
    return SimpleNamespace(narrator_enabled=False)


def _make_small_game(host_id: str, players_dict: dict, phase: Phase):
    """Build a minimal MasterGameState for vote tests."""
    G = setup_game("test-small-game", host_id, {})
    G = G.model_copy(deep=True)
    G.players = players_dict
    G.phase = phase
    G.host_player_id = host_id
    G.round = 1
    G.night_actions = NightActions(actions_required_count=0)
    return G


class _SeqSpy:
    """
    Async spy for narrate_sequence that records the specs list on each call.
    Used instead of AsyncMock because create_task + call_args has subtle
    timing issues with the args-capture in this codebase's test harness.
    """

    def __init__(self):
        self.calls: list[list] = []

    async def __call__(self, specs, G, cm, game_id):
        # Take a snapshot of the list so late mutations don't affect assertion
        self.calls.append(list(specs))

    @property
    def called(self) -> bool:
        return bool(self.calls)

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def all_trigger_ids(self) -> list[str]:
        """Flatten all trigger_ids across all calls."""
        return [t for call in self.calls for t, _, _ in call]

    def specs_for_call(self, call_index: int = 0) -> list:
        return self.calls[call_index]


# ── narrator disabled ─────────────────────────────────────────────────────────


class TestNarratorDisabled:
    async def test_narrator_disabled_no_task_created(self, monkeypatch):
        """With narrator_enabled=False, no narrate task is ever created."""
        mock_narrate = AsyncMock()
        mock_seq = _SeqSpy()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.narrate_sequence", mock_seq)
        # Explicitly set narrator_enabled=False — do NOT rely on the environment
        # default because the container may have NARRATOR_ENABLED=true exported.
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_disabled)

        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.LOBBY
        for p in G.players.values():
            p.role = None
            p.team = None

        await _dispatch(G, {"type": "start_game", "player_id": G.host_player_id})
        await asyncio.sleep(0)

        mock_narrate.assert_not_called()
        assert not mock_seq.called


# ── narrator trigger sites ────────────────────────────────────────────────────


class TestNarratorTriggers:
    async def test_game_start_trigger(self, monkeypatch):
        """handle_start_game fires narrate('game_start') when narrator is enabled."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_enabled)

        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.LOBBY
        for p in G.players.values():
            p.role = None
            p.team = None

        await _dispatch(G, {"type": "start_game", "player_id": G.host_player_id})
        await asyncio.sleep(0)

        mock_narrate.assert_called_once()
        assert mock_narrate.call_args[0][0] == "game_start"

    async def test_night_open_trigger_on_role_reveal(self, monkeypatch):
        """Confirming the last role reveal fires narrate('night_open')."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_enabled)

        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.ROLE_DEAL

        pids = list(G.players.keys())
        # Pre-confirm all players except the last one
        for pid in pids[:-1]:
            G.players[pid].role_confirmed = True
        last_pid = pids[-1]

        await _dispatch(G, {"type": "confirm_role_reveal", "player_id": last_pid})
        await asyncio.sleep(0)

        mock_narrate.assert_called_once()
        assert mock_narrate.call_args[0][0] == "night_open"

    async def test_night_close_on_night_timeout(self, monkeypatch):
        """handle_phase_timeout for NIGHT fires narrate_sequence with night_close + day_open."""
        spy = _SeqSpy()
        monkeypatch.setattr("api.intents.handlers.narrate_sequence", spy)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_enabled)

        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        # G.phase is already Phase.NIGHT from _eight_player_game

        await _dispatch(G, {"type": "phase_timeout", "phase": G.phase})
        await asyncio.sleep(0)

        assert spy.called, "narrate_sequence was not called for night timeout"
        trigger_ids = spy.all_trigger_ids()
        assert "night_close" in trigger_ids
        assert "day_open" in trigger_ids

    async def test_player_eliminated_on_night_timeout_with_kill(self, monkeypatch):
        """When a wolf kills during night timeout, specs include player_eliminated."""
        spy = _SeqSpy()
        monkeypatch.setattr("api.intents.handlers.narrate_sequence", spy)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_enabled)

        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        # Set wolf votes so p6 (Villager1) is killed
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}

        await _dispatch(G, {"type": "phase_timeout", "phase": G.phase})
        await asyncio.sleep(0)

        assert spy.called, "narrate_sequence was not called for night timeout with kill"
        specs = spy.specs_for_call(0)
        trigger_ids = [t for t, _, _ in specs]
        assert "night_close" in trigger_ids
        assert "player_eliminated" in trigger_ids

        elim_spec = next(s for s in specs if s[0] == "player_eliminated")
        assert elim_spec[1] == "Villager1"

    async def test_vote_open_on_day_timeout(self, monkeypatch):
        """handle_phase_timeout for DAY fires narrate('vote_open')."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_enabled)

        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY

        await _dispatch(G, {"type": "phase_timeout", "phase": G.phase})
        await asyncio.sleep(0)

        mock_narrate.assert_called_once()
        assert mock_narrate.call_args[0][0] == "vote_open"

    async def test_vote_elimination_on_day_vote(self, monkeypatch):
        """Submitting the last day vote fires narrate_sequence with vote_elimination."""
        spy = _SeqSpy()
        monkeypatch.setattr("api.intents.handlers.narrate_sequence", spy)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_enabled)

        # 4-player game: 1 wolf + 3 villagers; 3 pre-votes for p4 (Villager3)
        players = {
            "p1": _make_player("p1", "Wolf", "werewolf", Team.WEREWOLF),
            "p2": _make_player("p2", "Villager1", "villager", Team.VILLAGE),
            "p3": _make_player("p3", "Villager2", "villager", Team.VILLAGE),
            "p4": _make_player("p4", "Villager3", "villager", Team.VILLAGE),
        }
        G = _make_small_game("p2", players, Phase.DAY_VOTE)
        # Pre-populate three votes for p4 so next vote triggers auto-advance
        G.day_votes = {"p1": "p4", "p2": "p4", "p3": "p4"}
        for pid in ("p1", "p2", "p3"):
            G.players[pid].vote_target_id = "p4"

        # p4 submits the final vote → majority for p4 → elimination
        await _dispatch(G, {"type": "submit_day_vote", "player_id": "p4", "target_id": "p1"})
        await asyncio.sleep(0)

        assert spy.called, "narrate_sequence was not called after vote elimination"
        specs = spy.specs_for_call(0)
        trigger_ids = [t for t, _, _ in specs]
        assert "vote_elimination" in trigger_ids

        elim_spec = next(s for s in specs if s[0] == "vote_elimination")
        assert elim_spec[1] == "Villager3"

    async def test_village_wins_on_vote(self, monkeypatch):
        """Voting out the last wolf fires narrate_sequence with village_wins."""
        spy = _SeqSpy()
        monkeypatch.setattr("api.intents.handlers.narrate_sequence", spy)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_enabled)

        # 3-player game: 1 wolf + 2 villagers; villagers have pre-voted for wolf
        players = {
            "p1": _make_player("p1", "Wolf", "werewolf", Team.WEREWOLF),
            "p2": _make_player("p2", "Villager1", "villager", Team.VILLAGE),
            "p3": _make_player("p3", "Villager2", "villager", Team.VILLAGE),
        }
        G = _make_small_game("p2", players, Phase.DAY_VOTE)
        # p2 and p3 pre-voted for p1 (the wolf)
        G.day_votes = {"p2": "p1", "p3": "p1"}
        G.players["p2"].vote_target_id = "p1"
        G.players["p3"].vote_target_id = "p1"

        # p1 (wolf) casts final vote → p1 has 2 votes, p2 has 1 → p1 eliminated → village wins
        await _dispatch(G, {"type": "submit_day_vote", "player_id": "p1", "target_id": "p2"})
        await asyncio.sleep(0)

        assert spy.called, "narrate_sequence was not called after village wins"
        trigger_ids = spy.all_trigger_ids()
        assert "village_wins" in trigger_ids

    async def test_wolves_win_on_vote(self, monkeypatch):
        """Voting out the last villager fires narrate_sequence with wolves_win."""
        spy = _SeqSpy()
        monkeypatch.setattr("api.intents.handlers.narrate_sequence", spy)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_enabled)

        # 3-player game: 2 wolves + 1 villager; wolves pre-voted for villager
        players = {
            "p1": _make_player("p1", "Wolf1", "werewolf", Team.WEREWOLF),
            "p2": _make_player("p2", "Wolf2", "werewolf", Team.WEREWOLF),
            "p3": _make_player("p3", "Villager", "villager", Team.VILLAGE),
        }
        G = _make_small_game("p1", players, Phase.DAY_VOTE)
        # p1 and p2 pre-voted for p3 (the villager)
        G.day_votes = {"p1": "p3", "p2": "p3"}
        G.players["p1"].vote_target_id = "p3"
        G.players["p2"].vote_target_id = "p3"

        # p3 (villager) casts final vote → p3 has 2 votes → eliminated → wolves win
        await _dispatch(G, {"type": "submit_day_vote", "player_id": "p3", "target_id": "p1"})
        await asyncio.sleep(0)

        assert spy.called, "narrate_sequence was not called after wolves win"
        trigger_ids = spy.all_trigger_ids()
        assert "wolves_win" in trigger_ids
