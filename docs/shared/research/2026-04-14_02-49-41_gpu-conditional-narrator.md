---
title: "GPU-Conditional Ollama/TTS Services"
date: 2026-04-14
branch: feat/prd-008-narrator
commit: b63efa32d2852eb036a6faef25c111a8bb6ed4f4
researcher: bethCoderNewbie
---

## Problem

`docker-compose.yml` hard-requires NVIDIA GPU for both narrator services. On a CPU-only host, `docker compose up` fails at GPU reservation, blocking the entire stack — even when `NARRATOR_ENABLED=false`.

---

## Ground Truth

### Current `docker-compose.yml` state

| Service | Image | GPU block | Lines |
|---|---|---|---|
| `ollama` | `ollama/ollama` | Yes — `deploy.resources.reservations.devices` | 32–38 |
| `ollama-pull` | `ollama/ollama` | No | — |
| `tts` | `ghcr.io/remsky/kokoro-fastapi-gpu:latest` | Yes — same pattern | 63–68 |

**Backend `depends_on`** (`docker-compose.yml:85-93`): requires `tts: service_started` and `ollama: service_started` — meaning backend won't start if narrator services fail.

**`start.sh:59`**: `docker compose up --build "$@"` — no GPU detection, no profile selection.

### Key facts

1. `ollama/ollama` runs on CPU fine — the `deploy.resources` block merely *reserves* a GPU device. Removing it enables CPU inference (slower, but functional).
2. Kokoro has two image variants:
   - GPU: `ghcr.io/remsky/kokoro-fastapi-gpu:latest` (current)
   - CPU: `ghcr.io/remsky/kokoro-fastapi-cpu:latest` (needs substitution)
3. Docker Compose ≥ 2.20 supports `required: false` in `depends_on` — lets backend start even if a dependency service is not running/profiled.
4. No existing `docker-compose.gpu.yml` or `docker-compose.cpu.yml` override files exist.
5. No Compose profiles are currently defined on any service.

---

## Recommended Approach: Override File + start.sh Detection

### Why not profiles alone?

Profiles require the caller to always pass `--profile narrator`. They don't automatically select GPU vs CPU images based on hardware — you'd still need two profile variants or an override file.

### Architecture

```
docker-compose.yml          ← base; no GPU blocks; CPU TTS image
docker-compose.gpu.yml      ← override; adds GPU deploy blocks + GPU TTS image
start.sh                    ← detects nvidia-smi → selects compose files
```

### Changes required

**`docker-compose.yml`**
1. `ollama` (line 32–38): remove `deploy.resources` block entirely.
2. `tts` (line 58): change image to `ghcr.io/remsky/kokoro-fastapi-cpu:latest`; remove `deploy.resources` block (lines 63–68).
3. `backend.depends_on.tts` and `backend.depends_on.ollama` (lines 90–93): add `required: false` to each so backend starts without narrator services.

**New `docker-compose.gpu.yml`**
```yaml
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
  tts:
    image: ghcr.io/remsky/kokoro-fastapi-gpu:latest
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

**`start.sh`** — insert between step 1 (LAN IP) and step 2 (docker compose up):
```bash
# ── 1b. GPU detection ──────────────────────────────────────────────────────────
COMPOSE_FILES="-f docker-compose.yml"
if nvidia-smi &>/dev/null 2>&1; then
  echo "GPU detected  — narrator services will use GPU acceleration"
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
else
  echo "No GPU detected — narrator services will run on CPU (slower inference)"
fi

# Step 2 becomes:
docker compose $COMPOSE_FILES up --build "$@"
```

### Behaviour matrix

| Host | Command | Result |
|---|---|---|
| CPU-only | `./start.sh` | CPU TTS + Ollama, no GPU errors |
| GPU host | `./start.sh` | GPU TTS + Ollama via override |
| Any | `NARRATOR_ENABLED=false ./start.sh` | Services start but narrator is disabled at app level |
| Manual GPU override | `./start.sh -f docker-compose.yml -f docker-compose.gpu.yml up` | Force GPU path regardless of detection |

---

## Out of Scope

- Docker Compose profiles (adds caller burden, doesn't solve image selection)
- Removing narrator services entirely on CPU (they work on CPU, just slower)
- Auto-pulling Ollama model on first run — `ollama-pull` init container handles this already

---

## Success Criteria

- `docker compose up` on a CPU-only machine: all services start, no `nvidia runtime` errors
- `./start.sh` on a GPU machine: GPU override applied, `ghcr.io/remsky/kokoro-fastapi-gpu` used
- Backend starts regardless of narrator service state (`required: false` in depends_on)
