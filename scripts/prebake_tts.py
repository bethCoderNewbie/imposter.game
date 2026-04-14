#!/usr/bin/env python3
"""
Pre-bake narrator audio using Kokoro TTS (af_bella voice).

Requires: Kokoro Docker service running at http://localhost:8880
Start:    docker compose --profile tts up -d tts   (or with docker-compose.gpu.yml for GPU)
Run:      python scripts/prebake_tts.py
Commit:   git add backend-engine/api/narrator/audio/ && git commit

GPU recommended for generation speed; not needed at runtime (serves static files).
"""

import importlib.util
import json
import sys
import urllib.request
import wave
from collections import defaultdict
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = _PROJECT_ROOT / "backend-engine/api/narrator/audio"
KOKORO_URL = "http://localhost:8880/v1/audio/speech"

# Triggers that have {eliminated_name} placeholders — substitute generic text for audio.
DYNAMIC_TRIGGERS = frozenset({"vote_elimination", "player_eliminated", "hunter_revenge"})

# Load _SEED_DATA directly from the alembic migrations — no DB needed.
# Stub out alembic.op and sqlalchemy so the module-level imports don't fail.
import types as _types
_alembic_stub = _types.ModuleType("alembic")
_alembic_stub.op = _types.ModuleType("alembic.op")
sys.modules.setdefault("alembic", _alembic_stub)
sys.modules.setdefault("alembic.op", _alembic_stub.op)
sys.modules.setdefault("sqlalchemy", _types.ModuleType("sqlalchemy"))
sys.modules.setdefault("sqlalchemy.orm", _types.ModuleType("sqlalchemy.orm"))


def _load_seed(path: Path) -> list:
    spec = importlib.util.spec_from_file_location("_mig_" + path.stem, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._SEED_DATA


_VERSIONS = _PROJECT_ROOT / "backend-engine/alembic/versions"
_SEED_DATA: list = (
    _load_seed(_VERSIONS / "b2c3d4e5f6a7_reseed_narrator_scripts.py")
    + _load_seed(_VERSIONS / "c3d4e5f6a7b8_narrator_hunter_no_elim.py")
)


def synthesize(text: str, out_path: Path) -> None:
    """POST text to Kokoro TTS, save response WAV to out_path."""
    payload = json.dumps({
        "model": "kokoro",
        "input": text,
        "voice": "af_bella",
        "response_format": "wav",
    }).encode()
    req = urllib.request.Request(
        KOKORO_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        out_path.write_bytes(resp.read())


def duration_ms(wav_path: Path) -> int:
    with wave.open(str(wav_path)) as wf:
        framerate = wf.getframerate()
        bytes_per_frame = wf.getnchannels() * wf.getsampwidth()
    data_bytes = wav_path.stat().st_size - 44  # 44-byte PCM WAV header
    return int(max(data_bytes, 0) / bytes_per_frame / framerate * 1000)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[str]] = defaultdict(list)
    for trigger_id, text in _SEED_DATA:
        grouped[trigger_id].append(text)

    total = sum(len(v) for v in grouped.values())
    generated = 0
    skipped = 0
    errors = 0

    print(f"Output dir : {OUTPUT_DIR}")
    print(f"TTS URL    : {KOKORO_URL}")
    print(f"Total lines: {total}")
    print()

    for trigger_id, texts in grouped.items():
        for index, raw_text in enumerate(texts):
            text = (
                raw_text.format(eliminated_name="a player")
                if trigger_id in DYNAMIC_TRIGGERS
                else raw_text
            )
            out = OUTPUT_DIR / f"{trigger_id}_{index:02d}.wav"
            if out.exists():
                print(f"  SKIP  {out.name}")
                skipped += 1
                continue
            print(f"  GEN   {out.name}  |  {text[:55]}...")
            try:
                synthesize(text, out)
                ms = duration_ms(out)
                print(f"        -> {ms} ms")
                generated += 1
            except Exception as exc:
                print(f"  ERR   {out.name}: {exc}", file=sys.stderr)
                errors += 1

    print()
    print(f"Done. generated={generated}  skipped={skipped}  errors={errors}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
