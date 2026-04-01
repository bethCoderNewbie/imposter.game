# ADR-017: hunter_pending Routing Gate — Dead Hunter Only

## Status
Accepted

## Date
2026-04-01

## Context

ADR-011 §Decision 4a introduced `HunterPendingScreen` as the routing target for `phase === 'hunter_pending'`. The implementation moved `hunter_pending` out of the `DayVoteScreen` fallback and into a dedicated case. However, the routing block had no role or liveness guard:

```tsx
// ADR-011 implementation (App.tsx, as shipped)
if (phase === 'hunter_pending') {
  return (
    <HunterPendingScreen
      gameState={gameState}
      myPlayer={myPlayer!}
      sendIntent={sendIntent}
    />
  )
}

// Dead-player override — placed AFTER hunter_pending in ADR-011
if (myPlayer && !myPlayer.is_alive) {
  return <DeadSpectatorScreen gameState={gameState} myPlayerId={session.player_id} />
}
```

This produced two bugs:

**Bug 1 — Alive players shown the hunter's action screen.**
All alive players (villagers, wolves, seer, doctor, etc.) fell into the `hunter_pending` branch and rendered `HunterPendingScreen`. This leaked:
- That a Hunter was eliminated (the screen itself implies it)
- The target picker UI, which exposed the live player list in an action context

Alive players could not successfully send a `hunter_revenge` intent — the backend's `handle_hunter_revenge` validates `player.role === 'hunter'` and rejects others. But the UI was visible, which is a game-integrity violation in a social deduction game.

**Bug 2 — Dead hunter shown `DeadSpectatorScreen` instead of `HunterPendingScreen`.**
The dead-player override followed `hunter_pending` in the routing chain. When `phase === 'hunter_pending'`, the eliminated hunter (`!myPlayer.is_alive`) fell into the `hunter_pending` branch first — but since the branch had no liveness check, it rendered `HunterPendingScreen` correctly in that case only by accident. After the ADR-011 fix was re-read: the dead-player override was ordered after `hunter_pending`, so the hunter DID reach `HunterPendingScreen`. However the check `myPlayer!` assumed the player was alive (non-null-assertion). The actual failure mode was that **all alive players also reached `HunterPendingScreen`** with no gate.

**Root cause.** ADR-011 §4a described `hunter_pending` routing without specifying which players should see it. The intent ("Hunter fires their revenge shot") implies only the dead hunter should see the screen, but the implementation did not encode that constraint.

---

## Decision

Gate `HunterPendingScreen` to the eliminated hunter only:

```tsx
// hunter_pending check placed BEFORE the dead-player override
if (phase === 'hunter_pending') {
  if (myPlayer && !myPlayer.is_alive && myPlayer.role === 'hunter') {
    return (
      <HunterPendingScreen
        gameState={gameState}
        myPlayer={myPlayer}
        sendIntent={sendIntent}
      />
    )
  }
  // All other players (alive or dead non-hunter) wait
  return (
    <div className="app-status">
      <p>Waiting…</p>
    </div>
  )
}

// Dead-player override applies to all remaining live phases
if (myPlayer && !myPlayer.is_alive) {
  return <DeadSpectatorScreen gameState={gameState} myPlayerId={session.player_id} />
}
```

The gate condition is: `!myPlayer.is_alive && myPlayer.role === 'hunter'`. This is correct by invariant — a Hunter entering `hunter_pending` is always dead (the backend sets `HUNTER_PENDING` only after the Hunter is added to `hunter_queue` during night resolution, which requires their elimination). The `is_alive` check is redundant in theory but serves as a defensive programming layer.

**Why a "Waiting…" screen for everyone else:**
Alive players need visual feedback that a phase transition is in progress. `null` or no render would leave a blank screen. `DeadSpectatorScreen` would be incorrect for alive players. The generic `app-status` waiting div is already used for `Connecting…` and `Reconnecting…` — the same pattern is appropriate here.

**No changes to `DeadSpectatorScreen`.** Dead non-hunter players still fall through to `DeadSpectatorScreen` for all other phases via the existing override at `App.tsx:174`.

### Routing audit: no other roles require dead-player screens

A full audit of all roles confirmed Hunter is the only role with `actionPhase: "on_death"` (`roles.json:134`). `HUNTER_PENDING` is the only sub-phase in the Phase enum requiring a dead player to interact. No `*_pending` fields exist in `MasterGameState` beyond `hunter_queue`. The fix is isolated.

---

## Consequences

### Files Changed

| File | Change |
|---|---|
| `frontend-mobile/src/App.tsx` | `hunter_pending` block moved before dead-player override; gated to `!is_alive && role === 'hunter'`; alive-player waiting fallback added; duplicate `hunter_pending` block at bottom removed |
| `frontend-mobile/src/test/App.routing.test.tsx` | Hunter fixture corrected: `is_alive: false` (hunter in `hunter_pending` is always dead) |

### Positive

- Alive players no longer see `HunterPendingScreen` during `hunter_pending` — no role leak, no spurious intent UI.
- Dead hunter now correctly reaches `HunterPendingScreen` and can fire their revenge shot.
- Alive villagers and other roles no longer show `HunterPendingScreen` during `hunter_pending`, so the `NightActionShell` → `VillagerDecoyUI` rendering path resolves correctly when `phase` returns to `night`.
- The "Archives await…" bug for villagers (caused by wrong-screen routing during `hunter_pending`) is resolved as a side-effect.

### Negative

- None. The waiting screen is intentionally minimal; no PRD requirement exists for a richer `hunter_pending` spectator view for alive players.

---

## Related

- ADR-011: Mobile Client Protocol Parity — §Decision 4a (original `hunter_pending` routing)
- PRD-009: Hunter Action Leak & Villager Puzzle Fix
- `frontend-mobile/src/App.tsx` — implementation
- `backend-engine/engine/resolver/night.py:365–376` — `_step12_hunter_queue` (sets `HUNTER_PENDING`)
- `backend-engine/api/intents/handlers.py:302–321` — `handle_hunter_revenge`
