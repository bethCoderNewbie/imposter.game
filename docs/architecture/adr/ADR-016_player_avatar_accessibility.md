# ADR-016: PlayerAvatar Accessibility — role="img" + aria-label

## Status
Accepted

## Date
2026-03-30

## Context

`PlayerAvatar` is the primary player-identification primitive in the mobile frontend. It renders a circular colored badge with two-character initials and is used in all 14 screen components (lobby roster, night action selectors, day vote, discussion notepad, spectator view, game over screen).

Prior to this change, the component rendered a bare `<div>` with no ARIA attributes:

```tsx
<div className="player-avatar" style={...}>
  AL
</div>
```

Screen readers encounter this element as an anonymous container. The two-character initials ("AL") could be announced literally, but there is no semantic association between those characters and a player's identity. In action-selection UIs (e.g. `WolfVoteUI`, `DoctorProtectUI`) where each row is a `<button>` containing a `PlayerAvatar` plus a display name, the accessible name of the button is derived from its text content — so the visible name is still announced. However, in list-only contexts (e.g. `DeadSpectatorScreen`, `LobbyWaitingScreen`) where the avatar and name are siblings rather than parent/child, the avatar itself carries no accessible label.

The inconsistency and the WCAG 1.1.1 (Non-text Content) failure warranted a single, uniform fix.

### Alternatives Considered

**A — Visually-hidden `<span>` inside the div**

```tsx
<div className="player-avatar" style={...}>
  AL
  <span className="sr-only">{player.display_name}</span>
</div>
```

Adds an extra DOM node. The initials and the full name would both be read by some screen readers, causing redundancy ("AL Alice"). Rejected.

**B — Tooltip on hover/focus**

A `title` attribute or a tooltip component that reveals the full name. Mobile-hostile (no hover state). Inconsistent across screen readers. Rejected.

**C — `role="img"` + `aria-label={display_name}` (selected)**

```tsx
<div role="img" aria-label={player.display_name} className="player-avatar" style={...}>
  AL
</div>
```

`role="img"` declares the element as an image (ARIA landmark), and `aria-label` provides the accessible name. Screen readers announce only the `aria-label` value and skip the text content — so there is no "AL Alice" redundancy. No visible layout change, no new props, no calling-site updates required. Satisfies WCAG 1.1.1 at a single location that propagates to all 14+ render sites.

---

## Decision

Added `role="img"` and `aria-label={player.display_name}` to the `PlayerAvatar` wrapper `<div>`.

**Files changed:**
- `frontend-mobile/src/components/PlayerAvatar/PlayerAvatar.tsx` — two attributes added to the root element

No CSS changes. No prop changes. No calling-site changes.

---

## Consequences

**Positive:**
- All 14+ `PlayerAvatar` render sites gain WCAG 1.1.1 compliance with a single change.
- Screen readers announce the player's full display name rather than initials.
- No visible layout or behavioral impact.
- `getByRole('img', { name: 'Alice' })` is now available in tests — improves test readability (used in `PlayerAvatar.test.tsx`).

**Negative:**
- `role="img"` on a `<div>` is non-standard. ARIA specification permits it but some linting rules flag it. The tradeoff (semantic clarity vs. an HTML `<img>` element requiring a placeholder `src`) favors the `<div>` approach given the avatar is dynamically generated CSS rather than a raster image.

---

## Related

- PRD-008: Mobile Component Test Coverage (adds `PlayerAvatar.test.tsx` covering this attribute)
- ADR-003: Mobile UI Architecture (§3.2 — player identity display conventions)
- `frontend-mobile/src/components/PlayerAvatar/PlayerAvatar.tsx` — implementation
