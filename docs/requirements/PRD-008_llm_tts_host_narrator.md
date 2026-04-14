# PRD-008: LLM Text-to-Speech Host Narrator

**Status:** Draft — Revalidated 2026-04-13
**Date:** 2026-03-30
**Schema version context:** 0.7
**Revalidation note:** 4 inaccuracies corrected against current codebase (see §2.2, §3.1, §3.3, §3.4). Architecture confirmed feasible.

---

## §1 — Context & Problem

Werewolf is a social deduction game driven by a human moderator who reads scripted lines ("Night falls over the village…", "The Werewolves open their eyes…"). In a Jackbox-style digital deployment the host is a screen, not a person — so narration either goes silent or requires someone to read lines manually.

**Goal:** Replace the silent display with a voiced LLM narrator: a local model generates contextual narration lines from game events and a local TTS engine speaks them aloud through the Display TV's speakers. The narrator becomes the game's host.

**Same-WiFi constraint:** The current deployment requires every player's phone to reach the host machine on the LAN. This limits the game to a single physical location. This PRD evaluates two deployment topologies:

| | Option A — Full Local | Option B — Hybrid (Vercel Frontend) |
|---|---|---|
| Player WiFi required | Same LAN as host | Internet only |
| Display WiFi required | Same LAN as host | Internet only |
| Backend location | Host machine | Host machine |
| Frontend location | Host machine (Nginx) | Vercel CDN |
| Tunnel required | No | Yes (Cloudflare Tunnel) |

---

## §2.1 — Narration Event Model

### Narrator Triggers

The narrator fires on **phase transitions** and **elimination events**. It does NOT fire on per-player actions (too chatty). Every trigger maps to a prompt template fed to the local LLM.

| Trigger ID | Game Event | Example Generated Line |
|---|---|---|
| `game_start` | `start_game` intent processed | "The village sleeps uneasily. Among you hides a killer." |
| `night_open` | phase → `night_action` | "Night falls. Close your eyes." |
| `night_close` | phase → `night_resolution` | "The village stirs. Dawn breaks cold and grey." |
| `day_open` | phase → `day_discussion` | "Someone did not survive the night." |
| `player_eliminated` | `EliminationEvent` appended | "John has been found dead. They were a Villager." |
| `vote_open` | phase → `day_vote` | "It is time to cast your vote." |
| `vote_elimination` | vote resolves, player eliminated | "The village has spoken. Sarah leaves the game." |
| `wolves_win` | `winner == "werewolf"` | "The wolves have consumed the village. Darkness wins." |
| `village_wins` | `winner == "village"` | "The last wolf has been unmasked. The village is saved." |

### LLM Prompt Template

```
System: You are the narrator of a Werewolf party game. Speak in 1-2 dramatic sentences.
        Never reveal hidden roles. Do not break character. Use the player's name if provided.
User:   Event: {trigger_id}
        Players alive: {alive_count}
        Eliminated player: {name} ({role_if_game_over_else_hidden})
        Round: {round}
```

The backend calls Ollama's `/api/generate` endpoint (HTTP, non-streaming for simplicity). Target latency: < 2 s on a 3B-parameter model.

### TTS Engine Selection

| Engine | Model size | CPU RTF | Quality | License | Notes |
|---|---|---|---|---|---|
| **Kokoro-82M** | 82 MB | ~50× | High | Apache 2.0 | Recommended — fast, Python pip install |
| **Piper** | 5–65 MB | ~100× | Medium-High | MIT | Fastest option, ONNX runtime |
| **Bark** | 1.3 GB | ~1× (slow) | Highest | MIT | Best dramatic effect, needs GPU for real-time |

**Recommended default:** Kokoro-82M. Produces natural, theatrical English narration in < 500 ms on a modern CPU. Falls back to Piper if Kokoro fails to load.

---

## §2.2 — Payload Schema

### New WebSocket Message Type: `NarrateMessage`

**Backend (Python):** Add as a `TypedDict` or Pydantic model in `backend-engine/engine/state/models.py` (alongside existing event models). The backend has no shared TypeScript schema file — all message types are plain Python dicts dispatched via `ConnectionManager`.

```python
class NarratePayload(TypedDict):
    type: Literal["narrate"]
    trigger: str          # NarratorTrigger literal
    text: str             # generated narration text (for subtitle display)
    audio_url: str        # "/tts/audio/abc123.wav" (Option A) or absolute tunnel URL (Option B)
    duration_ms: int      # audio length for subtitle timing / client auto-advance
    phase: str            # current game phase when triggered
    round: int
```

**Frontend (TypeScript):** Add a TS interface in `frontend-display/src/types/narrator.ts` for type safety:

```typescript
interface NarrateMessage {
  type: "narrate";
  trigger: NarratorTrigger;
  text: string;
  audio_url: string;
  duration_ms: number;
  phase: string;
  round: number;
}

type NarratorTrigger =
  | "game_start" | "night_open" | "night_close"
  | "day_open"   | "player_eliminated" | "vote_open"
  | "vote_elimination" | "wolves_win" | "village_wins";
```

