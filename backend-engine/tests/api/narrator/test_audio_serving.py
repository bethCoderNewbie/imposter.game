"""
Tests for the GET /tts/audio/{filename} endpoint defined in api/main.py.

Uses the `client` fixture (fakeredis + TestClient).
asyncio_mode = "auto" — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.api.narrator.conftest import make_wav_bytes


class TestAudioServing:
    # get_narrator_settings is imported locally inside serve_tts_audio(), so patch
    # it at its definition site (api.narrator.config) rather than api.main.
    def test_returns_wav_for_existing_file(self, client, tmp_path, monkeypatch):
        """GET /tts/audio/{file} returns 200 + audio/wav for an existing WAV."""
        wav_data = make_wav_bytes(duration_s=0.5)
        (tmp_path / "test.wav").write_bytes(wav_data)

        monkeypatch.setattr(
            "api.narrator.config.get_narrator_settings",
            lambda: SimpleNamespace(narrator_audio_dir=str(tmp_path)),
        )

        resp = client.get("/tts/audio/test.wav")
        assert resp.status_code == 200
        assert "audio/wav" in resp.headers.get("content-type", "")

    def test_returns_404_for_missing_file(self, client, tmp_path, monkeypatch):
        """GET /tts/audio/{file} returns 404 when the file does not exist."""
        monkeypatch.setattr(
            "api.narrator.config.get_narrator_settings",
            lambda: SimpleNamespace(narrator_audio_dir=str(tmp_path)),
        )

        resp = client.get("/tts/audio/notfound.wav")
        assert resp.status_code == 404

    def test_returns_404_for_non_wav_extension(self, client, tmp_path, monkeypatch):
        """GET /tts/audio/{file} returns 404 for non-.wav extensions."""
        (tmp_path / "evil.txt").write_text("hax")

        monkeypatch.setattr(
            "api.narrator.config.get_narrator_settings",
            lambda: SimpleNamespace(narrator_audio_dir=str(tmp_path)),
        )

        resp = client.get("/tts/audio/evil.txt")
        assert resp.status_code == 404

    def test_returns_404_for_path_traversal_attempt(self, client, tmp_path, monkeypatch):
        """GET /tts/audio/../etc/passwd is rejected with 404."""
        monkeypatch.setattr(
            "api.narrator.config.get_narrator_settings",
            lambda: SimpleNamespace(narrator_audio_dir=str(tmp_path)),
        )

        resp = client.get("/tts/audio/../etc/passwd")
        assert resp.status_code == 404
