"""
Integration tests for host-only timer control intents:
  pause_timer · resume_timer · extend_timer · force_next

All tests use fakeredis via the `client` fixture.
The host is always players[0] (create_and_fill convention).
Intents are sent via send_player_intent (opens player WS, sends, closes).
"""

from __future__ import annotations

import pytest

from tests.helpers.game_driver import (
    create_and_fill,
    drive_night,
    drive_role_deal,
    send_player_intent,
)
from tests.helpers.role_utils import collect_role_map, first_with_role, players_with_role
from tests.helpers.ws_patterns import assert_phase, consume_until, until_phase


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _start_game(client, n=5):
    game_id, host_secret, players = create_and_fill(client, n)
    r = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
    assert r.status_code == 200, r.text
    return game_id, host_secret, players


def _advance_to_night(client, game_id, players):
    """Drive ROLE_DEAL → NIGHT via display WS. Returns display WS message."""
    role_map = collect_role_map(client, game_id, players)
    with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
        display_ws.receive_json()  # sync
        drive_role_deal(client, game_id, players, display_ws)
    return role_map


def _get_state_in_night(client, game_id, players):
    """Returns (role_map, state_dict) after advancing to NIGHT."""
    role_map = _advance_to_night(client, game_id, players)
    with client.websocket_connect(f"/ws/{game_id}/display") as ws:
        msg = ws.receive_json()
    assert msg["state"]["phase"] == "night"
    return role_map, msg["state"]


def _host_intent(players, intent_type):
    return {"type": intent_type}  # player_id added by send_player_intent


# ── TestPauseTimer ─────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestPauseTimer:

    def test_pause_timer_in_night(self, client):
        """pause_timer in NIGHT sets timer_paused=True and clears timer_ends_at."""
        game_id, host_secret, players = _start_game(client)
        _advance_to_night(client, game_id, players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync

            send_player_intent(client, game_id, players[0], {"type": "pause_timer"})

            msg = consume_until(
                display_ws,
                lambda m: m.get("state", {}).get("timer_paused") is True,
                max_messages=15,
            )

        assert msg["state"]["timer_paused"] is True
        assert msg["state"]["timer_ends_at"] is None
        assert msg["state"]["timer_remaining_seconds"] is not None

    def test_pause_already_paused_returns_error(self, client):
        """Sending pause_timer twice returns ALREADY_PAUSED."""
        game_id, host_secret, players = _start_game(client)
        _advance_to_night(client, game_id, players)

        send_player_intent(client, game_id, players[0], {"type": "pause_timer"})

        with client.websocket_connect(f"/ws/{game_id}/{players[0]['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": players[0]["session_token"]})
            ws.receive_json()  # sync
            ws.send_json({"type": "pause_timer"})
            resp = ws.receive_json()

        assert resp.get("code") == "ALREADY_PAUSED"

    def test_non_host_pause_returns_not_host(self, client):
        """Non-host sending pause_timer returns NOT_HOST."""
        game_id, host_secret, players = _start_game(client)
        _advance_to_night(client, game_id, players)

        non_host = players[1]
        with client.websocket_connect(f"/ws/{game_id}/{non_host['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": non_host["session_token"]})
            ws.receive_json()
            ws.send_json({"type": "pause_timer"})
            resp = ws.receive_json()

        assert resp.get("code") == "NOT_HOST"

    def test_pause_in_lobby_returns_wrong_phase(self, client):
        """pause_timer in LOBBY phase returns WRONG_PHASE."""
        game_id, host_secret, players = create_and_fill(client)
        # Game not started — still in LOBBY

        with client.websocket_connect(f"/ws/{game_id}/{players[0]['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": players[0]["session_token"]})
            ws.receive_json()
            ws.send_json({"type": "pause_timer"})
            resp = ws.receive_json()

        assert resp.get("code") == "WRONG_PHASE"


# ── TestResumeTimer ────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestResumeTimer:

    def test_resume_timer_restores_countdown(self, client):
        """pause then resume → timer_paused=False, timer_ends_at non-null."""
        game_id, host_secret, players = _start_game(client)
        _advance_to_night(client, game_id, players)

        send_player_intent(client, game_id, players[0], {"type": "pause_timer"})

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync (paused state)

            send_player_intent(client, game_id, players[0], {"type": "resume_timer"})

            msg = consume_until(
                display_ws,
                lambda m: m.get("state", {}).get("timer_paused") is False
                          and m.get("state", {}).get("timer_ends_at") is not None,
                max_messages=15,
            )

        assert msg["state"]["timer_paused"] is False
        assert msg["state"]["timer_ends_at"] is not None
        assert msg["state"]["timer_remaining_seconds"] is None

    def test_resume_not_paused_returns_error(self, client):
        """resume_timer when not paused returns NOT_PAUSED."""
        game_id, host_secret, players = _start_game(client)
        _advance_to_night(client, game_id, players)

        with client.websocket_connect(f"/ws/{game_id}/{players[0]['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": players[0]["session_token"]})
            ws.receive_json()
            ws.send_json({"type": "resume_timer"})
            resp = ws.receive_json()

        assert resp.get("code") == "NOT_PAUSED"


