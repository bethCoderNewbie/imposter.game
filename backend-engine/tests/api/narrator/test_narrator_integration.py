"""
Integration tests: display WebSocket receives narrate messages end-to-end.

Uses the `client` fixture (fakeredis + TestClient) so no external services needed.
LLM and TTS calls are mocked via the `narrator_mocks` fixture.

asyncio_mode = "auto" — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.helpers.game_driver import create_and_fill, drive_role_deal, send_player_intent
from tests.helpers.ws_patterns import consume_until


# ── Shared helpers ────────────────────────────────────────────────────────────


def _until_narrate(trigger: str | None = None):
    """Predicate: matches narrate messages, optionally filtered by trigger."""
    if trigger:
        return lambda m: m.get("type") == "narrate" and m.get("trigger") == trigger
    return lambda m: m.get("type") == "narrate"


def _start_game(client, n: int = 5):
    """Create, fill, and start a game. Returns (game_id, host_secret, players)."""
    game_id, host_secret, players = create_and_fill(client, n)
    r = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
    assert r.status_code == 200, r.text
    return game_id, host_secret, players


# ── narrator_mocks fixture ────────────────────────────────────────────────────


@pytest.fixture
def narrator_mocks(monkeypatch):
    """Enable narrator; mock LLM + TTS so no external services are required."""
    monkeypatch.setattr(
        "api.narrator.triggers.generate_narration",
        AsyncMock(return_value="Night falls over the village."),
    )
    monkeypatch.setattr(
        "api.narrator.triggers.synthesize",
        AsyncMock(return_value=("/tts/audio/test.wav", 2500)),
    )
    monkeypatch.setattr(
        "api.intents.handlers.get_settings",
        lambda: SimpleNamespace(narrator_enabled=True),
    )


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestNarratorIntegration:
    def test_display_receives_narrate_on_game_start(self, client, narrator_mocks):
        """Display WS receives a narrate message with trigger='game_start' after game starts."""
        game_id, host_secret, players = create_and_fill(client, n=5)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # initial LOBBY sync

            r = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
            assert r.status_code == 200

            msg = consume_until(display_ws, _until_narrate("game_start"), max_messages=30)

        assert msg["trigger"] == "game_start"
        assert msg["text"] == "Night falls over the village."
        assert msg["audio_url"] == "/tts/audio/test.wav"
        assert msg["duration_ms"] == 2500

    def test_display_receives_narrate_on_night_open(self, client, narrator_mocks):
        """Display WS receives narrate('night_open') after all players confirm their roles.

        Note: drive_role_deal() would drain and discard the narrate message because
        its consume_until looks for state.phase=='night' and skips other messages.
        Instead we confirm roles manually and drain the display WS ourselves.
        """
        game_id, host_secret, players = create_and_fill(client, n=5)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # initial LOBBY sync

            r = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
            assert r.status_code == 200

            # Confirm all roles — after the last confirm the narrate task fires
            for player in players:
                send_player_intent(client, game_id, player, {"type": "confirm_role_reveal"})

            # Drain all messages (game_start narrate, state updates, disconnects, night_open)
            msg = consume_until(display_ws, _until_narrate("night_open"), max_messages=100)

        assert msg["trigger"] == "night_open"

    def test_narrate_message_schema_complete(self, client, narrator_mocks):
        """Narrate message contains all required fields with correct types."""
        game_id, host_secret, players = create_and_fill(client, n=5)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # LOBBY sync

            r = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
            assert r.status_code == 200

            msg = consume_until(display_ws, _until_narrate(), max_messages=30)

        assert msg["type"] == "narrate"
        assert isinstance(msg["trigger"], str)
        assert isinstance(msg["text"], str) and msg["text"]
        assert isinstance(msg["audio_url"], str) and msg["audio_url"].startswith("/")
        assert isinstance(msg["duration_ms"], int) and msg["duration_ms"] > 0
        assert isinstance(msg["phase"], str)
        assert isinstance(msg["round"], int)

    def test_player_ws_does_not_receive_narrate(self, client, narrator_mocks):
        """A player's own WebSocket never receives narrate messages.

        narrate() unicasts to player_id=None (the display client) exclusively.
        A player WS connecting after game start receives only the role-deal sync.
        """
        game_id, host_secret, players = create_and_fill(client, n=5)

        # Connect display WS first so the narrate task can fire
        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # LOBBY sync
            r = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
            assert r.status_code == 200
            # Drain display WS to trigger the narrate task (ensures it has already fired)
            consume_until(display_ws, _until_narrate("game_start"), max_messages=30)

        # Now connect as a player — they receive only the ROLE_DEAL sync, no narrate
        host = players[0]
        with client.websocket_connect(
            f"/ws/{game_id}/{host['player_id']}"
        ) as player_ws:
            player_ws.send_json({"type": "auth", "session_token": host["session_token"]})
            sync_msg = player_ws.receive_json()  # ROLE_DEAL sync
            assert sync_msg.get("type") != "narrate", (
                f"Player WS unexpectedly received narrate message: {sync_msg}"
            )

    def test_narrator_disabled_no_narrate_message(self, client):
        """Without narrator_mocks, narrator_enabled=False and no narrate message is sent.

        We drain the display WS until the ROLE_DEAL state arrives (confirming the
        game started), asserting that no narrate message slips through.
        """
        game_id, host_secret, players = create_and_fill(client, n=5)

        with client.websocket_connect(f"/ws/{game_id}/display") as display_ws:
            display_ws.receive_json()  # LOBBY sync

            r = client.post(f"/api/games/{game_id}/start", json={"host_secret": host_secret})
            assert r.status_code == 200

            # Drain until ROLE_DEAL state, asserting no narrate message appears
            for _ in range(20):
                msg = display_ws.receive_json()
                assert msg.get("type") != "narrate", (
                    f"Unexpected narrate message with narrator disabled: {msg}"
                )
                if msg.get("state", {}).get("phase") == "role_deal":
                    break  # Game started successfully, no narrate seen
