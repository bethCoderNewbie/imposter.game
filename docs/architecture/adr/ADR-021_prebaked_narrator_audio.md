# ADR-021 — Pre-baked Narrator Audio

**Status:** Accepted
**Date:** 2026-04-13
**Related:** PRD-008 (Narrator pipeline)

---

## Context

The narrator pipeline (PRD-008) requires two heavy runtime services:

- **Ollama** — 2 GB LLM model for dynamic narration text
- **Kokoro** — GPU TTS container for speech synthesis

On CPU-only hosts or zero-dependency dev runs, both services are a barrier to running the full game stack. However, the 9 narrator triggers map to ~20 static seed lines each in the `narrator_scripts` DB table — these texts are fixed at migration time and can be converted to audio once and committed to the repo.

Two triggers (`vote_elimination`, `player_eliminated`) contain an `{eliminated_name}` template placeholder. A pre-baked WAV cannot encode a runtime player name, so these files are generated with the placeholder substituted to `"a player"`. The subtitle displayed to players uses the real eliminated player's name drawn from the DB preset at runtime.

---

## Decision

Add `narrator_mode = "prebaked"` as a fourth operating mode alongside `auto`, `live`, and `static`.

**Audio generation (one-time, developer machine):**
- Script: `scripts/prebake_tts.py`
- Voice: Fish-Speech voice cloning with Rickman reference WAVs (`rickman_clean_raw/`)
- Output: `backend-engine/api/narrator/audio/{trigger_id}_{nn:02d}.wav` (180 files)
- Committed to the repo; no runtime GPU or LLM dependency

**Runtime serving:**
- FastAPI mounts `StaticFiles` at `/tts/static/` from the `audio/` directory on startup (conditional on directory existence)
- `pick_prebaked(trigger_id)` selects a random WAV for the trigger
- Subtitle (`text`) uses real eliminated name; audio says "a player" for dynamic triggers

**Docker Compose:**
- `tts` service moved behind `profiles: ["tts"]` — excluded from default `docker compose up`
- Operators using live Kokoro: `docker compose --profile tts up`

---

## Consequences

**Positive:**
- Zero runtime GPU, LLM, or TTS dependency for narration in prebaked mode
- Deterministic, predictable audio quality (baked once, served forever)
- Simpler dev onboarding — `docker compose up` just works with narration enabled

**Negative:**
- ~150–200 MB binary assets added to the repo (Fish-Speech WAV output)
- Audio/subtitle name divergence for `vote_elimination` and `player_eliminated` triggers — audio says "a player", subtitle shows the real name. This is intentional and documented here.
- WAVs must be regenerated if seed texts change (migration edit → re-run script)

**Neutral:**
- `narrator_mode = "auto"` (default) is unchanged — Ollama + Kokoro path unaffected
- `narrator_mode = "static"` still works (Kokoro required, LLM optional)

---

## Related

- `backend-engine/api/narrator/config.py` — `narrator_prebaked_dir` setting
- `backend-engine/api/narrator/tts.py` — `pick_prebaked()` function
- `backend-engine/api/narrator/triggers.py` — `"prebaked"` branch in `narrate()`
- `backend-engine/api/main.py` — conditional `StaticFiles` mount
- `scripts/prebake_tts.py` — one-time generation script
- `docs/ops/runbook.md` — operator instructions
