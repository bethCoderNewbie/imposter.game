#!/usr/bin/env python3
"""
Pre-bake narrator audio using a configurable TTS model.

Requires: a TTS Docker service running at the model's default endpoint.
Run:      python scripts/prebake_tts.py [--model MODEL] [--url URL] [--voice VOICE] [--force]
Commit:   git add backend-engine/api/narrator/audio/ && git commit

GPU recommended for generation speed; not needed at runtime (serves static files).

docker compose -f /home/beth/work/ml/games/models/voice/fish-speech/docker-compose.yml up -d --build
docker compose -f /home/beth/work/ml/games/models/voice/cosyvoice/docker-compose.yml up -d

Model defaults (all expose OpenAI-compatible /v1/audio/speech):
  kokoro      http://localhost:8014  voice=af_bella      model_id=kokoro
  chatterbox  http://localhost:8012  voice=default       model_id=tts-1
  fish-speech http://localhost:8081  voice=rickman_clean_raw  model_id=fish-speech
  openedai    http://localhost:8010  voice=alloy         model_id=tts-1
  dia         http://localhost:8013  voice=default       model_id=tts-1
  qwen3       http://localhost:8016  voice=uncle_fu       model_id=tts-1
             supported voices: aiden, dylan, eric, ono_anna, ryan, serena, sohee, uncle_fu, vivian
  cosyvoice   http://localhost:8015  voice=7c95bbd303fd (marvin)  model_id=tts-1

Note: the imposter's bundled kokoro container runs on 8880, not 8014.
Use --url http://localhost:8880/v1/audio/speech when using that container.
"""

import argparse
import datetime
import hashlib
import importlib.util
import json
import sys
import urllib.request
import wave
from collections import defaultdict
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_AUDIO_ROOT = _PROJECT_ROOT / "backend-engine/api/narrator/audio"

# Triggers that have {eliminated_name} placeholders — substitute generic text for audio.
DYNAMIC_TRIGGERS = frozenset({"vote_elimination", "player_eliminated", "hunter_revenge"})

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

_MODELS: dict[str, dict] = {
    "kokoro":      {"port": 8014, "voice": "af_bella",          "model_id": "kokoro"},
    "chatterbox":  {"port": 8012, "voice": "default",           "model_id": "tts-1"},
    "fish-speech": {"port": 8081, "voice": "rickman_clean_raw", "model_id": "fish-speech"},
    "openedai":    {"port": 8010, "voice": "alloy",             "model_id": "tts-1"},
    "dia":         {"port": 8013, "voice": "default",           "model_id": "tts-1"},
    "qwen3":       {"port": 8016, "voice": "uncle_fu",           "model_id": "tts-1"},
    "cosyvoice":   {"port": 8015, "voice": "7c95bbd303fd",       "model_id": "tts-1"},  # marvin
}

# ---------------------------------------------------------------------------
# Seed loading (no DB needed — stubs out alembic/sqlalchemy imports)
# ---------------------------------------------------------------------------

import types as _types
_alembic_stub = _types.ModuleType("alembic")
_alembic_stub.op = _types.ModuleType("alembic.op")
sys.modules.setdefault("alembic", _alembic_stub)
sys.modules.setdefault("alembic.op", _alembic_stub.op)
sys.modules.setdefault("sqlalchemy", _types.ModuleType("sqlalchemy"))
sys.modules.setdefault("sqlalchemy.orm", _types.ModuleType("sqlalchemy.orm"))

_VERSIONS = _PROJECT_ROOT / "backend-engine/alembic/versions"

SEED_FILES = [
    _VERSIONS / "b2c3d4e5f6a7_reseed_narrator_scripts.py",
    _VERSIONS / "c3d4e5f6a7b8_narrator_hunter_no_elim.py",
]


