"""
Shared fixtures and helpers for narrator tests.

Provides:
- make_wav_bytes()      — minimal valid WAV bytes for TTS mocking
- _MockHttpxResponse    — httpx response stub
- _MockHttpxClient      — async context manager stub for httpx.AsyncClient
- clear_settings_cache  — autouse fixture; clears lru_cache on every test
"""

from __future__ import annotations

import io
import wave
from unittest.mock import MagicMock

import pytest


def make_wav_bytes(duration_s: float = 1.0, framerate: int = 22050) -> bytes:
    """Minimal valid WAV bytes — 1 channel, 16-bit PCM."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(b"\x00\x00" * int(duration_s * framerate))
    return buf.getvalue()


class _MockHttpxResponse:
    def __init__(self, json_data=None, content: bytes = b"", status_code: int = 200):
        self._json = json_data or {}
        self.content = content
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                "err",
                request=MagicMock(spec=["url", "method"]),
                response=MagicMock(spec=["status_code"]),
            )


class _MockHttpxClient:
    """Minimal async context manager that replaces httpx.AsyncClient in tests."""

    def __init__(self, response: _MockHttpxResponse | None):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def post(self, *a, **kw):
        return self._response


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear lru_cache on Settings singletons before and after each test."""
    from api.narrator.config import get_narrator_settings
    from engine.config import get_settings

    get_settings.cache_clear()
    get_narrator_settings.cache_clear()
    yield
    get_settings.cache_clear()
    get_narrator_settings.cache_clear()
