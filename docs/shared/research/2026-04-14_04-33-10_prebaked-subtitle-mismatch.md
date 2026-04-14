---
title: "Prebaked Subtitle/Audio Mismatch — Root Cause & Fix"
date: 2026-04-14
branch: feat/prd-008-narrator
commit: 976bf075e5690c0ddc8bd4b6c75959ae6d8e467e
researcher: bethCoderNewbie
---

## Root Cause

Two independent `random.choice()` calls in `triggers.py:51-54`:

```python
# prebaked mode
text = await get_preset_script(trigger_id, eliminated_name)  # random DB row
audio_url, duration_ms = await pick_prebaked(trigger_id)     # random WAV file
```

`scripts.py:28` — `random.choice(scripts)` over all DB rows for the trigger.  
`tts.py:98` — `random.choice(candidates)` over sorted WAV files for the trigger.

The two selections are entirely decoupled. The subtitle shown is rarely the line being spoken.

---

## Why Index-Based Correlation Works

WAV files are named `{trigger_id}_{index:02d}.wav` (`game_start_00.wav` … `game_start_19.wav`).  
Seed rows were inserted in the same positional order in both migration files (`a1b2c3d4e5f6` and `b2c3d4e5f6a7`).

So WAV index `N` corresponds to the `N`th DB row (sorted by `id`) for that `trigger_id`.  
Total: 181 files on disk (180 WAVs + 1 `.gitkeep`), 9 triggers × 20 lines each.

---

## Fix: Pick Index Once, Pass to Both

### 1. `tts.py` — `pick_prebaked()` returns index alongside URL

```python
async def pick_prebaked(trigger_id: str) -> tuple[str, int, int]:
    """Returns (audio_url, duration_ms, chosen_index)."""
    cfg = get_narrator_settings()
    audio_dir = Path(cfg.narrator_prebaked_dir)
    candidates = sorted(audio_dir.glob(f"{trigger_id}_*.wav"))
    if not candidates:
        raise FileNotFoundError(f"No prebaked audio for '{trigger_id}' in {audio_dir}")
    idx = random.randrange(len(candidates))
    chosen = candidates[idx]
    with wave.open(str(chosen)) as wf:
        framerate = wf.getframerate()
        bytes_per_frame = wf.getnchannels() * wf.getsampwidth()
    data_bytes = chosen.stat().st_size - 44
    duration_ms = int(max(data_bytes, 0) / bytes_per_frame / framerate * 1000)
    return f"/tts/static/{chosen.name}", duration_ms, idx
```

### 2. `scripts.py` — `get_preset_script()` accepts optional `index`

```python
async def get_preset_script(
    trigger_id: str,
    eliminated_name: str | None = None,
    index: int | None = None,
) -> str:
    async with get_session_factory()() as session:
        rows = await session.execute(
            select(NarratorScript)
            .where(NarratorScript.trigger_id == trigger_id)
            .order_by(NarratorScript.id)
        )
        scripts = rows.scalars().all()
    if not scripts:
        return ""
    chosen = scripts[index % len(scripts)] if index is not None else random.choice(scripts)
    return chosen.text.format(eliminated_name=eliminated_name or "a player")
```

### 3. `triggers.py` — prebaked block uses shared index

```python
if cfg.narrator_mode == "prebaked":
    audio_url, duration_ms, idx = await pick_prebaked(trigger_id)
    text = await get_preset_script(trigger_id, eliminated_name, index=idx)
    if not text:
        return 0
```

---

## Impact on Other Modes

`get_preset_script()` is also called in `auto` and `static` modes as a fallback (lines 67). Those callers pass no `index`, so they continue with `random.choice()` — no change in behaviour.

---

## Files to Change

| File | Lines | Change |
|---|---|---|
| `backend-engine/api/narrator/tts.py` | 86–107 | Return `idx` from `pick_prebaked()` |
| `backend-engine/api/narrator/scripts.py` | 17–30 | Add `index` param; use `ORDER BY id` + offset |
| `backend-engine/api/narrator/triggers.py` | 48–54 | Unpack `idx`; pass to `get_preset_script` |

---

## Verification

Play a full game with `NARRATOR_ENABLED=true NARRATOR_MODE=prebaked` and confirm the subtitle text matches the spoken audio on every phase transition.
