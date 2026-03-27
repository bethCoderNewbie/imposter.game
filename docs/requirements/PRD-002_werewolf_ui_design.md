# PRD-002: Werewolf — Display TV & Mobile UX/UI Design

## §1. Context & Problem

PRD-001 defines the game state machine and server architecture. This document defines the **visual and interaction design** for both client surfaces: the shared Display TV and the individual Mobile Phone.

The UI has two competing constraints that must be resolved in tandem:

1. **The Display TV** must be readable from 8–10 feet across a dark living room. It must build tension, convey phase changes dramatically, and keep spectators (and the eliminated) engaged.
2. **The Mobile Phone** must protect role secrecy. An observant neighbor should never be able to infer a player's role by watching their screen from a few feet away — this is the primary anti-cheat surface.

Both clients derive all state from `StrippedState` WebSocket broadcasts (defined in PRD-001 §2.6). Neither client owns timer state or game logic.

---

## §2. Display TV UX/UI

### §2.1 Design Principles

- **Readable at distance:** All Display text uses `clamp(minPx, Xvmin, maxPx)` — never fixed `px`. Formula: `target_px ÷ 10.8 ≈ vmin` (1080p baseline). See PRD-003 §2 for the full typography reference table.
- **Theme-first:** Dark, moonlit village aesthetic. The UI is the automated Game Master — it should feel theatrical, not like a webapp.
- **No role data, ever:** The Display receives `StrippedDisplayState` with all `role` and `alignment` fields removed. The UI must never infer or display roles from indirect signals (e.g., do not show "3/3 wolves have voted").
- **Static substrate / dynamic overlay:** The background (night gradient, day gradient, grain) is a baked CSS layer with no game-state dependency — class swap on root only. Animated game state (timer, player grid, vote-web) overlays on top. Reference: PRD-003 §4.

### §2.2 Pre-Game Lobby Screen

**Layout:**
- Center: large QR code (minimum 300×300px, high-contrast on dark background) + short join URL (e.g., `wolf.local/join`) + 4-letter room code in bold.
- Below QR: live player roster — as each player joins, their avatar "pops in" with a subtle entrance animation around a **village campfire** illustration.
- Top-right: player count badge (e.g., `5 / 10 joined`).
- Bottom: "Waiting for host to start..." status line.

**Behavior:**
- Avatar pop-in animation fires on each `state_update` where a new `player_id` appears in `players[]`.
- Avatar positions are laid out in a circular arc around the campfire. New arrivals fill clockwise from the top.

### §2.3 Night Phase Screen

**Layout:**
- Full-screen dark background substrate: `radial-gradient(ellipse at 50% 20%, #141b2e 0%, #0a0e1a 60%, #060810 100%)` + grain overlay `opacity: 0.03, mix-blend-mode: screen` (PRD-003 §4.1). Moon illustration top-center overlaid.
- Large countdown timer in the center: white digits, monospace font, `clamp(64px, 11.1vmin, 160px)`. Format: `MM:SS`.
- Below timer: rotating atmospheric narrative text `clamp(22px, 3.1vmin, 44px)` (cycles every 8 seconds):
  - `"The village sleeps..."`
  - `"Something stirs in the dark..."`
  - `"The Werewolves are hunting..."`
  - `"The Seer peers into the shadows..."`
  - `"A guardian watches over the village..."`
- Bottom-left: aggregate action progress indicator `clamp(14px, 1.9vmin, 26px)` — `"Night actions: 3 / 4"` using a generic label (not role-specific). This tells the room the game is progressing without revealing who has acted.
- Audio: ambient loop — crickets, low wind, distant howl. Triggered on phase enter. Volume: 40% default (host-configurable).

**Behavior:**
- On phase enter: `night-enter` keyframe (PRD-003 §3.1) — 2s fade routing through black intermediate.
- Timer color: default `#ffffff` → `#f6ad55` (amber, 0.5s transition) at ≤30s → `#fc8181` (red, 0.5s transition) + `text-shadow: 0 0 12px currentColor` at ≤10s.
- When all actions submitted early (auto-advance): timer immediately fades out, then transition to Night Resolution.

### §2.4 Night Resolution Interstitial

