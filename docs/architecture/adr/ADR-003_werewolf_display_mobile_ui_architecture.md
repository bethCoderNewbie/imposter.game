# ADR-003: Werewolf — Display TV & Mobile UI Architecture

## Status
Accepted

## Date
2026-03-26

## Context

PRD-002 defines the visual and interaction design for both client surfaces: the shared Display TV and the individual Mobile Phone. The two surfaces have competing constraints that drive several non-obvious implementation choices.

The Display TV must be readable at 8–10 feet on any screen size (720p → 4K), deliver theatrical phase transitions and a live SVG vote-web, and play ambient audio — all without ever exposing role or alignment data.

The Mobile Phone must protect role secrecy from physical observers at 2 feet, provide haptic confirmation in place of visible feedback, and render a night-phase screen that looks identical for every role. The Role Reveal interaction has a specific anti-cheat requirement: role data must not exist in the DOM while the screen is in its hidden state.

ADR-001 §4 already decided React DOM (no PixiJS) for both clients. This ADR records the UI-layer decisions that follow from PRD-002's requirements — rendering strategy, animation approach, audio, haptics, DOM security, typography, and client storage.

---

## Decision

### 1. CSS-Only Animations (No Framer Motion / GSAP)

**Chosen:** CSS `@keyframes` + `transition` for all phase transitions and per-element effects: `night-enter` (2s fade through black), `reveal-flicker` (1.2s text entrance), `claw-slide-in` (1.2s death reveal), `vote-majority-pulse` (3s infinite red glow cycle).

**Rejected:** Framer Motion, GSAP, Anime.js.

**Rationale:**
- PRD-002 §2.8 explicitly prohibits Canvas and PixiJS; the same DOM-only principle extends to JS animation engines.
- All required effects (fade, slide, filter, box-shadow pulse, grayscale) are expressible in pure CSS. There is no sequencing complexity (scroll-linked animation, physics) that would justify a library.
- CSS animations are GPU-composited on `transform` and `opacity` paths, providing smooth 60fps without JS thread involvement.
- Animation keyframe names and `animation-delay` stagger values are defined in PRD-003 §3 (single source of truth). Components reference those class names; they do not define animation values inline.

### 2. SVG Vote-Web Overlay (Not Canvas)

**Chosen:** An absolute-positioned `<svg>` element layered over the `DayScreen` player grid. When the server transitions `phase` from `day_vote` to vote resolution, the client renders all `<line>` elements simultaneously — one per vote cast — from each voter's avatar centroid to their target's centroid. `stroke-width` scales with vote count on the target. A player exceeding 50% of votes receives the `vote-majority-pulse` CSS class. Lines are not drawn as individual votes arrive.

**Rejected:** Canvas 2D context for vote-line drawing; live-update-per-vote SVG rendering.

**Rationale:**
- PRD-002 §2.5 and §2.8 explicitly require SVG.
- Reveal-all-at-once (PRD-002 §6 Q5, resolved) is preferred over live incremental updates. Showing each vote as it arrives telegraphs early vote leaders and allows players to change their vote strategically based on the emerging web — undermining the drama of the simultaneous reveal.
- SVG `<line>` elements are DOM nodes: they inherit CSS transitions (for a brief staggered entrance animation on reveal), can receive `className` changes for the majority-pulse effect, and are cleared by unmounting the SVG subtree.
- No bespoke render loop needed. The reveal is triggered by a single phase-transition event in the WebSocket state, after which the full vote data is in `state.votes`.

### 3. HTML5 `<audio>` for Ambient Sound (Not Web Audio API)

**Chosen:** Preloaded `<audio>` elements for each track (ambient night loop, rooster SFX, victory fanfare, wolf howl). Tracks are triggered by calling `.play()` / `.pause()` from phase-transition effect hooks.

