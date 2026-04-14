---
title: "Why Prebaked Narrator Is Completely Silent"
date: 2026-04-14
branch: feat/prd-008-narrator
commit: b487a31abdb4a0951c847b3051f1106135da9ab8
researcher: bethCoderNewbie
---

## Summary

There are **two independent hard stops** before any audio plays. Either one alone silences the narrator completely.

---

## Root Cause 1 — `NARRATOR_ENABLED` is `false` (primary)

Every narrator call in `handlers.py` is wrapped in:
```python
if get_settings().narrator_enabled:
    asyncio.create_task(narrate(...))
```
Lines: `90, 113, 277, 312, 411, 422, 432, 438`

The default in `docker-compose.yml:72`:
```yaml
NARRATOR_ENABLED: ${NARRATOR_ENABLED:-false}
```
The host `.env` file has **no `NARRATOR_ENABLED` entry** → resolves to `false` → zero narration tasks are ever created.

**Fix:** Add `NARRATOR_ENABLED=true` to `.env`.

---

## Root Cause 2 — Prebaked mode requires DB text, not just WAV files

`triggers.py:48-53`:
```python
if cfg.narrator_mode == "prebaked":
    text = await get_preset_script(trigger_id, eliminated_name)
    if not text:
        return 0                     # ← silent exit
    audio_url, duration_ms = await pick_prebaked(trigger_id)
```

`scripts.py:17-30` queries the `narrator_scripts` Postgres table (migration `a1b2c3d4e5f6`). If the migration wasn't applied or the table is empty, `text = ""` → `return 0` → no audio, no subtitle, no error surfaced.

**Fix:** Ensure `alembic upgrade head` ran against the Postgres container. The entrypoint.sh already does this, but a first-run failure (e.g. Postgres not yet ready) would leave the table missing.

---

## Secondary Issues (would cause partial silence even after fixes above)

| # | Location | Symptom | Cause |
|---|---|---|---|
| 3 | `App.tsx:198` | Subtitle never shows | `NarratorSubtitle` is gated by `audioUnlocked` — display must click "Click to Begin" before any subtitle renders. Audio play() is still attempted, but silently catches errors. |
| 4 | `useNarrator.ts:10` | Audio fails silently | `audio.play().catch(() => {})` — browser autoplay rejection, CSP block, or 404 are all swallowed. No console error surfaced to user. |
| 5 | `triggers.py:84` | Entire pipeline swallowed | `except Exception: logger.debug(...)` — all errors log at DEBUG level only. Silent in default `DEBUG=false` mode. |
| 6 | `connection_manager.py:70-72` | Narration lost | `unicast(game_id, None, ...)` uses `room.get(None)`. If display WS isn't connected at the moment `game_start` fires, `ws is None` and the message is dropped silently. |

---

## Verified Working Path (when both fixes applied)

```
handlers.py:90 → narrate("game_start", ...) [task created]
  → triggers.py:51 → get_preset_script("game_start")  [DB query → text]
  → triggers.py:54 → pick_prebaked("game_start")       [random WAV from /app/backend-engine/api/narrator/audio/]
  → triggers.py:74 → cm.unicast(game_id, None, {"type":"narrate", "audio_url":"/tts/static/game_start_XX.wav", ...})
  → connection_manager.py:74 → ws.send_text(...)       [display WS receives message]
  → useGameState.ts:50-51 → onNarrate(msg)             [dispatched to useNarrator]
  → useNarrator.ts:9 → new Audio("/tts/static/game_start_XX.wav").play()
  → nginx /tts/ → backend /tts/static/ → StaticFiles mount (main.py:105)
  → WAV served ✓
```

The `StaticFiles` mount at `main.py:104-105` is conditional on `_prebaked_dir.exists()` — this is safe because the WAV files are committed and copied into the Docker image via `COPY backend-engine/ ./backend-engine/`.

---

## Verification Commands

```bash
# 1. Confirm NARRATOR_ENABLED is reaching the container
docker compose exec backend printenv NARRATOR_ENABLED
# → must print "true"

# 2. Confirm DB table is seeded
docker compose exec postgres psql -U werewolf -d werewolf -c "SELECT trigger_id, COUNT(*) FROM narrator_scripts GROUP BY trigger_id;"
# → should show 9 trigger_ids with rows each

# 3. Confirm static route is reachable
curl -I http://localhost:8000/tts/static/game_start_00.wav
# → 200 OK with Content-Type: audio/wav

# 4. Confirm narrator fires (tail backend logs at DEBUG)
DEBUG=true docker compose up backend
# → look for "Narrator pipeline failed" or absence of errors
```
