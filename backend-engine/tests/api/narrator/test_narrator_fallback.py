"""
Unit tests for the fallback logic and new behaviour in api.narrator.triggers:

- narrate() return type (int / 0 instead of None)
- NARRATOR_MODE: auto / static / live
- narrate_sequence() ordering and inter-trigger sleep

All external I/O and the DB session are fully mocked.
asyncio_mode = "auto" (see pyproject.toml) — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from tests.conftest import _five_player_game


# ── Shared helpers ────────────────────────────────────────────────────────────


class _TrackingCM:
    """Connection manager that records unicast calls."""

    def __init__(self):
        self.unicast_calls: list[tuple] = []

    async def unicast(self, game_id, player_id, payload):
        self.unicast_calls.append((game_id, player_id, payload))

    async def broadcast(self, game_id, G):
        pass


def _settings(mode: str = "auto"):
    return SimpleNamespace(narrator_mode=mode)


# ── Return type ───────────────────────────────────────────────────────────────


class TestNarrateReturnValue:
    async def test_returns_duration_ms_on_success(self, monkeypatch):
        from api.narrator.triggers import narrate

        G, _ = _five_player_game()
        cm = _TrackingCM()

        monkeypatch.setattr(
            "api.narrator.triggers.get_narrator_settings", lambda: _settings("auto")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration",
            AsyncMock(return_value="The wolf prowls!"),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.synthesize",
            AsyncMock(return_value=("/tts/audio/x.wav", 3500)),
        )

        result = await narrate("night_open", G, cm, "test-game")

        assert result == 3500

    async def test_returns_0_when_both_sources_empty(self, monkeypatch):
        from api.narrator.triggers import narrate

        G, _ = _five_player_game()
        cm = _TrackingCM()

        monkeypatch.setattr(
            "api.narrator.triggers.get_narrator_settings", lambda: _settings("auto")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration", AsyncMock(return_value="")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.get_preset_script", AsyncMock(return_value="")
        )

        result = await narrate("night_open", G, cm, "test-game")

        assert result == 0

    async def test_returns_0_on_tts_exception(self, monkeypatch):
        import httpx

        from api.narrator.triggers import narrate

        G, _ = _five_player_game()
        cm = _TrackingCM()

        monkeypatch.setattr(
            "api.narrator.triggers.get_narrator_settings", lambda: _settings("auto")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration",
            AsyncMock(return_value="Some text"),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.synthesize",
            AsyncMock(side_effect=httpx.ConnectError("refused")),
        )

        result = await narrate("night_open", G, cm, "test-game")

        assert result == 0


# ── auto mode ─────────────────────────────────────────────────────────────────


class TestNarrateModeAuto:
    async def test_uses_llm_text_when_llm_succeeds(self, monkeypatch):
        """LLM returns text → DB never queried."""
        from api.narrator.triggers import narrate

        G, _ = _five_player_game()
        cm = _TrackingCM()
        mock_db = AsyncMock(return_value="DB text")

        monkeypatch.setattr(
            "api.narrator.triggers.get_narrator_settings", lambda: _settings("auto")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration",
            AsyncMock(return_value="LLM text"),
        )
        monkeypatch.setattr("api.narrator.triggers.get_preset_script", mock_db)
        monkeypatch.setattr(
            "api.narrator.triggers.synthesize",
            AsyncMock(return_value=("/tts/audio/x.wav", 1000)),
        )

        await narrate("game_start", G, cm, "test-game")

        mock_db.assert_not_called()
        _, _, payload = cm.unicast_calls[0]
        assert payload["text"] == "LLM text"

    async def test_falls_back_to_db_when_llm_returns_empty(self, monkeypatch):
        """LLM returns '' → DB preset is used."""
        from api.narrator.triggers import narrate

        G, _ = _five_player_game()
        cm = _TrackingCM()

        monkeypatch.setattr(
            "api.narrator.triggers.get_narrator_settings", lambda: _settings("auto")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration", AsyncMock(return_value="")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.get_preset_script",
            AsyncMock(return_value="DB preset text"),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.synthesize",
            AsyncMock(return_value=("/tts/audio/x.wav", 1000)),
        )

        result = await narrate("game_start", G, cm, "test-game")

        assert result == 1000
        _, _, payload = cm.unicast_calls[0]
        assert payload["text"] == "DB preset text"

    async def test_returns_0_when_both_llm_and_db_empty(self, monkeypatch):
        from api.narrator.triggers import narrate

        G, _ = _five_player_game()
        cm = _TrackingCM()
        mock_synth = AsyncMock(return_value=("/tts/audio/x.wav", 1000))

        monkeypatch.setattr(
            "api.narrator.triggers.get_narrator_settings", lambda: _settings("auto")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration", AsyncMock(return_value="")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.get_preset_script", AsyncMock(return_value="")
        )
        monkeypatch.setattr("api.narrator.triggers.synthesize", mock_synth)

        result = await narrate("game_start", G, cm, "test-game")

        assert result == 0
        mock_synth.assert_not_called()


# ── live mode ─────────────────────────────────────────────────────────────────


class TestNarrateModeLive:
    async def test_uses_llm_and_does_not_query_db_on_empty(self, monkeypatch):
        """live mode: if LLM returns empty, DB is NOT queried and result is 0."""
        from api.narrator.triggers import narrate

        G, _ = _five_player_game()
        cm = _TrackingCM()
        mock_db = AsyncMock(return_value="DB text")
        mock_synth = AsyncMock(return_value=("/tts/audio/x.wav", 1000))

        monkeypatch.setattr(
            "api.narrator.triggers.get_narrator_settings", lambda: _settings("live")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration", AsyncMock(return_value="")
        )
        monkeypatch.setattr("api.narrator.triggers.get_preset_script", mock_db)
        monkeypatch.setattr("api.narrator.triggers.synthesize", mock_synth)

        result = await narrate("game_start", G, cm, "test-game")

        mock_db.assert_not_called()
        mock_synth.assert_not_called()
        assert result == 0

    async def test_uses_llm_text_when_available(self, monkeypatch):
        from api.narrator.triggers import narrate

        G, _ = _five_player_game()
        cm = _TrackingCM()

        monkeypatch.setattr(
            "api.narrator.triggers.get_narrator_settings", lambda: _settings("live")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration",
            AsyncMock(return_value="Live LLM text"),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.get_preset_script",
            AsyncMock(return_value="Should not appear"),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.synthesize",
            AsyncMock(return_value=("/tts/audio/x.wav", 2000)),
        )

        result = await narrate("night_open", G, cm, "test-game")

        assert result == 2000
        _, _, payload = cm.unicast_calls[0]
        assert payload["text"] == "Live LLM text"


# ── static mode ───────────────────────────────────────────────────────────────


class TestNarrateModelStatic:
    async def test_skips_llm_and_uses_db(self, monkeypatch):
        """static mode: generate_narration is never called."""
        from api.narrator.triggers import narrate

        G, _ = _five_player_game()
        cm = _TrackingCM()
        mock_llm = AsyncMock(return_value="Should not be called")

        monkeypatch.setattr(
            "api.narrator.triggers.get_narrator_settings", lambda: _settings("static")
        )
        monkeypatch.setattr("api.narrator.triggers.generate_narration", mock_llm)
        monkeypatch.setattr(
            "api.narrator.triggers.get_preset_script",
            AsyncMock(return_value="Static preset"),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.synthesize",
            AsyncMock(return_value=("/tts/audio/x.wav", 1500)),
        )

        result = await narrate("game_start", G, cm, "test-game")

        mock_llm.assert_not_called()
        assert result == 1500
        _, _, payload = cm.unicast_calls[0]
        assert payload["text"] == "Static preset"

    async def test_returns_0_when_db_empty_in_static_mode(self, monkeypatch):
        from api.narrator.triggers import narrate

        G, _ = _five_player_game()
        cm = _TrackingCM()

        monkeypatch.setattr(
            "api.narrator.triggers.get_narrator_settings", lambda: _settings("static")
        )
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration",
            AsyncMock(return_value="Should not be called"),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.get_preset_script", AsyncMock(return_value="")
        )

        result = await narrate("game_start", G, cm, "test-game")

        assert result == 0
        assert len(cm.unicast_calls) == 0


# ── narrate_sequence ──────────────────────────────────────────────────────────


class TestNarrateSequence:
    async def test_empty_specs_is_noop(self, monkeypatch):
        from api.narrator.triggers import narrate_sequence

        G, _ = _five_player_game()
        cm = _TrackingCM()
        mock_narrate = AsyncMock(return_value=0)
        mock_sleep = AsyncMock()

        monkeypatch.setattr("api.narrator.triggers.narrate", mock_narrate)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        await narrate_sequence([], G, cm, "test-game")

        mock_narrate.assert_not_called()
        mock_sleep.assert_not_called()

    async def test_single_spec_calls_narrate_once_no_sleep(self, monkeypatch):
        from api.narrator.triggers import narrate_sequence

        G, _ = _five_player_game()
        cm = _TrackingCM()
        mock_narrate = AsyncMock(return_value=1000)
        mock_sleep = AsyncMock()

        monkeypatch.setattr("api.narrator.triggers.narrate", mock_narrate)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        await narrate_sequence([("game_start", None, None)], G, cm, "test-game")

        mock_narrate.assert_called_once()
        assert mock_narrate.call_args[0][0] == "game_start"
        # Single trigger: sleep is called once after it
        mock_sleep.assert_called_once_with(1000 / 1000 + 0.3)

    async def test_multiple_specs_called_in_order(self, monkeypatch):
        from api.narrator.triggers import narrate_sequence

        G, _ = _five_player_game()
        cm = _TrackingCM()
        mock_narrate = AsyncMock(return_value=0)
        mock_sleep = AsyncMock()

        monkeypatch.setattr("api.narrator.triggers.narrate", mock_narrate)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        specs = [
            ("night_close", None, None),
            ("day_open", None, None),
            ("player_eliminated", "Alice", None),
        ]
        await narrate_sequence(specs, G, cm, "test-game")

        assert mock_narrate.call_count == 3
        assert mock_narrate.call_args_list[0][0][0] == "night_close"
        assert mock_narrate.call_args_list[1][0][0] == "day_open"
        assert mock_narrate.call_args_list[2][0][0] == "player_eliminated"

    async def test_sleeps_duration_plus_300ms_buffer(self, monkeypatch):
        from api.narrator.triggers import narrate_sequence

        G, _ = _five_player_game()
        cm = _TrackingCM()
        mock_narrate = AsyncMock(return_value=2000)
        mock_sleep = AsyncMock()

        monkeypatch.setattr("api.narrator.triggers.narrate", mock_narrate)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        await narrate_sequence(
            [("night_close", None, None), ("day_open", None, None)], G, cm, "test-game"
        )

        # Each trigger returned 2000 ms → sleep(2.3) after each
        assert mock_sleep.call_count == 2
        for c in mock_sleep.call_args_list:
            assert c == call(2.3)

    async def test_no_sleep_when_narrate_returns_0(self, monkeypatch):
        """When narrate() returns 0 (skipped), no sleep is inserted."""
        from api.narrator.triggers import narrate_sequence

        G, _ = _five_player_game()
        cm = _TrackingCM()
        mock_narrate = AsyncMock(return_value=0)
        mock_sleep = AsyncMock()

        monkeypatch.setattr("api.narrator.triggers.narrate", mock_narrate)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        await narrate_sequence(
            [("night_close", None, None), ("day_open", None, None)], G, cm, "test-game"
        )

        mock_sleep.assert_not_called()

    async def test_continues_after_zero_duration_trigger(self, monkeypatch):
        """A skipped (0-duration) trigger does not prevent subsequent triggers."""
        from api.narrator.triggers import narrate_sequence

        G, _ = _five_player_game()
        cm = _TrackingCM()
        # First spec returns 0 (skipped), second returns 1000
        mock_narrate = AsyncMock(side_effect=[0, 1000])
        mock_sleep = AsyncMock()

        monkeypatch.setattr("api.narrator.triggers.narrate", mock_narrate)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        await narrate_sequence(
            [("night_close", None, None), ("day_open", None, None)], G, cm, "test-game"
        )

        assert mock_narrate.call_count == 2
        # Sleep only called for the second trigger (which returned 1000)
        mock_sleep.assert_called_once_with(1.3)

    async def test_passes_eliminated_name_and_role_to_narrate(self, monkeypatch):
        from api.narrator.triggers import narrate_sequence

        G, _ = _five_player_game()
        cm = _TrackingCM()
        mock_narrate = AsyncMock(return_value=0)
        mock_sleep = AsyncMock()

        monkeypatch.setattr("api.narrator.triggers.narrate", mock_narrate)
        monkeypatch.setattr("asyncio.sleep", mock_sleep)

        await narrate_sequence(
            [("player_eliminated", "Bob", "villager")], G, cm, "test-game"
        )

        _, kwargs = mock_narrate.call_args
        assert kwargs.get("eliminated_name") == "Bob"
        assert kwargs.get("eliminated_role") == "villager"