A 3–4 second dramatic beat between Night and Day phases.

**Layout:**
- Full black screen `background-image: linear-gradient(to right, #434343 0%, black 100%)`.
- Centered text entrance: `reveal-flicker` keyframe 1.2s (PRD-003 §3.2). Text: `"Dawn breaks over the village..."` (no deaths) or `"A body is discovered..."` (one or more killed).
- If a player was killed: their avatar slides into center frame with `animation: claw-slide-in 1.2s ease-out, animation-delay: 600ms`; claw-mark overlay fades in over 1.2s.
- Audio: rooster crow SFX, then silence before Day music begins.

**Behavior:**
- Duration: 4 seconds fixed (non-skippable). Gives the room time to react before voting begins.
- Triggered by the server transitioning from `night` → `day` with `elimination_log` entries present.

### §2.5 Day Phase Screen

**Layout:**
- Background substrate: `background-image: linear-gradient(to top, #dad4ec 0%, #dad4ec 1%, #f3e7e9 100%)` + grain overlay `opacity: 0.015, mix-blend-mode: multiply` (PRD-003 §4.1). Distinct visual contrast from Night.
- Top-center: round label `clamp(16px, 2.2vmin, 30px)` + discussion timer `clamp(48px, 7.4vmin, 96px)`.
- **Village Grid:** Responsive CSS grid of all players (living + dead). Each cell:
  - Living: full-color avatar, display name `clamp(14px, 2.0vmin, 26px)` below.
  - Eliminated: avatar `transition: filter 0.5s ease-in-out` to `filter: grayscale(1)`, name in gray, tombstone icon overlay.
- Bottom: phase label `clamp(20px, 2.8vmin, 36px)` — `"Discussion"` during timer, transitions to `"Voting"` when timer expires or host advances.

**Voting Overlay (Day → Vote sub-phase):**
- When `phase == "day_vote"`, animate SVG lines from each voter's avatar to their target's avatar.
- Line color: neutral gray initially; thickens as more votes pile onto a target.
- A player with >50% of votes: `vote-majority-pulse` keyframe 3s infinite (PRD-003 §3.3) — red box-shadow cycle `0.20 → 0.85 → 0.20` opacity.
- Vote tally badge `clamp(12px, 1.9vmin, 24px)` on each avatar.

**Behavior:**
- SVG vote-web is revealed **all at once** when voting closes (server transitions `phase` from `day_vote` to resolution). Lines are not drawn live as individual votes arrive — the full vote picture is revealed simultaneously for dramatic effect.
- Eliminated player animation: when a day vote resolves, the eliminated player's avatar plays `filter: grayscale(1)` + tombstone drop over 500ms.

### §2.6 Game Over Screen

**Layout:**
- Full-screen splash with winning team color:
  - Villager win: gold/warm theme. Winning headline `clamp(48px, 8.3vmin, 120px)`: `"THE VILLAGE SURVIVES"`.
  - Wolf win: red/dark theme. Winning headline `clamp(48px, 8.3vmin, 120px)`: `"THE WOLVES DEVOUR THE VILLAGE"`.
- Below headline: all player avatars revealed with role badge overlays `clamp(12px, 1.7vmin, 22px)` (Villager, Werewolf, Seer, Doctor).
- **Elimination Timeline** scrolls below. Event text `clamp(16px, 2.4vmin, 32px)`. One per row:
    - `"Night 1 — Alex was eliminated by the Wolves"`
    - `"Night 2 — Jordan was saved by the Doctor"`
    - `"Day 2 — Sam was voted out (was: Villager)"`
    - `"Night 3 — Chris (Werewolf) voted to kill Taylor"`
- Audio: victory fanfare (Villager) or ominous howl chord (Wolf).

**Behavior:**
- Timeline entries: `reveal-flicker` keyframe (PRD-003 §3.2) with `animation-delay: N * 600ms` stagger per entry.
- Events are constructed server-side from `elimination_log` + `night_actions` history and sent in `game_over` state payload.

### §2.7 Typography Reference

All Display typography values (vmin clamps, ~px at 1080p) are defined in **PRD-003 §2**. Do not duplicate values here — reference that table when implementing any Display component.

