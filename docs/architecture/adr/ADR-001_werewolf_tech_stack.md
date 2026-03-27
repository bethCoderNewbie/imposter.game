# ADR-001: Werewolf — Tech Stack Selection

## Status
Accepted

## Date
2026-03-26

## Context

We need to choose:

1. **Backend framework** — which server technology manages game state and WebSocket connections.
2. **Role secrecy enforcement model** — where role data is stripped before broadcast.
3. **Timer ownership** — who owns the night/day countdown: server or clients.
4. **Frontend rendering strategy** — whether the Display client needs Canvas/WebGL or standard DOM.
5. **Real-time protocol** — which network layer handles live state sync.
6. **Deployment model** — how a group self-hosts for a party.

The game's defining technical challenge is **role secrecy**: unlike a board game where hidden information is limited to hand cards, every player in Werewolf has a fundamentally different view of the world based on their role. Wolves know each other; the Seer accumulates private knowledge across rounds; dead players become omniscient spectators. The State Stripper must handle five distinct view types (wolf, seer, villager/doctor, dead, display) without a single role leak.

A secondary constraint is **timer authority**: the night phase must auto-advance when all active roles submit, but also timeout if players are slow. Timers owned by clients desync across devices; timers owned by the server require a reliable background task mechanism.

This project shares its "Jackbox-style" dual-client architecture concept with *Brass: Birmingham* (same developer) — one shared Display TV, many private mobile devices — so the team already has hands-on experience with the Python FastAPI + React WebSocket pattern established in ADR-002 of that project.

---

## Decision

### 1. Custom Python/FastAPI Backend

**Chosen:** Python FastAPI + WebSockets (same stack as Brass Birmingham).

**Rejected:** Boardgame.io (Node.js), Colyseus (Node.js), Party Kit.

**Rationale:**
- The team has proven infrastructure for this stack: phase machine, queue-based concurrency, State Stripper pattern, and Docker Compose deployment.
- Werewolf's backend is *simpler* than Brass Birmingham — no graph traversal, no market model — so the same stack carries zero new risk.
- Future role expansion (Witch, Cupid, Hunter) and AI-bot opponents benefit from the Python ecosystem.
- Boardgame.io and Colyseus save networking boilerplate but impose framework-specific state models that complicate the five-view State Stripper.

### 2. Server-Authoritative State with a Five-View State Stripper

**Chosen:** `player_view(G, player_id) -> StrippedState` pure function, called once per connected socket on every broadcast.

**Rejected:** Client-side filtering (trust the client not to read other players' roles from the payload).

**Rationale:**
- Sending full role data to every client and relying on client JS to hide it is a trivially exploitable cheat vector (open browser DevTools → read WebSocket frame).
- A pure, server-side `player_view` function is stateless, unit-testable, and eliminates the attack surface entirely.
- Five view types: `wolf` (sees wolf teammates), `seer` (sees accumulated peek history), `villager/doctor` (baseline), `dead` (sees all roles), `display` (sees no roles, only phase + aggregate counts).

### 3. Server Owns All Timers

**Chosen:** Server stores `timer_ends_at` as an absolute ISO8601 UTC timestamp in game state. A single background `asyncio` task per active game fires `phase_timeout` when the deadline passes. Clients render a countdown from `(timer_ends_at - now)`.

**Rejected:** Client-side countdown timers with a server sync pulse.

**Rationale:**
- Client clocks diverge. If ten phones each own a countdown, they will fire `phase_timeout` at slightly different times, causing visible desync on the Display TV.
- Server-owned timers are a single source of truth. The display TV and all mobile clients derive their visible countdown from the same `timer_ends_at` value in the broadcasted state.
- The background asyncio task is already a proven pattern (identical to Brass Birmingham's turn timer).
- **Auto-advance exception:** When all active roles submit their actions before the timer expires, the server cancels the background task and transitions immediately — no timer-tick latency.

### 4. React DOM for Both Mobile and Display (No PixiJS)

**Chosen:** Pure React DOM for both the Mobile Controller and the Display Client.

**Rejected:** React + PixiJS Canvas for the Display (as used in Brass Birmingham).

**Rationale:**
- Werewolf's Display UI is a grid of player avatars, a timer bar, and animated text. There is no spatial board, no vector routes, and no overlapping sprite layers. Standard CSS grid + CSS animations are sufficient.
- Eliminating PixiJS removes the heaviest dependency in the Brass Birmingham stack, reduces bundle size, and avoids `@pixi/react` fiber lifecycle complexity.
- CSS transitions and keyframe animations can deliver the "sun rising / moon falling" phase transitions and "tombstone" death effects at zero additional library cost.

### 5. WebSockets (not Server-Sent Events or Long-Polling)

**Chosen:** WebSockets via FastAPI's native `WebSocket` support.

**Rejected:** Server-Sent Events (SSE), long-polling.

**Rationale:**
- Mobile → Server bidirectional communication is required (night action submission, day votes). SSE is server-push only and requires a separate REST channel for client messages, adding complexity.
- Long-polling introduces unacceptable latency for phase transitions that must feel simultaneous across all devices.
- WebSockets provide the same persistent, bidirectional channel proven in Brass Birmingham.

### 6. Docker + Docker Compose for Self-Hosting

**Chosen:** Containerized deployment — FastAPI backend, two React frontends (mobile + display), Redis (session/reconnect tokens), Nginx reverse proxy.

**Rejected:** PostgreSQL for persistence (Werewolf sessions are transient, not persisted across server restarts).

**Rationale:**
- Same self-hosting requirement as Brass Birmingham: one `docker compose up` deploys everything.
- Werewolf game sessions are party-night ephemeral. Redis TTL-based storage is appropriate; a full relational DB adds operational overhead for no benefit.
- Nginx handles WebSocket upgrades and serves both React frontends from the same origin, avoiding CORS complexity.

---

## Consequences

**Positive:**
- Zero new infrastructure risk — same proven stack as Brass Birmingham.
- State Stripper is the entire security model; it is pure, isolated, and independently testable.
- Server-owned timers guarantee phase synchronization across all devices.
- No PixiJS means a lighter Display bundle and simpler component model.
- Redis-only persistence keeps the deployment footprint minimal for a party-game use case.

**Negative:**
- No framework boilerplate savings — phase machine, timer task management, and WebSocket broadcast logic are all hand-rolled (same cost as Brass Birmingham, but the team has the pattern).
- Five State Stripper view types must be exhaustively tested; a missing case silently leaks role data.
- Browser autoplay policy may block ambient audio on the Display TV — requires a one-time user gesture (e.g., host clicking "Start Game") to unlock the audio context before the first night phase.
- Redis-only persistence means a server restart during a game session loses all state. Acceptable for party use; unacceptable for tournament play (out of scope for v1).