`NarrateMessage` is unicast to **Display client only**. Mobile clients do not receive it. Confirm the display player_id registration key in `backend-engine/api/ws/endpoint.py` before implementing the unicast call.

### New TTS Service REST Contract

Internal endpoint (not player-facing):

```
POST /tts/generate
Body:     { "text": "...", "voice": "af_bella" }
Response: { "audio_url": "/tts/audio/{uuid}.wav", "duration_ms": 3200 }

GET /tts/audio/{uuid}.wav
Response: audio/wav binary
```

Audio files are ephemeral (TTL 5 min, cleaned by background task).

---

## §3 — Client-Server Specifications

### §3.1 Backend (`backend-engine/`)

**New package:** `backend-engine/api/narrator/`

| File | Responsibility |
|---|---|
| `narrator/llm.py` | Calls Ollama `POST /api/generate`. Prompt templating. Returns `str`. |
| `narrator/tts.py` | Calls TTS service HTTP. Returns `(audio_url, duration_ms)`. |
| `narrator/triggers.py` | Maps game event → trigger ID → calls llm + tts → returns `NarratePayload`. |
| `narrator/config.py` | `OLLAMA_URL`, `OLLAMA_MODEL`, `TTS_SERVICE_URL`, `NARRATOR_ENABLED` env vars. |

**Integration point:** `backend-engine/api/intents/handlers.py`. After each state mutation matching a trigger, call `narrator/triggers.py` as a fire-and-forget `asyncio.create_task(...)`. On completion, call `cm.unicast(game_id, <display_player_id>, narrate_payload)`.

> **Note:** `ConnectionManager` has no `send_to_display()` method. The actual methods are `unicast(game_id, player_id, payload)`, `broadcast(game_id, G)`, and `broadcast_raw(game_id, payload)`. Either add a `send_to_display()` convenience wrapper to `ConnectionManager`, or call `cm.unicast()` directly. Confirm the display player_id key (`None` or `"display"`) by reading `backend-engine/api/ws/endpoint.py` first.

**Key invariant:** Narration never blocks state mutation. If TTS or LLM fails, the game continues silently.

### §3.2 TTS Microservice (new container)

```
tts-service/
  Dockerfile     # python:3.11-slim, pip install kokoro soundfile fastapi uvicorn
  main.py        # FastAPI: POST /generate, GET /audio/{uuid}
  audio/         # ephemeral wav files
```

Isolated container so Kokoro model weights load once and stay in memory. Exposed internally as `tts:5500` in docker-compose.

### §3.3 Display Client (`frontend-display/`)

**New hook:** `frontend-display/src/hooks/useNarrator.ts`

```typescript
// Fires on "narrate" WS message
const useNarrator = () => {
  // 1. Play audio via <audio> element (audio context already unlocked by App.tsx:96-111 gesture)
  // 2. Show subtitle overlay for duration_ms
  // 3. Dispatch to gameStore: set narratorText, clear after duration
}
```

**New component:** `frontend-display/src/components/NarratorSubtitle.tsx` — fixed bottom overlay, CSS fade in/out, renders `narratorText` from Zustand store.

The existing audio unlock gesture at `App.tsx:97-104` already handles browser autoplay policy. No change needed.

### §3.4 Mobile Client

No changes. Mobile phones do not play or display narration.

---

## §4 — Deployment Options

### Option A — Full Local (LAN Party)

```
[Host Machine — docker compose up]
  nginx:80
    /          → frontend-mobile:80
    /display/  → frontend-display:80
    /api/      → backend:8000
    /ws/       → backend:8000
    /tts/      → tts-service:5500   ← NEW nginx location block
  backend:8000
    calls tts:5500 internally
    calls http://host.docker.internal:11434 (Ollama)
  tts-service:5500  ← NEW container
  redis

[Ollama — host machine, not Docker]
  port 11434, model: llama3.2:3b (or mistral:7b for richer prose)
```

**Player access:** `http://{LAN_IP}` — same as today.
**Audio URLs** in `NarrateMessage`: `/tts/audio/{uuid}.wav` — same-origin relative path, works on LAN.

**Changes to existing files:**

| File | Change |
|---|---|
| `docker-compose.yml` | Add `tts-service` container |
| `nginx.conf` | Add `/tts/` location block proxying to `tts:5500` |
| `backend-engine/api/main.py` | Include narrator router |
| `backend-engine/api/intents/handlers.py` | Fire narration tasks on phase transitions |
| `backend-engine/api/schemas/shared_types.ts` | Add `NarrateMessage`, `NarratorTrigger` |

**Pros:** Zero tunnel complexity. Audio served from localhost, no latency overhead.
**Cons:** Players must be on same WiFi. Ollama installed separately on host machine.

---

### Option B — Hybrid (Vercel Frontend + Local Backend + Cloudflare Tunnel)

```
[Internet]
  Vercel
    frontend-mobile.vercel.app   ← static Vite build, VITE_WS_URL env var
    frontend-display.vercel.app  ← static Vite build, VITE_WS_URL env var

[Cloudflare Tunnel — host machine]
  cloudflared tunnel run werewolf
    → exposes localhost:80 as https://werewolf.yourdomain.com
  Free tier, stable persistent URL (requires CF account + one-time tunnel setup)

[Host Machine — docker compose up]
  nginx:80      (same as Option A, now internet-accessible via tunnel)
  backend:8000
  tts-service:5500
  redis

[Ollama — host machine]
  port 11434
```