def _load_seed(path: Path) -> list:
    spec = importlib.util.spec_from_file_location("_mig_" + path.stem, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._SEED_DATA


_SEED_DATA: list = sum((_load_seed(p) for p in SEED_FILES), [])


def _compute_seed_hash() -> str:
    h = hashlib.sha256()
    for p in sorted(SEED_FILES):
        h.update(p.name.encode())   # include filename so renames are detected
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

_MANIFEST_NAME = ".manifest.json"


def _load_manifest(out_dir: Path) -> dict:
    manifest_path = out_dir / _MANIFEST_NAME
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_manifest(out_dir: Path, model: str, url: str, voice: str,
                    seed_hash: str, file_count: int) -> None:
    manifest = {
        "model": model,
        "url": url,
        "voice": voice,
        "seed_hash": seed_hash,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "file_count": file_count,
    }
    (out_dir / _MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")


# ---------------------------------------------------------------------------
# TTS synthesis
# ---------------------------------------------------------------------------

def synthesize(text: str, out_path: Path, *, url: str, voice: str, model_id: str) -> None:
    """POST text to a TTS service, save response WAV to out_path."""
    payload = json.dumps({
        "model": model_id,
        "input": text,
        "voice": voice,
        "response_format": "wav",
    }).encode()
    req = urllib.request.Request(
        url,
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-bake narrator audio using a configurable TTS model.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model",
        default="qwen3",
        choices=list(_MODELS),
        help="TTS model to use (default: qwen3).",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="Override the model's default endpoint URL.",
    )
    parser.add_argument(
        "--voice",
        default=None,
        help="Override the model's default voice.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-generate files even if they already exist.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()

    reg = _MODELS[args.model]
    url   = args.url   or f"http://localhost:{reg['port']}/v1/audio/speech"
    voice = args.voice or reg["voice"]
    model_id = reg["model_id"]

    out_dir = _AUDIO_ROOT / args.model
    out_dir.mkdir(parents=True, exist_ok=True)

    seed_hash = _compute_seed_hash()

    # Seed-change warning
    manifest = _load_manifest(out_dir)
    if manifest and manifest.get("seed_hash") and manifest["seed_hash"] != seed_hash:
        print(
            f"WARN  seed data changed "
            f"(was {manifest['seed_hash']}, now {seed_hash}) "
            f"— use --force to regenerate"
        )

    grouped: dict[str, list[str]] = defaultdict(list)
    for trigger_id, text in _SEED_DATA:
        grouped[trigger_id].append(text)

    total = sum(len(v) for v in grouped.values())
    generated = 0
    skipped = 0
    errors = 0

    print(f"Model      : {args.model}  (model_id={model_id})")
    print(f"TTS URL    : {url}")
    print(f"Voice      : {voice}")
    print(f"Output dir : {out_dir}")
    print(f"Seed hash  : {seed_hash}")
    print(f"Total lines: {total}")
    print()

    for trigger_id, texts in grouped.items():
        for index, raw_text in enumerate(texts):
            text = (
                raw_text.format(eliminated_name="a player")
                if trigger_id in DYNAMIC_TRIGGERS
                else raw_text
            )
            out = out_dir / f"{trigger_id}_{index:02d}.wav"
            if out.exists() and not args.force:
                print(f"  SKIP  {out.name}")
                skipped += 1
                continue
            action = "REGEN" if (out.exists() and args.force) else "GEN  "
            print(f"  {action} {out.name}  |  {text[:55]}...")
            try:
                synthesize(text, out, url=url, voice=voice, model_id=model_id)
                ms = duration_ms(out)
                print(f"        -> {ms} ms")
                generated += 1
            except Exception as exc:
                print(f"  ERR   {out.name}: {exc}", file=sys.stderr)
                errors += 1

    file_count = len(list(out_dir.glob("*.wav")))
    _write_manifest(out_dir, model=args.model, url=url, voice=voice,
                    seed_hash=seed_hash, file_count=file_count)

    print()
    print(f"Done. generated={generated}  skipped={skipped}  errors={errors}")
    print(f"Manifest written to {out_dir / _MANIFEST_NAME}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
