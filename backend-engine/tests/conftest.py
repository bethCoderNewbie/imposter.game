"""
Shared pytest fixtures for all Werewolf backend tests.
"""

from __future__ import annotations

import pytest

from engine.setup import setup_game
from engine.state.enums import Phase, Team
from engine.state.models import MasterGameState, NightActions, PlayerState


def _make_player(pid: str, name: str, role: str, team: Team, alive: bool = True) -> PlayerState:
    p = PlayerState(player_id=pid, display_name=name, avatar_id="default_01")
    p.role = role
    p.team = team
    p.is_alive = alive
    return p


def _eight_player_game() -> tuple[MasterGameState, dict[str, str]]:
    """
    Returns (G, role_map) for an 8-player game with known roles:
      wolf1, wolf2, seer1, doctor1, tracker1, villager1, villager2, villager3
    """
    pids = {
        "wolf1": "p1",
        "wolf2": "p2",
        "seer1": "p3",
        "doctor1": "p4",
        "tracker1": "p5",
        "villager1": "p6",
        "villager2": "p7",
        "villager3": "p8",
    }
    G = setup_game("test-game-8", "p1", {})
    G = G.model_copy(deep=True)
    G.players = {
        "p1": _make_player("p1", "Wolf1", "werewolf", Team.WEREWOLF),
        "p2": _make_player("p2", "Wolf2", "werewolf", Team.WEREWOLF),
        "p3": _make_player("p3", "Seer", "seer", Team.VILLAGE),
        "p4": _make_player("p4", "Doctor", "doctor", Team.VILLAGE),
        "p5": _make_player("p5", "Tracker", "tracker", Team.VILLAGE),
        "p6": _make_player("p6", "Villager1", "villager", Team.VILLAGE),
        "p7": _make_player("p7", "Villager2", "villager", Team.VILLAGE),
        "p8": _make_player("p8", "Villager3", "villager", Team.VILLAGE),
    }
    G.phase = Phase.NIGHT
    G.round = 1
    G.host_player_id = "p1"
    G.night_actions = NightActions(actions_required_count=3)  # seer, doctor, tracker
    return G, pids


def _five_player_game() -> tuple[MasterGameState, dict[str, str]]:
    """
    Returns (G, role_map) for a 5-player game with known roles:
      wolf1, seer1, doctor1, villager1, villager2
    """
    G = setup_game("test-game-5", "p1", {})
    G = G.model_copy(deep=True)
    G.players = {
        "p1": _make_player("p1", "Wolf", "werewolf", Team.WEREWOLF),
        "p2": _make_player("p2", "Seer", "seer", Team.VILLAGE),
        "p3": _make_player("p3", "Doctor", "doctor", Team.VILLAGE),
        "p4": _make_player("p4", "Villager1", "villager", Team.VILLAGE),
        "p5": _make_player("p5", "Villager2", "villager", Team.VILLAGE),
    }
    G.phase = Phase.NIGHT
    G.round = 1
    G.host_player_id = "p1"
    G.night_actions = NightActions(actions_required_count=2)  # seer, doctor
    return G, {}


@pytest.fixture
def eight_player_game() -> tuple[MasterGameState, dict[str, str]]:
    return _eight_player_game()


@pytest.fixture
def five_player_game() -> tuple[MasterGameState, dict[str, str]]:
    return _five_player_game()


@pytest.fixture
def wolf_pid(eight_player_game) -> str:
    G, _ = eight_player_game
    return "p1"


@pytest.fixture
def seer_pid(eight_player_game) -> str:
    G, _ = eight_player_game
    return "p3"