**Player access:** `https://frontend-mobile.vercel.app` — any internet connection, no LAN required.
**WebSocket URL:** Frontend reads `import.meta.env.VITE_WS_URL` → `wss://werewolf.yourdomain.com/ws`.
**Audio URLs** in `NarrateMessage`: Must be **absolute** — `https://werewolf.yourdomain.com/tts/audio/{uuid}.wav`. Backend builds this from `PUBLIC_BASE_URL` env var.

**Additional changes vs Option A:**

| File | Change |
|---|---|
| `frontend-display/src/screens/LobbyScreen.tsx` | Replace build-time `HOST_IP` bake-in in QR code join URL with `import.meta.env.VITE_PUBLIC_BASE_URL` |
| `frontend-mobile/src/screens/LobbyScreen.tsx` | Same env var refactor for join URL |
| `backend-engine/engine/config.py` | Add `PUBLIC_BASE_URL` setting for absolute audio URL construction |
| `start.sh` | Add `cloudflared` startup instructions / optional auto-launch |
| Vercel project config | Set `VITE_PUBLIC_BASE_URL=https://werewolf.yourdomain.com` per deployment |

> **Note:** The WebSocket URL in both frontends is **already dynamic** via `window.location.host` (built at runtime in `useGameState.ts`, not `useWebSocket.ts`). No WS URL change is needed for Option B — it resolves correctly through the Cloudflare Tunnel automatically.

**Player UX:** Scan a Vercel QR code instead of a LAN QR code. Otherwise identical.

**Tunnel comparison:**

| Option | Cost | URL stability | Setup friction | Notes |
|---|---|---|---|---|
| **Cloudflare Tunnel** | Free | Stable (named tunnel) | One-time CF account + `cloudflared` install | Recommended |
| ngrok | Free (random URL) / $10/mo (fixed) | Random on free tier | `ngrok http 80` | Easiest, but URL changes each session on free |
| Tailscale Funnel | Free | Stable | Requires all players to install Tailscale | Not suitable for casual party play |

**Pros:** Players join from any network. Host just needs internet.
**Cons:** CF Tunnel one-time setup. Audio latency +50–100 ms via tunnel. Tunnel drop = full disconnect.

---

## §5 — Phase-Gate Plan

| Phase | Deliverable | Blocks |
|---|---|---|
| 0 — Schema | `NarrateMessage` + `NarratorTrigger` in `shared_types.ts` | All phases |
| 1 — TTS Service | `tts-service/` container; Kokoro; `/generate` + `/audio/` | Phase 2 |
| 2 — LLM Integration | `narrator/` package; prompt templates; trigger mapping | Phase 3 |
| 3 — Backend Wiring | Handlers fire narrate tasks; unicast to display | Phase 4 |
| 4 — Display UI | `useNarrator` hook; `NarratorSubtitle` component | — |
| 5A — Option A Deploy | docker-compose + nginx update | — |
| 5B — Option B Deploy | Vercel projects; CF tunnel; `VITE_WS_URL` env var refactor | — |

Phases 5A and 5B are independent. Implement 0–4 once, then choose topology.

---

## §6 — User Stories

| As a | I want to | So that |
|---|---|---|
| Display Client | receive a `narrate` WS message on phase transition | I can play audio and show the narrator subtitle without polling |
| Display Client | have narrator audio auto-unlock via the existing host gesture | I don't need a second click-to-enable |
| Mobile Player (Option B) | join from my home WiFi | I don't need to be on the same network as the host |
| Game Server | fire narration as a non-blocking async task | a slow TTS response never delays phase transitions |
| Game Server | skip narration silently if TTS or LLM is unavailable | the game degrades gracefully without crashing |
| Host (Option B) | set `VITE_WS_URL` as a Vercel env var | I can redeploy pointing to a new tunnel URL without rebuilding locally |

---

## §7 — Open Questions

| # | Question | Impact |
|---|---|---|
| 1 | Which Ollama model — `llama3.2:3b` (~2 GB) or `mistral:7b` (~4 GB)? | Narration quality vs host machine RAM requirement |
| 2 | Should narration block phase advance (subtitle shown, then game proceeds) or run concurrently? | UX timing; concurrent needs no new WS message; blocking needs `narrate_ack` or client timer |
| 3 | Should the Framer (Mastermind role) get a distinct narrator voice? | Kokoro supports multiple voice IDs (`af_bella`, `am_adam`, etc.); adds per-role complexity |
| 4 | Audio format: WAV (large, zero encode) vs MP3 (smaller, requires ffmpeg in container)? | Container size; network overhead on Option B |
| 5 | Should `NarrateMessage` send text-only to dead-player mobile clients? | Accessibility for spectators; increases broadcast surface |
| 6 | Should `NARRATOR_ENABLED=false` be the default, requiring explicit opt-in? | Protects users who don't have Ollama installed from startup errors |
