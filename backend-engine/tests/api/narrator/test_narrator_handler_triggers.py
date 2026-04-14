"""
Tests that verify narrate() is triggered at the correct handler call sites.

Pattern:
  1. Mock narrate as AsyncMock so create_task captures it synchronously.
  2. Enable narrator via monkeypatching get_settings.
  3. Dispatch the relevant intent.
  4. await asyncio.sleep(0) so the event loop runs any scheduled tasks.
  5. Assert mock_narrate was called with the expected trigger_id.

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


def _narrator_settings():
    """SimpleNamespace that looks like Settings with narrator_enabled=True."""
    return SimpleNamespace(narrator_enabled=True)


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


# ── narrator disabled ─────────────────────────────────────────────────────────


class TestNarratorDisabled:
    async def test_narrator_disabled_no_task_created(self, monkeypatch):
        """With narrator_enabled=False (default), no narrate task is ever created."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        # Do NOT override get_settings → narrator_enabled=False by default

        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.LOBBY
        for p in G.players.values():
            p.role = None
            p.team = None

        await _dispatch(G, {"type": "start_game", "player_id": G.host_player_id})
        await asyncio.sleep(0)

        mock_narrate.assert_not_called()


# ── narrator trigger sites ────────────────────────────────────────────────────


class TestNarratorTriggers:
    async def test_game_start_trigger(self, monkeypatch):
        """handle_start_game fires narrate('game_start') when narrator is enabled."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_settings)

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
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_settings)

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
        """handle_phase_timeout for NIGHT fires narrate('night_close')."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_settings)

        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        # G.phase is already Phase.NIGHT from _eight_player_game

        await _dispatch(G, {"type": "phase_timeout", "phase": G.phase})
        await asyncio.sleep(0)

        triggers_fired = [call[0][0] for call in mock_narrate.call_args_list]
        assert "night_close" in triggers_fired

    async def test_player_eliminated_on_night_timeout_with_kill(self, monkeypatch):
        """When a wolf kills during night timeout, narrate('player_eliminated') fires too."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_settings)

        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        # Set wolf votes so p6 (Villager1) is killed
        G.night_actions.wolf_votes = {"p1": "p6", "p2": "p6"}

        await _dispatch(G, {"type": "phase_timeout", "phase": G.phase})
        await asyncio.sleep(0)

        triggers_fired = [call[0][0] for call in mock_narrate.call_args_list]
        assert "night_close" in triggers_fired
        assert "player_eliminated" in triggers_fired

        # Verify eliminated_name is passed for player_eliminated
        elim_call = next(c for c in mock_narrate.call_args_list if c[0][0] == "player_eliminated")
        assert elim_call[1].get("eliminated_name") == "Villager1"

    async def test_vote_open_on_day_timeout(self, monkeypatch):
        """handle_phase_timeout for DAY fires narrate('vote_open')."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_settings)

        G, _ = _eight_player_game()
        G = G.model_copy(deep=True)
        G.phase = Phase.DAY

        await _dispatch(G, {"type": "phase_timeout", "phase": G.phase})
        await asyncio.sleep(0)

        mock_narrate.assert_called_once()
        assert mock_narrate.call_args[0][0] == "vote_open"

    async def test_vote_elimination_on_day_vote(self, monkeypatch):
        """Submitting the last day vote that causes elimination fires narrate('vote_elimination')."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_settings)

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

        triggers_fired = [call[0][0] for call in mock_narrate.call_args_list]
        assert "vote_elimination" in triggers_fired

        elim_call = next(c for c in mock_narrate.call_args_list if c[0][0] == "vote_elimination")
        assert elim_call[1].get("eliminated_name") == "Villager3"

    async def test_village_wins_on_vote(self, monkeypatch):
        """Voting out the last wolf fires narrate('village_wins')."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_settings)

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

        triggers_fired = [call[0][0] for call in mock_narrate.call_args_list]
        assert "village_wins" in triggers_fired

    async def test_wolves_win_on_vote(self, monkeypatch):
        """Voting out the last villager fires narrate('wolves_win')."""
        mock_narrate = AsyncMock()
        monkeypatch.setattr("api.intents.handlers.narrate", mock_narrate)
        monkeypatch.setattr("api.intents.handlers.get_settings", _narrator_settings)

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

        triggers_fired = [call[0][0] for call in mock_narrate.call_args_list]
        assert "wolves_win" in triggers_fired
