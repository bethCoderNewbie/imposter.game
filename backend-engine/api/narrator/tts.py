"""
Kokoro TTS client: synthesize text to WAV, serve via /tts/audio/{uuid}.wav.
Background cleanup removes files older than NARRATOR_AUDIO_TTL_S.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
import wave
from pathlib import Path

import httpx

from api.narrator.config import get_narrator_settings
from engine.config import get_settings

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

    base = get_settings().backend_public_url.rstrip("/")
    return f"{base}/tts/audio/{file_id}.wav", duration_ms


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


async def pick_prebaked(trigger_id: str, voice: str = "kokoro") -> tuple[str, int, int]:
    """
    Randomly select a pre-generated WAV for trigger_id from the given voice subdir.
    Files named: {trigger_id}_{index:02d}.wav
    Returns ("/tts/static/{voice}/{filename}", duration_ms, chosen_index).
    The index is used by get_preset_script() to select the matching subtitle row.
    Raises FileNotFoundError if no candidates — caught by narrate() try/except.
    """
    cfg = get_narrator_settings()
    audio_dir = Path(cfg.narrator_prebaked_dir) / voice
    candidates = sorted(audio_dir.glob(f"{trigger_id}_*.wav"))
    if not candidates:
        raise FileNotFoundError(f"No prebaked audio for '{trigger_id}' in {audio_dir}")
    chosen = random.choice(candidates)
    actual_idx = int(chosen.stem.rsplit("_", 1)[-1])  # e.g. "game_start_07" → 7

    # Robust byte-count method — same as synthesize() — works for both Piper and Kokoro WAVs.
    with wave.open(str(chosen)) as wf:
        framerate = wf.getframerate()
        bytes_per_frame = wf.getnchannels() * wf.getsampwidth()
    data_bytes = chosen.stat().st_size - 44
    duration_ms = int(max(data_bytes, 0) / bytes_per_frame / framerate * 1000)

    base = get_settings().backend_public_url.rstrip("/")
    return f"{base}/tts/static/{voice}/{chosen.name}", duration_ms, actual_idx