### §2.8 Anti-Patterns

See **PRD-003 §7** for the full list. Critical prohibitions for Display:

1. **No fixed-px text** — always `clamp(minPx, Xvmin, maxPx)`.
2. **No game-state logic in the background substrate** — night/day class swap on root only.
3. **No single `transform: scale()` HUD wrapper** — each layer scales via vmin independently.
4. **No Canvas / PixiJS** — DOM-only; SVG for vote-web, CSS for animations.

---

## §3. Mobile Phone UX/UI

### §3.1 Design Principles

- **Secrecy first:** At a glance from 2 feet away, every player's screen must look identical during the night phase. No bright colors, no visible text, no role-specific icons visible from the side.
- **Clarity for the holder:** When the player IS looking at their own screen, role and action UI must be immediately legible without reading instructions.
- **Anti-cheat by design:** Interaction patterns (haptics, decoy tasks) obscure who is acting from physical observers.

### §3.2 Onboarding & Lobby

**Layout:**
- Single-column form, vertically centered:
  1. Name input field (max 16 chars, auto-focused on load).
  2. Avatar upload: a tap target that opens the device image picker (`<input type="file" accept="image/*">`). Selected image is cropped to a square and uploaded to the server as the player's avatar. No preset illustrated set; no live camera.
  3. `"Join Game"` CTA button (disabled until name entered).
- After joining: lobby waiting screen showing all joined players as a scrollable list with their avatars. Live-updates on `state_update`.
- Host device: additional `"Start Game"` button appears when ≥5 players have joined.

### §3.3 Role Reveal

**Layout:**
- Full-screen dark background.
- Center: large "HOLD TO REVEAL" button (rounded rectangle, 80% screen width).
- While held (`pointerdown`):
  - Background transitions to role color (e.g., red for Wolf, gold for Seer, green for Villager, blue for Doctor).
  - Role name in large bold type: `"YOU ARE THE WEREWOLF"`.
  - Role icon (SVG illustration) centered below text.
  - Bullet list of role abilities (3 lines max):
    - *"Each night, vote with your pack to eliminate one villager."*
    - *"You win when wolves outnumber the village."*
    - *"You know who your fellow wolves are."*
- On release (`pointerup` / `pointercancel`): screen immediately blanks back to dark.

**Behavior:**
- Role data is only rendered into the DOM while the button is held — not in the HTML while hidden. This prevents inspect-element cheating.
- `confirm_role_reveal` intent sent to server after first hold (≥1 second). Does not require second tap.
- Haptic: single 200ms vibration on reveal, single 100ms vibration on blank.

### §3.4 Night Phase

**The Fake-Out Constraint:** All roles — Wolves, Seer, Doctor, and Villager — must display a screen that looks visually identical from 2 feet away. The screen is dark for everyone.

**Universal shell (all roles):**
- Full-screen dark background `background-image: linear-gradient(to right, #434343 0%, black 100%);` (same as Display TV night).
- Top-center: small moon icon + `"Night"` label in dim white.
- Center: role-specific content (described below) — but the *silhouette* of the content area is the same rectangle for all roles.

**Wolves — Kill Vote:**
- Header (small, dim): `"Choose your target"`
- Scrollable list of living players (excluding self and wolf teammates): avatar + name.
- Tap to select: selected player gets a subtle red highlight (not bright enough to be visible at distance).
- `"Confirm"` button at bottom. Disabled until a target selected.
- Haptic: 300ms pattern on confirm.
- After submit: `"Waiting for your pack..."` idle state.

**Seer — Peek:**
- Header (small, dim): `"Choose who to investigate"`
- Same scrollable living-player list as Wolves.
- Tap to select + `"Confirm"` button.
- After submit: result shown inline — `"Jordan is... NOT a Wolf"` or `"Jordan is... a WOLF"` in dim green/red text.
- Previous round peeks listed below current result (persistent across rounds for Seer only).
- Haptic: 300ms pattern on confirm.

**Doctor — Protect:**
- Header (small, dim): `"Choose who to protect"`
- Same scrollable living-player list (including self). Cannot re-select last round's target (grayed out).
- Tap to select + `"Confirm"` button.
- After submit: `"Protection active"` idle state.
- Haptic: 300ms pattern on confirm.

