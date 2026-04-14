"""
Kokoro TTS client: synthesize text to WAV, serve via /tts/audio/{uuid}.wav.
Background cleanup removes files older than NARRATOR_AUDIO_TTL_S.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
import wave
from pathlib import Path

import httpx

from api.narrator.config import get_narrator_settings

logger = logging.getLogger(__name__)


async def synthesize(text: str) -> tuple[str, int]:
    """
    POST text to Kokoro, save response WAV to disk.
    Returns (audio_url, duration_ms). Raises on failure — caller must catch.
    """
    cfg = get_narrator_settings()
    audio_dir = Path(cfg.narrator_audio_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())
    file_path = audio_dir / f"{file_id}.wav"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{cfg.kokoro_url}/v1/audio/speech",
            json={
                "model": "kokoro",
                "input": text,
                "voice": cfg.narrator_voice,
                "response_format": "wav",
            },
        )
        resp.raise_for_status()
        file_path.write_bytes(resp.content)

    # Compute duration from actual file size rather than the WAV nframes header field.
    # Kokoro writes 0xFFFFFFFF into nframes (streaming WAV) so the header value is
    # unreliable; deriving from (data bytes / bytes-per-frame) is always correct.
    with wave.open(str(file_path)) as wf:
        framerate = wf.getframerate()
        bytes_per_frame = wf.getnchannels() * wf.getsampwidth()
    data_bytes = file_path.stat().st_size - 44  # 44-byte standard PCM WAV header
    duration_ms = int(max(data_bytes, 0) / bytes_per_frame / framerate * 1000)

    return f"/tts/audio/{file_id}.wav", duration_ms


async def cleanup_old_audio() -> None:
    """Remove WAV files older than narrator_audio_ttl_s. Runs once per call."""
    cfg = get_narrator_settings()
    audio_dir = Path(cfg.narrator_audio_dir)
    if not audio_dir.exists():
        return

    cutoff = time.time() - cfg.narrator_audio_ttl_s
    for f in audio_dir.glob("*.wav"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


async def run_cleanup_loop() -> None:
    """Long-running background task: clean up expired audio files every minute."""
    while True:
        await asyncio.sleep(60)
        try:
            await cleanup_old_audio()
        except Exception:
            logger.debug("Audio cleanup error (non-fatal)")
