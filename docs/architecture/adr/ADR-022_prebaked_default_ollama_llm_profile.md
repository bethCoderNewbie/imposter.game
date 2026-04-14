# ADR-022 — Default NARRATOR_MODE=prebaked + Gate Ollama Behind `llm` Profile

**Status:** Accepted
**Date:** 2026-04-13
**Related:** ADR-021 (Pre-baked Narrator Audio), PRD-008 (Narrator pipeline)

---

## Context

ADR-021 introduced `narrator_mode = "prebaked"` and committed 181 WAVs to the repo. However,
the default `NARRATOR_MODE` remained `"auto"`, meaning every `docker compose up` (and every
`start.sh` invocation) unconditionally started the `ollama` service, which:

1. Pulls a ~2 GB model on first run
2. Holds a persistent container even when all audio is served from disk
3. Adds a `depends_on: ollama` constraint to the `backend` service, serialising startup

In `prebaked` mode the backend reads WAVs from `backend-engine/api/narrator/audio/`, resolves
subtitle text via `get_preset_script()` at trigger time, and has zero LLM or TTS runtime
requirements. Keeping `"auto"` as the default imposed those dependencies on every operator who
had not explicitly opted in.

---

## Decision

### 1. Change the Python default (`config.py`)

```python
# before
narrator_mode: str = "auto"   # "auto" | "live" | "static" | "prebaked"

# after
narrator_mode: str = "prebaked"   # "prebaked" | "auto" | "live" | "static"
```

### 2. Gate Ollama behind a `llm` Compose profile

Add `profiles: ["llm"]` to both the `ollama` and `ollama-pull` services in
`docker-compose.yml`. These services are now excluded from the default
`docker compose up` and must be activated explicitly:

```
docker compose --profile llm up
```

`docker-compose.gpu.yml` requires no change — profile inheritance from the base service
applies automatically when the files are merged by `start.sh`.

### 3. Change the Compose env default

```yaml
# before
NARRATOR_MODE: ${NARRATOR_MODE:-auto}

# after
NARRATOR_MODE: ${NARRATOR_MODE:-prebaked}
```

### 4. Conditional profiles in `start.sh`

`start.sh` reads `NARRATOR_MODE` from the shell environment or `.env` file and sets
`COMPOSE_PROFILES` only when LLM synthesis is required:

```bash
NARRATOR_MODE="${NARRATOR_MODE:-prebaked}"
if [[ "$NARRATOR_MODE" == "auto" || "$NARRATOR_MODE" == "live" ]]; then
  COMPOSE_PROFILES="--profile llm --profile tts"
else
  COMPOSE_PROFILES=""   # Ollama + Kokoro skipped
fi
docker compose $COMPOSE_FILES $COMPOSE_PROFILES up --build "$@"
```

`prebaked` and `static` modes start neither Ollama nor Kokoro. `auto` and `live` modes start
both (Kokoro was already behind `profiles: ["tts"]` per ADR-021).

### 5. Document in `.env.example`

`NARRATOR_MODE=prebaked` added after `NARRATOR_VOICE` in the Narrator block.

---

## Consequences

**Positive:**
- `docker compose up` no longer pulls a 2 GB model or starts Ollama on fresh installs
- Default stack starts faster and with fewer containers
- Operators who want LLM narration opt in explicitly via `NARRATOR_MODE=auto` or
  `NARRATOR_MODE=live`; the `--profile llm` flag is added automatically by `start.sh`

**Negative:**
- Operators upgrading from a previous install where `NARRATOR_MODE` was unset will silently
  switch from `auto` to `prebaked`. If they relied on LLM narration they must set
  `NARRATOR_MODE=auto` in their `.env`
- `ollama` no longer appears in `docker compose ps` by default, which may surprise operators
  who assume all services are always present

**Neutral:**
- `narrator_mode = "auto"` and `"live"` are fully supported — behaviour unchanged when
  explicitly selected
- `docker-compose.gpu.yml` is unaffected
- `NarratorSubtitle` safety is unchanged: in `prebaked` mode `triggers.py` returns early if
  `get_preset_script()` finds no scripts; the component only renders when `text` is non-null

---

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| Keep default `"auto"`, add opt-out `NARRATOR_LLM=false` flag | Two separate knobs for the same concern; more confusing than a single `NARRATOR_MODE` |
| Remove `ollama` from Compose entirely | Breaks `auto` and `live` modes for operators who want them |
| Keep `"auto"` default, just document Ollama overhead | Does not fix the unconditional 2 GB pull on new installs |

---

## Related

- `backend-engine/api/narrator/config.py` — `narrator_mode` default
- `docker-compose.yml` — `profiles: ["llm"]` on `ollama` + `ollama-pull`; `NARRATOR_MODE` env default
- `start.sh` — conditional `$COMPOSE_PROFILES` injection
- `.env.example` — `NARRATOR_MODE=prebaked`
- ADR-021 — original prebaked mode and `profiles: ["tts"]` for Kokoro