**Villager / Mayor / Jester — Archive Puzzle:**

This is the Archives puzzle system (`roles.json` `archivePuzzleSystem`). The server sends a `puzzle_state` object at night-phase start; the player solves it and submits a `submit_puzzle_answer` intent; a correct solve triggers a `HintPayload` unicast.

- Header (small, dim): `"The Archives await. Solve the puzzle to earn a clue."`
- Center: puzzle content area — same glass-panel rectangle dimensions as wolf-vote list (anti-cheat constraint). Puzzle type rotates per round (server-selected from `archivePuzzleSystem.puzzleTypes`):
  - **Logic / Trivia** (`puzzle_type: "logic"`) — question drawn from `puzzles.md` static bank (400 questions across 8 categories). Displayed as short question text + 2 answer buttons. Time limit: 20s.
  - **Math** (`puzzle_type: "math"`) — arithmetic expression + 3 answer buttons. Time limit: 15s.
  - **Memory Sequence** (`puzzle_type: "sequence"`) — 4 colored tiles flash in order; player replays the sequence. Time limit: 30s.
- Timer bar: thin progress strip below the content panel, depletes over `time_limit_seconds`. Color: amber when ≤8s remain.
- On correct answer: brief `"✓ Clue incoming..."` flash (1s), then hint text rendered in dim amber italic: `"There are 3 Wolves total in this game."`
- On wrong answer or timeout: `"No clue this round."` in muted text. No haptic.
- After puzzle resolves (correct or not): idle state — `"Rest..."` in dim text. Haptic: single 100ms pulse on solve (correct only).
- Screen appearance from 2 feet: dark background, centered panel with tap targets — visually indistinguishable from wolf-vote or seer-peek screens (`archivePuzzleSystem.antiCheatConstraint`).

> **Logic puzzle bank:** `puzzles.md` (project root) — 400 trivia questions across categories: Classic Riddles, Geography & Nature, Science & Technology, History & Pop Culture, Food & Drink, Travel & Geography, History & Art, Pop Culture / Movies / Music, Animals & Nature. Server selects and rotates via game seed to prevent question repetition across rounds. Questions are presented as-is; distractors generated server-side.

### §3.5 Day Phase

**Layout (Discussion sub-phase):**
- Light background `linear-gradient(to top, #dad4ec 0%, #dad4ec 1%, #f3e7e9 100%)` — matches Display TV day substrate (PRD-003 §4.1).
- Top: round label + timer (mirrored from server `timer_ends_at`).
- **Private Notepad** (collapsible panel, default collapsed):
  - Scrollable list of all living players.
  - Each row: avatar + name + toggle (`Sus` / `Safe` / `?`).
  - Stored in local device memory only — never sent to server.
- Bottom: phase label `"Discussion — Speak up!"`.

**Layout (Voting sub-phase):**
- Living player list with `"Vote to Eliminate"` button on each row.
- Self row: grayed out (cannot vote for self, enforced server-side and client-side).
- Already-voted state: selected player gets a checkmark, all other Vote buttons become `"Change Vote"`.
- Haptic: 200ms pulse on vote submission.
- After submit: `"Vote cast — waiting for others..."` status.

### §3.6 Dead State

**Trigger:** Server broadcasts `is_alive: false` for this player's `player_id`.

**Layout:**
- Screen fades to full grayscale via CSS filter (`filter: grayscale(1)`).
- Top banner: `"You have been eliminated."` in muted text.
- Role reveal section (always visible now — no hold required):
  - All living players listed with their true `role` and `alignment` badges.
  - Updates in real-time as the game continues.
- Bottom: `"Watch the game unfold..."` label.

**Behavior:**
- All action buttons are removed from the DOM (not just disabled).
- Night phase: dead player sees the same dark screen but with a `"You are a spectator"` overlay — no action UI, but they can see aggregate progress (how many have acted).
- Day phase: dead player sees voting live but cannot submit.
- Haptic: long 500ms rumble on death notification.

---

## §4. Component Inventory

