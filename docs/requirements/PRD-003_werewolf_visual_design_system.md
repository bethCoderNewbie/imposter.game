# PRD-003: Werewolf — Visual Design System

## §1. Context & Purpose

This document is the **single source of truth** for Werewolf's visual token vocabulary. It is a design system reference — not a feature PRD. All component PRDs (PRD-002+) cross-reference this document for typography values, animation keyframes, color tokens, and layer architecture. Do not embed design system values inline in other PRDs; reference the section here instead.

**Derived from:** Brass Birmingham's production-proven TV display system (ADR-014, `project_display_scaling_config.md`). Adapted for Werewolf's DOM-only architecture (no PixiJS, per ADR-001).

**Audience:** Frontend developers implementing Display and Mobile React components.

---

## §2. Typography System

### §2.1 Formula

```
target_px ÷ 10.8 ≈ vmin
```

Calibrated at 1080p (the reference display resolution for an 80" TV at 8–10 feet). At 1080p, `1vmin = 10.8px`. Above 1080p, text grows proportionally. Below 1080p, the `clamp` minimum prevents collapse.

All Display text MUST use `clamp(minPx, Xvmin, maxPx)`. Never use fixed `px` for HUD text.

### §2.2 Display Typography Reference Table

| Element | vmin | ~px @1080p | Full `clamp()` |
|---------|------|-----------|----------------|
| Night phase timer | 11.1vmin | 120px | `clamp(64px, 11.1vmin, 160px)` |
| Day discussion timer | 7.4vmin | 80px | `clamp(48px, 7.4vmin, 96px)` |
| Winning headline | 8.3vmin | 90px | `clamp(48px, 8.3vmin, 120px)` |
| Room code (Lobby) | 7.4vmin | 80px | `clamp(40px, 7.4vmin, 96px)` |
| Phase label (Discussion / Voting) | 2.8vmin | 30px | `clamp(20px, 2.8vmin, 36px)` |
| Narrative text (Night carousel) | 3.1vmin | 33px | `clamp(22px, 3.1vmin, 44px)` |
| Round label ("Day 2") | 2.2vmin | 24px | `clamp(16px, 2.2vmin, 30px)` |
| Player name under avatar | 2.0vmin | 22px | `clamp(14px, 2.0vmin, 26px)` |
| Elimination timeline event | 2.4vmin | 26px | `clamp(16px, 2.4vmin, 32px)` |
| Role badge (Game Over reveal) | 1.7vmin | 18px | `clamp(12px, 1.7vmin, 22px)` |
| Vote tally badge | 1.9vmin | 20px | `clamp(12px, 1.9vmin, 24px)` |
| Night action progress indicator | 1.9vmin | 20px | `clamp(14px, 1.9vmin, 26px)` |

### §2.3 Mobile Typography

Mobile screens are held at 12–18 inches; vmin is less critical but clamp is still preferred. All interactive labels (role name, action header, player list) should use `clamp` with a minimum of `14px` and a vmin coefficient appropriate for portrait viewport. Mobile-specific values are implementation decisions — this table covers Display only.

---

## §3. Animation Vocabulary

Three named keyframes are shared across both clients. Reference these by name in PRD component specs — do not define one-off animations unless strictly necessary.

### §3.1 `night-enter` — Night phase background entrance

Used on: `NightScreen` root, `NightActionShell` (Mobile).

```css
@keyframes night-enter {
  0%   { opacity: 0; background-color: #000000; }
  50%  { opacity: 0; background-color: #000000; }
  100% { opacity: 1; }
}
/* animation: night-enter 2s ease-in-out forwards; */
```

Routes through black intermediate, then fades up to the night substrate. Duration: 2s.

### §3.2 `reveal-flicker` — Dramatic text reveal

Used on: Night Resolution death announcement, Game Over timeline entries.

Derived from BB's `NodeContextMenu.css` glow keyframe.

```css
@keyframes reveal-flicker {
  0%   { opacity: 0; }
  3%   { opacity: 1; }
  10%  { opacity: 0; }
  12%  { opacity: 0.7; }
  16%  { opacity: 0.3; }
  100% { opacity: 1; }
}
/* animation: reveal-flicker 1.2s cubic-bezier(0.5, 1, 0.89, 1) forwards; */
```

For staggered sequences (e.g., timeline entries): `animation-delay: N * 600ms`.

### §3.3 `vote-majority-pulse` — Vote target majority indicator

Used on: `VoteWeb` player avatar when player holds >50% of active votes.

Derived from BB's `SlotLayer.tsx` gold pulse pattern (3s, opacity 0.20 → 0.85 cycle).

```css
@keyframes vote-majority-pulse {
  0%   { box-shadow: 0 0 0 3px rgba(229, 62, 62, 0.20); }
  50%  { box-shadow: 0 0 0 8px rgba(229, 62, 62, 0.85); }
  100% { box-shadow: 0 0 0 3px rgba(229, 62, 62, 0.20); }
}
/* animation: vote-majority-pulse 3s ease-in-out infinite; */
```

### §3.4 Timing Function Standards

| Context | Timing function | Rationale |
|---------|----------------|-----------|
| Phase transitions | `ease-in-out` | Smooth bidirectional |
| Entrance animations | `cubic-bezier(0.5, 1, 0.89, 1)` | Snappy entrance (from BB) |
| Filter transitions (grayscale) | `ease-in-out` | Smooth death reveal |
| Timer color threshold | `linear` 0.5s | Immediate legibility shift |

---

## §4. Layer Architecture

Two-layer rendering model. Mirrors BB's `BoardBackgroundLayer` (static DOM substrate) / `Stage` (dynamic PixiJS entities) split — adapted here for pure DOM/CSS.

| Layer | Technology | Game-state dependency | Examples |
|-------|-----------|----------------------|---------|
| **Substrate** | CSS class swap on `<body>` or root `<div>` | None | Night gradient, day gradient, grain texture |
| **Dynamic overlay** | React components, re-render on `state_update` | Yes | Timer, player grid, vote-web SVG, narrative carousel, action progress |

**Rule:** The substrate layer must never read from `StrippedDisplayState`. Phase transitions fire by swapping a CSS class (e.g., `.phase-night`, `.phase-day`) on the root element — not by injecting inline styles from component state.

### §4.1 Substrate Specifications

**Night substrate** (`.phase-night`):
```css
background: radial-gradient(ellipse at 50% 20%, #141b2e 0%, #0a0e1a 60%, #060810 100%);
```
Grain overlay (SVG feTurbulence, same technique as BB `boardRenderer.ts`):
```css
.night-grain {
  opacity: 0.03;
  mix-blend-mode: screen;
  pointer-events: none;
}
```

**Day substrate** (`.phase-day`):
```css
background-image: linear-gradient(to top, #dad4ec 0%, #dad4ec 1%, #f3e7e9 100%);
```
Grain overlay:
```css
.day-grain {
  opacity: 0.015;
  mix-blend-mode: multiply;
  pointer-events: none;
}
```

**Night Resolution substrate** (`.phase-night-resolution`):
```css
background-image: linear-gradient(to right, #434343 0%, black 100%);
```
No grain — the high-contrast reveal scene needs a clean backdrop.

---

## §5. Color Semantic Tokens

Define as CSS custom properties on `:root`. Reference tokens in components — never hardcode hex values.

```css
:root {
  /* Backgrounds */
  --night-bg-deep:       #060810;
  --night-bg-mid:        #0a0e1a;
  --night-bg-glow:       #141b2e;

  /* Timer states */
  --timer-default:       #ffffff;
  --timer-warning:       #f6ad55;   /* ≤30s */
  --timer-critical:      #fc8181;   /* ≤10s */

  /* Team colors */
  --wolf-primary:        #e53e3e;
  --village-primary:     #edc94b;

  /* Role colors */
  --role-wolf:           #e53e3e;
  --role-seer:           #805ad5;
  --role-doctor:         #38a169;
  --role-villager:       #718096;

  /* Dead state */
  --eliminated-filter:   grayscale(1);

  /* Glass panel (dark overlay menus) — from BB NodeContextMenu */
  --glass-bg:            linear-gradient(-20deg, #0a1923 0%, #1a1529 100%);
  --glass-border:        rgba(255, 255, 255, 0.15);
  --glass-blur:          blur(24px);
}
```

### §5.1 Role Color Usage

| Token | Role | Used on |
|-------|------|---------|
| `--role-wolf` | Werewolf | Role reveal background, wolf-team game over splash, vote ring |
| `--role-seer` | Seer | Role reveal background, seer badge |
| `--role-doctor` | Doctor | Role reveal background, doctor badge |
| `--role-villager` | Villager | Role reveal background, villager badge |
| `--village-primary` | Village team | Village-win game over headline accent |

---

## §6. HUD Positioning Conventions

All HUD panels use `vmin`-based positioning. Never use fixed `px` offsets for panel placement. Derived from BB's `ActionFeed` / `DeckCounter` positioning pattern.

| Panel slot | CSS | Example component |
|-----------|-----|------------------|
| Top-left | `top: 1.1vmin; left: 1.1vmin` | Action progress badge |
| Top-right | `top: 1.1vmin; right: 1.1vmin` | Player count (Lobby), round label |
| Top-center | `top: 1.1vmin; left: 50%; transform: translateX(-50%)` | Night timer, day timer |
| Bottom-center | `bottom: 1.1vmin; left: 50%; transform: translateX(-50%)` | Phase label, narrative text |

**Overflow guard:** Any panel that could overflow the viewport at small sizes must clamp its position with a minimum 8px margin from each edge. Reference: BB's `clampToViewport()` utility pattern (`NodeContextMenu.tsx:54`).

---

## §7. Anti-Patterns

Documented failures from Brass Birmingham (ADR-014) adapted for Werewolf.

1. **No fixed-px HUD text.** `font-size: 120px` on a timer renders at a correct size on one screen and is unreadable on another. Always `clamp(minPx, Xvmin, maxPx)`.

2. **No game-state logic in the substrate.** The background gradient must not be controlled by a React component reading `phase` from state. Use a CSS class on the root element that a top-level effect swaps — the substrate is static once the class is set.

3. **No single `transform: scale()` wrapper for the entire HUD.** Wrapping all HUD elements in a scaled container causes them to shrink on large screens (where scale < 1) and balloon on small screens. Each element scales independently via its own `vmin` value.

4. **No Canvas / PixiJS.** Werewolf Display is DOM-only. Vote-web connections are SVG `<line>` elements. Phase transitions are CSS keyframes. Introduce Canvas only if a specific rendering requirement demonstrably cannot be met in DOM.

5. **No client-owned timers.** Never use `setInterval(tick, 1000)` as the authoritative countdown source. Derive the displayed countdown from `(state.timer_ends_at - Date.now())` on every render tick. The server `timer_ends_at` timestamp is the single source of truth.

6. **No role data derived from Display-visible signals.** Do not compute or display "wolves haven't acted yet" from aggregate counts. The Display only knows N of M players have acted — role identity is never inferrable from what the Display receives.