**Audio unlock gesture (PRD-002 §6 Q3, resolved):** The Display TV page renders a full-screen "Click to Begin" overlay on load (dark background, centered play icon, `"Click anywhere to start the display"`). The first click on this overlay: (1) calls `document.documentElement.requestFullscreen()` to enter fullscreen, (2) creates and immediately resumes an `AudioContext` (or calls `.resume()` if already created), and (3) dismisses the overlay. All subsequent phase-driven `.play()` calls succeed without further user interaction. If `AudioContext.state` is ever detected as `'suspended'` mid-game (e.g., browser throttling), a small speaker icon in the corner re-appears as a tap target.

**Rejected:** Web Audio API for track playback; piggybacking unlock on "Start Game" mobile action (the Display TV is a separate browser window with its own autoplay state).

**Rationale:**
- PRD-002 §2.3 specifies an ambient loop with a configurable volume level — no spatial audio, no real-time DSP, no precise sub-millisecond scheduling. `<audio>` covers all stated requirements.
- Web Audio API adds implementation overhead (buffer loading, source node recreation on each play, context state management) with no benefit for this use case.
- The "Click to Begin" overlay is the lowest-friction resolution to the autoplay constraint: it doubles as the fullscreen entry point (TVs are typically navigated to in a browser before fullscreen is activated), so the click serves two purposes simultaneously with no perceived extra step.

### 4. Vibration API for Haptic Feedback

**Chosen:** `navigator.vibrate(pattern)` called from Mobile event handlers. Patterns follow PRD-002 §3.3–§3.5 exactly: role reveal (200ms), role blank (100ms), night action confirm (300ms), death notification (500ms). On devices that do not support `navigator.vibrate` (iOS Safari), the call is a silent no-op; no fallback is provided.

**Rejected:** A third-party haptics library; a visible flash fallback on unsupported devices.

**Rationale:**
- The Vibration API is standard on all target Android devices (Chrome, Firefox). iOS Safari does not expose it, but haptics are secondary to the core secrecy requirement — a visible flash fallback would contradict PRD-002 §3.1 ("secrecy first").
- The silent no-op behavior is the correct UX: iOS players receive no confirmation indicator, which is preferable to a screen flash that could reveal action timing to observers.
- A library wrapper adds no value when the underlying API is two lines per call site.

### 5. Hold-to-Reveal: DOM Injection on `pointerdown` (Not CSS Hide)

**Chosen:** The `RoleRevealScreen` renders only the "HOLD TO REVEAL" button shell on mount. On `pointerdown`, React state transitions to `isRevealing: true`, which causes the role name, role color background, role icon SVG, and ability bullet list to be conditionally rendered into the DOM. On `pointerup` or `pointercancel`, `isRevealing` returns to `false` and the role subtree is unmounted.

**Rejected:** Rendering the role markup on mount and toggling `visibility: hidden` or `opacity: 0` when not held.

**Rationale:**
- PRD-002 §3.3 explicitly requires this pattern: "Role data is only rendered into the DOM while the button is held — not in the HTML while hidden. This prevents inspect-element cheating."
- CSS hide leaves role text in the DOM. A player opening DevTools — or a third-party browser extension — can read the role value without holding the button.
- Conditional rendering means the DOM contains no role-revealing markup at rest. Combined with server-side State Stripping (ADR-001 §2), this closes the client-side inspection vector entirely.
- `confirm_role_reveal` intent is sent to the server after the first hold lasting ≥1 second. The intent is sent from the `pointerdown` handler after a 1000ms timer; it is not gated on `pointerup`.

### 6. `clamp()` + `vmin` Responsive Typography (No Fixed-px Text)