| Component | Client | Phase | Notes |
|-----------|--------|-------|-------|
| `LobbyScreen` | Display | Lobby | QR code, campfire, avatar parade |
| `NightScreen` | Display | Night | Dark background, timer, narrative text carousel |
| `NightResolution` | Display | Transition | Interstitial death reveal |
| `DayScreen` | Display | Day | Player grid, tombstones, discussion timer |
| `VoteWeb` | Display | Day/Vote | SVG vote-line overlay on player grid |
| `GameOverScreen` | Display | Game Over | Splash, role reveal, event timeline |
| `OnboardingForm` | Mobile | Lobby | Name input + avatar picker |
| `LobbyWaitingScreen` | Mobile | Lobby | Joined players list |
| `RoleRevealScreen` | Mobile | Role Deal | Hold-to-reveal interaction |
| `NightActionShell` | Mobile | Night | Dark container for all role UIs |
| `WolfVoteUI` | Mobile | Night | Kill target selector |
| `SeerPeekUI` | Mobile | Night | Peek target + history |
| `DoctorProtectUI` | Mobile | Night | Protect target selector |
| `VillagerDecoyUI` | Mobile | Night | Sheep counter decoy task |
| `DayDiscussionScreen` | Mobile | Day | Timer + private notepad |
| `DayVoteScreen` | Mobile | Day/Vote | Player list + vote buttons |
| `DeadSpectatorScreen` | Mobile | Any | Grayscale, full role reveal |

---

## §5. User Stories

| As a | I want to | So that |
|------|-----------|---------|
| Display Client | show a QR code and live avatar parade in the lobby | players can join without typing a URL |
| Display Client | fade to a dark moonlit screen when night begins | the room feels tense and immersive |
| Display Client | rotate atmospheric narrative text during the night | the game master narration is automated |
| Display Client | play ambient night audio | phone sounds from active players are masked |
| Display Client | show player avatars as tombstones when they die | eliminations are visually dramatic |
| Display Client | draw live SVG lines between voters and targets | the room can see alliances forming in real time |
| Display Client | show a role-reveal timeline on the game over screen | players can debrief what really happened |
| Mobile Player | hold a button to see my role | my neighbors can't see my role by glancing over |
| Mobile Player | have a dark screen during night identical to all other players | observers can't identify wolves by screen brightness |
| Mobile Player (Villager) | tap a sheep counter as a decoy task | I'm visibly tapping like the active-role players |
| Mobile Player | feel haptic confirmation on night action submit | I don't need a visible flash to confirm my tap |
| Mobile Player | mark players as Sus/Safe in a private notepad | I can track my suspicions without saying them aloud |
| Mobile Player (Dead) | see all roles immediately after being eliminated | I stay engaged as a spectator |

---

## §6. Open Questions

| # | Question | Owner | Priority | Resolution |
|---|----------|-------|----------|------------|
| 1 | Does the Display TV reveal which player is the Doctor when a protection blocks a kill? | Game Design | P0 | **Resolved:** Silent. No reveal of Doctor identity when a save occurs. |
| 2 | Avatar approach: preset illustrated set vs. device camera selfie? | UX / Product | P1 | **Resolved:** Image upload — player provides their own photo via device image picker. See §3.2. |
| 3 | Night audio autoplay: browser autoplay policy blocks audio without prior user gesture — where is this gesture? | Engineering | P1 | **Resolved:** Display TV shows a "Click to begin" fullscreen overlay on page load. The first click dismisses the overlay, unlocks the AudioContext, and enters fullscreen. All subsequent phase-driven audio plays without friction. See ADR-003 §3. |
| 4 | Should the Seer's peek history on mobile persist across a page refresh? | Engineering | P1 | **Resolved:** Yes — stored in `sessionStorage` keyed by `room_code + player_id`. Clears on tab close (intentional: history is per-session, not cross-game). |
| 5 | Vote-web SVG lines: animate incrementally on each vote (live) or reveal all at once when voting closes? | UX | P2 | **Resolved:** Reveal all at once when voting closes. Prevents telegraphing early winners. See §2.5. |
| 6 | Day phase private notepad — should `Sus`/`Safe` tags survive accidental tab closes? | Engineering | P2 | **Resolved:** Yes — stored in `localStorage` scoped by `room_code`. See ADR-003 §7. |
