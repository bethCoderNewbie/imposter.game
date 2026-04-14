# ADR-023: Use Web Audio API for Voting Countdown Beep

**Status:** Accepted
**Date:** 2026-04-14

## Context

The voting phase (PRD-012 §2.1) needs a per-second tick sound for the final 10 seconds of the
`day_vote` timer. Two options were evaluated:

1. **MP3 file** — pre-recorded tick played via `<audio>` element or `new Audio()`
2. **Web Audio API oscillator** — programmatically generated tone, no asset required

The display client already uses HTML5 `<audio>` for night ambient, rooster, and game-over sounds
(all looping or one-shot files). The countdown beep is different: it fires up to 10 times in rapid
succession, one per second, with a pitch change on the final second.

## Decision

Use the Web Audio API (`AudioContext.createOscillator()`) for the countdown beep.

A lazy-initialised `AudioContext` is stored in a `useRef` inside `useCountdownBeep`. On each new
`secondsRemaining` value ≤ 10, a short oscillator burst (120 ms, exponential gain ramp) is
scheduled at `ctx.currentTime`. The final second uses 880 Hz; all others use 440 Hz.

## Consequences

**Positive:**
- No audio asset to manage, commit to source control, or serve from nginx
- Pitch and envelope are code-controlled — the final-second emphasis requires no separate file
- Zero latency on first play (no fetch/decode pipeline)
- `AudioContext` is supported in all target browsers (Chrome, Safari, Firefox, Edge)
- Consistent with the `audioUnlocked` gate already used for MP3 playback

**Negative:**
- Synthetic sine-wave tone; replacing it with a recorded sound requires a code change, not just
  swapping an asset file
- Requires lazy `AudioContext` initialisation — must not be constructed before a user gesture
  (already handled: `audioUnlocked` is only set true after the "Click to Begin" interaction)

## Alternatives Rejected

**MP3 tick file:** Adds a binary asset that is difficult to diff, requires placement in
`public/audio/`, and introduces a decode delay on first play. This delay could cause the first tick
(at exactly 10 seconds) to fire noticeably late. Also requires an additional HTTP request unless
preloaded, which complicates the preload manifest.