**Chosen:** All Display TV text sizes use the CSS `clamp(minPx, Xvmin, maxPx)` formula. No bare `px`, `rem`, or `vw` values appear in Display components. The conversion formula (1080p baseline: `target_px ÷ 10.8 ≈ vmin`) is defined in PRD-003 §2, which is the single source of truth for all Display typography values. Mobile components use standard `rem`/`px` (viewport independence is less critical on a hand-held device viewed at arm's length).

**Rejected:** Fixed `px` sizes; a `transform: scale()` wrapper on the entire HUD; `vw` alone.

**Rationale:**
- PRD-002 §2.1 mandates `clamp()`/`vmin` for all Display text. PRD-002 §2.8 explicitly prohibits a single `transform: scale()` HUD wrapper.
- The Display must remain readable at 8–10 feet across resolutions from 720p to 4K. `vmin` scales against the smaller viewport dimension, which keeps text proportional on both landscape widescreen TVs and portrait monitors without media queries.
- `vw` alone breaks on portrait screens (text becomes too small). `rem` is relative to root font-size, which adds an indirection layer with no benefit. `transform: scale()` causes sub-pixel rendering artifacts and breaks absolute-positioned overlays (SVG vote-web, modal layers).
- Typography values are not duplicated in component files — they reference PRD-003 §2's table via CSS custom properties or shared style constants.

### 7. Private Notepad: `localStorage` with Room-Scoped Keys

**Chosen:** The `DayDiscussionScreen` notepad stores each `Sus`/`Safe`/`?` tag in `localStorage` under the key `ww_note_{room_code}_{viewer_player_id}_{target_player_id}`. Data is read on component mount and written on each toggle. It is never sent to the server.

**Rejected:** `sessionStorage` (lost on accidental tab close); server storage (privacy concern, unnecessary bandwidth); in-memory React state only (lost on refresh).

**Rationale:**
- PRD-002 §3.5 requires the notepad to be "stored in local device memory only — never sent to server."
- PRD-002 §6 Open Question #6 asks whether tags should survive tab closes. This ADR resolves that question in favor of `localStorage` persistence: the cost of stale data is low (it is scoped per room code and will be overwritten next game), while the cost of losing notes mid-game is a degraded player experience.
- Room-code scoping (`ww_note_{room_code}_...`) ensures a player rejoining a different room does not see notes from a previous session.

### 8. Server-Seeded Villager Decoy Delay

**Chosen:** The server includes a `decoy_reveal_delay_ms` integer field (range: 15000–30000 ms, randomly sampled server-side at night-start) in the Villager player's `StrippedPlayerState` payload. The `VillagerDecoyUI` component starts a `setTimeout` of this duration on mount; when it fires, the sheep counter is replaced with `"Rest..."` and a single 100ms haptic pulse is triggered.

**Rejected:** Pure client-side `Math.random()` to determine the delay.

**Rationale:**
- PRD-002 §3.4 requires the delay to be "server-seeded to prevent timing analysis."
- If the client generates the delay locally with `Math.random()`, the timer is silent (no network event). However, a sophisticated physical observer watching for any network traffic from a Villager's device could infer that the Villager's timer fired because no `night_action` confirm message was ever sent — contrasting with the single confirm message sent by active-role players. The timing of the client-side timer is thus inferrable from the absence of network activity.
- Server-seeding embeds the delay value in the state broadcast, making the client-side timer duration opaque to network observers. The Villager's behavior pattern (dark screen, tapping activity for 15–30s, then idle) is indistinguishable from an active role that submitted early and entered a wait state.

### 9. Session Reconnect Token: `localStorage`

**Chosen:** The mobile client's reconnect session (game_id, player_id, session_token) is stored in `localStorage` under the key `ww_session` as a JSON object. It is read on every app mount, used to call `POST /api/games/{id}/rejoin`, and cleared on rejoin failure (401/404) or explicit "leave" actions.

**Rejected:** `sessionStorage` (original implementation — reverted in ADR-013).

**Rationale:**
- Mobile browsers (iOS Safari, Android Chrome) kill background tabs under memory pressure, clearing `sessionStorage`. For a party game where players switch apps on their phone during play, this is an expected OS behavior — not an edge case. A player who switches to a messaging app mid-night phase would return to the onboarding form instead of their game.
- `localStorage` persists until the origin is cleared or the item is explicitly removed. The backend's 4-hour Redis TTL on session tokens is the expiry guard. Stale entries trigger a 401 from `/rejoin`, which calls `clearSession()` — no permanent accumulation.
- **This is distinct from the Seer peek history** (§10 below), which explicitly uses `sessionStorage` because its data should not outlast the tab session.

### 10. Seer Peek History: `sessionStorage`

**Chosen:** Seer peek results are stored in `sessionStorage` keyed by `ww_seer_{room_code}_{player_id}`. Each entry is an ordered array of `{ round, target_name, result }` objects. The component reads from `sessionStorage` on mount and appends each new result after the server confirms a peek. Data is cleared automatically on tab close.

**Rejected:** `localStorage` (persists across games — stale history from a prior session could be confused with the current game's peeks); server storage (the Seer's accumulated knowledge is private — it must not be included in any broadcast payload that could reach other players).

**Rationale:**
- PRD-002 §3.4 (Seer) shows peek history as a persistent list below the current round's result: *"Previous round peeks listed below current result (persistent across rounds for Seer only)."*
- PRD-002 §6 Q4 resolved: history persists within a session but not across games.
- `sessionStorage` is per-tab: if the Seer accidentally closes the tab, history is lost. This is acceptable — they rejoin under the same `player_id` and the server can replay their accumulated peeks in the `StrippedPlayerState` response (the server is the authoritative source; `sessionStorage` is a display cache, not the record of truth).
- Seer peek results are included in the server-side `StrippedPlayerState` for the Seer view type, so a page refresh re-hydrates the history from the next state broadcast.

---

## Consequences

**Positive:**
- Zero new UI dependencies beyond React — no animation library, no audio library, no haptics library. Bundle size stays minimal.
- CSS animations are GPU-composited; SVG vote-web is rendered in a single pass on vote-close. No bespoke render loops to maintain.
- DOM injection for Role Reveal closes the client-side inspect-element cheat vector completely when combined with server-side State Stripping.
- `localStorage` for the reconnect session token (§9) and notepad (§7), and `sessionStorage` for Seer peek history (§10) give each storage concern the correct scope: session tokens and notepad data survive tab kills; Seer history is intentionally ephemeral within a tab.
- Server-seeded Villager decoy delay closes PRD-002 §3.4's timing-analysis requirement.
- `clamp()`/`vmin` typography ensures Display readability across all TV resolutions without media queries or scale wrappers.
- "Click to Begin" overlay on Display TV resolves PRD-002 Open Question #3 with no perceived friction (doubles as fullscreen entry).
- Reveal-all-at-once vote-web eliminates the early-winner telegraphing problem (PRD-002 §6 Q5).

**Negative:**
- HTML5 `<audio>` autoplay requires the "Click to Begin" overlay to be clicked before the first night phase. If the display TV's browser is navigated to a different page and back, the overlay reappears and must be clicked again to re-unlock audio.
- `navigator.vibrate` is unsupported on iOS Safari. Mobile players on iPhone receive no haptic confirmation. No visible fallback is provided (by design — PRD-002 §3.1 secrecy constraint).
- SVG vote-web centroid calculation (`getBoundingClientRect`) fires once at vote-close (not per state update). Performance concern from prior draft is eliminated by the reveal-all-at-once decision.
- `localStorage` notepad data persists until explicitly cleared. Players sharing a device across multiple game nights will accumulate stale entries under old room codes. These are benign but should be pruned when the player joins a new room (clear all `ww_note_*` keys that do not match the current `room_code`).
- If the Seer closes their browser tab mid-game, `sessionStorage` peek history is lost. On rejoin, the server re-broadcasts the full Seer state including accumulated peek history; the client re-populates `sessionStorage` from this broadcast on mount.
