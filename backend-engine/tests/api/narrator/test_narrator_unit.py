"""
Unit tests for narrator LLM, TTS, cleanup, and pipeline.

All external I/O is mocked — no Ollama or Kokoro services needed.
asyncio_mode = "auto" (see pyproject.toml) so no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from tests.api.narrator.conftest import _MockHttpxClient, _MockHttpxResponse, make_wav_bytes


# ── TestGenerateNarration ─────────────────────────────────────────────────────


class TestGenerateNarration:
    async def test_returns_text_on_ollama_success(self):
        from api.narrator.llm import generate_narration

        response = _MockHttpxResponse(json_data={"response": "Night falls."})
        with patch("api.narrator.llm.httpx.AsyncClient", return_value=_MockHttpxClient(response)):
            result = await generate_narration(
                "night_open",
                alive_count=6,
                eliminated_name=None,
                eliminated_role=None,
                round_num=1,
            )
        assert result == "Night falls."

    async def test_returns_empty_on_timeout(self):
        from api.narrator.llm import generate_narration

        mock_client = _MockHttpxClient(None)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with patch("api.narrator.llm.httpx.AsyncClient", return_value=mock_client):
            result = await generate_narration(
                "night_open",
                alive_count=6,
                eliminated_name=None,
                eliminated_role=None,
                round_num=1,
            )
        assert result == ""

    async def test_returns_empty_on_http_error(self):
        from api.narrator.llm import generate_narration

        response = _MockHttpxResponse(status_code=500)
        with patch("api.narrator.llm.httpx.AsyncClient", return_value=_MockHttpxClient(response)):
            result = await generate_narration(
                "night_open",
                alive_count=6,
                eliminated_name=None,
                eliminated_role=None,
                round_num=1,
            )
        assert result == ""

    async def test_returns_empty_for_unknown_trigger(self):
        from api.narrator.llm import generate_narration

        result = await generate_narration(
            "bogus",
            alive_count=6,
            eliminated_name=None,
            eliminated_role=None,
            round_num=1,
        )
        assert result == ""


# ── TestSynthesize ────────────────────────────────────────────────────────────


class TestSynthesize:
    async def test_saves_wav_returns_url_and_duration(self, tmp_path, monkeypatch):
        from api.narrator.tts import synthesize

        wav_bytes = make_wav_bytes(duration_s=1.0)
        response = _MockHttpxResponse(content=wav_bytes)

        monkeypatch.setattr(
            "api.narrator.tts.get_narrator_settings",
            lambda: SimpleNamespace(
                kokoro_url="http://tts:8880",
                narrator_audio_dir=str(tmp_path),
                narrator_voice="af_bella",
                narrator_audio_ttl_s=300,
            ),
        )
        with patch("api.narrator.tts.httpx.AsyncClient", return_value=_MockHttpxClient(response)):
            url, duration_ms = await synthesize("hello")

        assert url.startswith("/tts/audio/")
        assert url.endswith(".wav")
        assert 900 <= duration_ms <= 1100  # ~1000 ms
        filename = url.split("/")[-1]
        assert (tmp_path / filename).exists()

    async def test_audio_url_starts_with_tts_audio(self, tmp_path, monkeypatch):
        from api.narrator.tts import synthesize

        wav_bytes = make_wav_bytes(duration_s=0.5)
        response = _MockHttpxResponse(content=wav_bytes)

        monkeypatch.setattr(
            "api.narrator.tts.get_narrator_settings",
            lambda: SimpleNamespace(
                kokoro_url="http://tts:8880",
                narrator_audio_dir=str(tmp_path),
                narrator_voice="af_bella",
                narrator_audio_ttl_s=300,
            ),
        )
        with patch("api.narrator.tts.httpx.AsyncClient", return_value=_MockHttpxClient(response)):
            url, _ = await synthesize("test phrase")

        assert url.startswith("/tts/audio/")

    async def test_raises_on_kokoro_http_error(self, tmp_path, monkeypatch):
        from api.narrator.tts import synthesize

        response = _MockHttpxResponse(status_code=503)
        monkeypatch.setattr(
            "api.narrator.tts.get_narrator_settings",
            lambda: SimpleNamespace(
                kokoro_url="http://tts:8880",
                narrator_audio_dir=str(tmp_path),
                narrator_voice="af_bella",
                narrator_audio_ttl_s=300,
            ),
        )
        with patch("api.narrator.tts.httpx.AsyncClient", return_value=_MockHttpxClient(response)):
            with pytest.raises(httpx.HTTPStatusError):
                await synthesize("hello")


# ── TestCleanupOldAudio ───────────────────────────────────────────────────────


class TestCleanupOldAudio:
    async def test_deletes_expired_files(self, tmp_path, monkeypatch):
        from api.narrator.tts import cleanup_old_audio

        old_file = tmp_path / "old.wav"
        old_file.write_bytes(b"fake")
        old_time = time.time() - 400  # 400 s ago > TTL of 300 s
        os.utime(str(old_file), (old_time, old_time))

        monkeypatch.setattr(
            "api.narrator.tts.get_narrator_settings",
            lambda: SimpleNamespace(
                narrator_audio_dir=str(tmp_path),
                narrator_audio_ttl_s=300,
            ),
        )
        await cleanup_old_audio()
        assert not old_file.exists()

    async def test_keeps_recent_files(self, tmp_path, monkeypatch):
        from api.narrator.tts import cleanup_old_audio

        new_file = tmp_path / "new.wav"
        new_file.write_bytes(b"fake")  # mtime = now

        monkeypatch.setattr(
            "api.narrator.tts.get_narrator_settings",
            lambda: SimpleNamespace(
                narrator_audio_dir=str(tmp_path),
                narrator_audio_ttl_s=300,
            ),
        )
        await cleanup_old_audio()
        assert new_file.exists()


# ── TestNarratorPipeline ──────────────────────────────────────────────────────


class _TrackingCM:
    """Connection manager that records unicast calls for assertion."""

    def __init__(self):
        self.unicast_calls: list[tuple] = []

    async def unicast(self, game_id, player_id, payload):
        self.unicast_calls.append((game_id, player_id, payload))

    async def broadcast(self, game_id, G):
        pass


class TestNarratorPipeline:
    async def test_unicasts_to_display_player_id_none(self, monkeypatch):
        from api.narrator.triggers import narrate
        from tests.conftest import _five_player_game

        G, _ = _five_player_game()
        cm = _TrackingCM()
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration",
            AsyncMock(return_value="Village awakes."),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.synthesize",
            AsyncMock(return_value=("/tts/audio/x.wav", 2000)),
        )

        await narrate("night_close", G, cm, "test-game-1")

        assert len(cm.unicast_calls) == 1
        _, player_id, _ = cm.unicast_calls[0]
        assert player_id is None

    async def test_message_payload_structure(self, monkeypatch):
        from api.narrator.triggers import narrate
        from tests.conftest import _five_player_game

        G, _ = _five_player_game()
        cm = _TrackingCM()
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration",
            AsyncMock(return_value="Village awakes."),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.synthesize",
            AsyncMock(return_value=("/tts/audio/x.wav", 2000)),
        )

        await narrate("night_close", G, cm, "test-game-1")

        _, _, payload = cm.unicast_calls[0]
        assert payload["type"] == "narrate"
        assert payload["trigger"] == "night_close"
        assert payload["text"] == "Village awakes."
        assert payload["audio_url"] == "/tts/audio/x.wav"
        assert payload["duration_ms"] == 2000
        assert isinstance(payload["phase"], str)
        assert isinstance(payload["round"], int)

    async def test_silent_when_llm_returns_empty(self, monkeypatch):
        from api.narrator.triggers import narrate
        from tests.conftest import _five_player_game

        G, _ = _five_player_game()
        cm = _TrackingCM()
        synthesize_mock = AsyncMock(return_value=("/tts/audio/x.wav", 2000))
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration",
            AsyncMock(return_value=""),
        )
        monkeypatch.setattr("api.narrator.triggers.synthesize", synthesize_mock)

        await narrate("night_close", G, cm, "test-game-1")

        synthesize_mock.assert_not_called()
        assert len(cm.unicast_calls) == 0

    async def test_silent_on_tts_exception(self, monkeypatch):
        from api.narrator.triggers import narrate
        from tests.conftest import _five_player_game

        G, _ = _five_player_game()
        cm = _TrackingCM()
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration",
            AsyncMock(return_value="Night falls."),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.synthesize",
            AsyncMock(side_effect=httpx.ConnectError("connection refused")),
        )

        # Must not raise — all exceptions are swallowed inside narrate()
        await narrate("night_close", G, cm, "test-game-1")
        assert len(cm.unicast_calls) == 0

    async def test_silent_on_generic_exception(self, monkeypatch):
        from api.narrator.triggers import narrate
        from tests.conftest import _five_player_game

        G, _ = _five_player_game()
        cm = _TrackingCM()
        monkeypatch.setattr(
            "api.narrator.triggers.generate_narration",
            AsyncMock(return_value="Night falls."),
        )
        monkeypatch.setattr(
            "api.narrator.triggers.synthesize",
            AsyncMock(side_effect=RuntimeError("oops")),
        )

        # Must not raise
        await narrate("night_close", G, cm, "test-game-1")
        assert len(cm.unicast_calls) == 0