# ── TestExtendTimer ────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestExtendTimer:

    def test_extend_timer_live(self, client):
        """extend_timer on a live timer pushes timer_ends_at forward by ≥30s."""
        game_id, host_secret, players = _start_game(client)
        _advance_to_night(client, game_id, players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            sync = display_ws.receive_json()
            before = sync["state"]["timer_ends_at"]

            send_player_intent(client, game_id, players[0], {"type": "extend_timer"})

            msg = consume_until(
                display_ws,
                lambda m: m.get("state", {}).get("timer_ends_at") is not None
                          and m.get("state", {}).get("timer_ends_at") != before,
                max_messages=15,
            )

        from datetime import datetime, timezone
        t_before = datetime.fromisoformat(before.replace("Z", "+00:00"))
        t_after = datetime.fromisoformat(msg["state"]["timer_ends_at"].replace("Z", "+00:00"))
        assert (t_after - t_before).total_seconds() >= 29  # ≥30s (allow 1s tolerance)

    def test_extend_timer_while_paused(self, client):
        """extend_timer while paused adds 30s to timer_remaining_seconds."""
        game_id, host_secret, players = _start_game(client)
        _advance_to_night(client, game_id, players)

        send_player_intent(client, game_id, players[0], {"type": "pause_timer"})

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            sync = display_ws.receive_json()
            remaining_before = sync["state"]["timer_remaining_seconds"]

            send_player_intent(client, game_id, players[0], {"type": "extend_timer"})

            msg = consume_until(
                display_ws,
                lambda m: (m.get("state", {}).get("timer_remaining_seconds") or 0)
                          > (remaining_before or 0),
                max_messages=15,
            )

        assert msg["state"]["timer_remaining_seconds"] >= (remaining_before or 0) + 29


# ── TestForceNext ──────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestForceNext:

    def test_force_next_night_advances_phase(self, client):
        """force_next in NIGHT immediately resolves night and advances phase."""
        game_id, host_secret, players = _start_game(client)
        _advance_to_night(client, game_id, players)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync

            send_player_intent(client, game_id, players[0], {"type": "force_next"})

            msg = consume_until(
                display_ws,
                lambda m: m.get("state", {}).get("phase") in ("day", "hunter_pending", "game_over"),
                max_messages=20,
            )

        assert msg["state"]["phase"] in ("day", "hunter_pending", "game_over")

    def test_force_next_role_deal_advances_to_night(self, client):
        """force_next in ROLE_DEAL advances to NIGHT."""
        game_id, host_secret, players = _start_game(client)
        collect_role_map(client, game_id, players)  # consume disconnect noise

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync (ROLE_DEAL)

            send_player_intent(client, game_id, players[0], {"type": "force_next"})

            msg = consume_until(display_ws, until_phase("night"), max_messages=20)

        assert_phase(msg, "night")

    def test_force_next_day_returns_use_advance_phase(self, client):
        """force_next in DAY phase returns USE_ADVANCE_PHASE error."""
        game_id, host_secret, players = _start_game(client)
        role_map = collect_role_map(client, game_id, players)
        wolf = first_with_role(role_map, "werewolf", players)
        villagers = players_with_role(role_map, "villager", players)
        seer = first_with_role(role_map, "seer", players)
        kill_target = villagers[0] if villagers else seer

        night_acts = {}
        if wolf:
            night_acts[wolf["player_id"]] = {
                "type": "submit_night_action",
                "target_id": kill_target["player_id"],
            }
        doctor = first_with_role(role_map, "doctor", players)
        if doctor and seer:
            night_acts[doctor["player_id"]] = {
                "type": "submit_night_action",
                "target_id": seer["player_id"],
            }
        if seer and wolf:
            night_acts[seer["player_id"]] = {
                "type": "submit_night_action",
                "target_id": wolf["player_id"],
            }

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()
            drive_role_deal(client, game_id, players, display_ws)
            drive_night(client, game_id, players, display_ws, night_acts)
            # Now in DAY

        with client.websocket_connect(f"/ws/{game_id}/{players[0]['player_id']}") as ws:
            ws.send_json({"type": "auth", "session_token": players[0]["session_token"]})
            ws.receive_json()
            ws.send_json({"type": "force_next"})
            resp = ws.receive_json()

        assert resp.get("code") == "USE_ADVANCE_PHASE"

    def test_force_next_clears_pause_state(self, client):
        """force_next after pause clears timer_paused on the resulting state."""
        game_id, host_secret, players = _start_game(client)
        _advance_to_night(client, game_id, players)

        send_player_intent(client, game_id, players[0], {"type": "pause_timer"})

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # sync (paused)

            send_player_intent(client, game_id, players[0], {"type": "force_next"})

            msg = consume_until(
                display_ws,
                lambda m: m.get("state", {}).get("phase") in ("day", "hunter_pending", "game_over"),
                max_messages=20,
            )

        assert msg["state"].get("timer_paused") is False
        assert msg["state"].get("timer_remaining_seconds") is None
