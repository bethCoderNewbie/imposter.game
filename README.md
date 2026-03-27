# Werewolf — Digital Implementation

[![CI](https://github.com/your-org/imposter/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/imposter/actions/workflows/ci.yml)

A self-hosted, web-based digital implementation of *Werewolf* (Mafia), a social deduction party game for 5–18 players. Uses a **"Jackbox-style" dual-client architecture**: players use personal mobile devices as private role cards and action pads, while a shared TV display acts as the automated Game Master — driving narrative, managing timers, and animating public outcomes. No human moderator required.

---

## Architecture Overview

```
┌──────────────────────────┐     WebSocket      ┌────────────────────────────────────┐
│  Mobile Controller        │ ◄────────────────► │         FastAPI Game Engine         │
│  React                    │                    │                                    │
│  (per-player, private)    │                    │  engine/phases/  — FSM             │
└──────────────────────────┘                    │  engine/actions/ — night resolver  │
                                                 │  engine/state/   — Pydantic models │
┌──────────────────────────┐     WebSocket      │  engine/stripper — 5-view stripper │
│  Display Client           │ ◄────────────────► │                                    │
│  React (DOM-only)         │                    │  storage/ → Redis (TTL sessions)   │
│  (public TV, no roles)    │                    └────────────────────────────────────┘
└──────────────────────────┘
```

**Key patterns:**
- **Server-authoritative state** — backend is the single source of truth; clients send intents only
- **Five-view State Stripper** — `player_view(G, player_id)` pure function strips role data per socket before every broadcast (wolf / seer / villager+doctor / dead / display)
- **Server-owned timers** — `timer_ends_at` absolute UTC timestamp in state; clients derive countdown from it
- **Per-game async queue** — serializes intent processing to prevent race conditions
- **Auto-advance** — server transitions night → day immediately when all active roles submit, no timer wait

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend language | Python ≥ 3.11 |
| API framework | FastAPI + Uvicorn |
| Data validation | Pydantic V2 |
| Cache / session store | Redis (TTL-based, no PostgreSQL) |
| Frontend framework | React 18 + TypeScript + Vite |
| Display rendering | DOM + CSS + SVG (no Canvas/PixiJS) |
| Deployment | Docker + Docker Compose + Nginx |

---

## Game Roles

| Role | Team | Night Action | Count (8-player default) |
|---|---|---|---|
| Villager | Village | Decoy task (count sheep) | 4 |
| Werewolf | Wolf | Vote to eliminate a living player | 2 |
| Seer | Village | Peek at one player's alignment | 1 |
| Doctor | Village | Protect one player from elimination | 1 |

Minimum viable game: 5 players (3 Villagers, 1 Wolf, 1 Seer). Role counts are host-configurable at lobby creation.

---

## Phase Machine

```
LOBBY → ROLE_DEAL → [NIGHT → DAY]* → GAME_OVER
```

| Phase | Duration | Trigger Out |
|---|---|---|
| `lobby` | Indefinite | Host starts game |
| `role_deal` | Up to 30s | All players confirm role reveal |
| `night` | 60s default | All active roles submit OR timer expires |
| `day` | 180s default | All living players vote OR timer expires |
| `game_over` | Indefinite | Win condition met |

**Win conditions** (checked after every elimination):
- Wolves win: `wolves_alive >= villagers_alive`
- Villagers win: `wolves_alive == 0`

---

## Project Structure

```
Imposter/
├── .github/
│   └── workflows/
│       └── ci.yml                                # GitHub Actions CI pipeline (5 jobs)
├── backend-engine/
│   ├── api/                                      # FastAPI routes, WS endpoint, queue
│   ├── engine/                                   # Pure game logic (resolvers, FSM, stripper)
│   ├── storage/                                  # Redis store
│   └── tests/
│       ├── engine/                               # Unit tests — pure engine logic
│       ├── storage/                              # Unit tests — Redis store (fakeredis)
│       ├── api/                                  # Integration tests — HTTP + WebSocket
│       └── e2e/                                  # E2E tests — full game flow (real Redis)
├── frontend-display/                             # React TV client
├── frontend-mobile/                              # React mobile client
├── docs/
│   ├── requirements/
│   │   ├── PRD-001_werewolf_core_system.md      # Game rules, state schema, phase machine
│   │   ├── PRD-002_werewolf_ui_design.md         # Display TV + Mobile UX/UI design
│   │   └── PRD-003_werewolf_visual_design_system.md  # Design tokens, animation, typography
│   ├── architecture/
│   │   ├── adr/                                  # Architecture Decision Records
│   │   ├── data_dictionary.md                    # MasterGameState + StrippedState schema
│   │   └── roles.json                            # Role definitions
│   └── ops/
│       ├── runbook.md                            # Setup, testing, deployment, troubleshooting
│       └── coding-practices.md                  # Backend patterns and conventions
└── CLAUDE.md
```

---

## Getting Started

### Local dev (backend only)

**Prerequisites:** Python 3.11+, Redis.

```bash
# 1. Create and activate the virtual environment
python -m venv .venv
source .venv/Scripts/activate        # Bash
# .\.venv\Scripts\Activate.ps1       # PowerShell
# If PowerShell blocks: Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

# 2. Install dependencies
pip install -e ".[dev,test]"

# 3. Configure environment
cp .env.example .env   # then set SECRET_KEY

# 4. Start Redis (Docker or local)
docker run -d -p 6379:6379 redis

# 5. Run the server
uvicorn api.main:app --reload --app-dir backend-engine

# 6. Run tests
pytest -m "not e2e"           # unit + integration (no Redis required)
REDIS_URL=redis://localhost:6379/15 pytest  # full suite including E2E
```

### Docker (full stack — Phases 4+)

**Prerequisites:** Docker, all devices on the same Wi-Fi.

```bash
cp .env.example .env   # set SECRET_KEY
./start.sh
```

`start.sh` auto-detects your machine's LAN IP so the QR code is reachable from phones, then runs `docker compose up --build`.

| Service | URL |
|---|---|
| Mobile controller (each player) | `http://<LAN-IP>/` — opened via QR |
| Display client (shared TV) | `http://<LAN-IP>/display/` |
| REST API | `http://<LAN-IP>/api/` |
| WebSocket | `ws://<LAN-IP>/ws/` |

### Match Lifecycle

1. **Open the Display client** on the shared TV and click **Create New Match**. A QR code and 4-letter room code appear.
2. **Each player scans the QR code** on their phone. Enter name and tap **Join**.
3. **Host clicks Start Game** when all players are ready. Server deals roles.
4. **Players hold to reveal** their role on their own phone. All screens are dark during night.
5. **Night phase:** Wolves vote to kill, Seer peeks, Doctor protects, Villagers count sheep.
6. **Day phase:** Casualties announced, players discuss and vote to eliminate.
7. **Game ends** when wolves equal or outnumber villagers, or all wolves are eliminated.

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | HMAC signing key (≥ 32 chars) |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection URL |
| `SCHEMA_VERSION` | No | `0.4` | Game state schema version |
| `NIGHT_TIMER_SECONDS` | No | `60` | Night phase duration |
| `DAY_TIMER_SECONDS` | No | `180` | Day discussion duration |
| `VOTE_TIMER_SECONDS` | No | `90` | Voting phase duration |
| `ROLE_DEAL_TIMER_SECONDS` | No | `30` | Role reveal timer |
| `HUNTER_PENDING_TIMER_SECONDS` | No | `30` | Hunter revenge window |
| `DEBUG` | No | `false` | Enable debug logging |

---

## State Stripping (Role Secrecy)

The `MasterGameState` is never sent to any client directly. Before each broadcast, `player_view(G, player_id)` produces a stripped view:

| Information | Wolf (alive) | Seer (alive) | Villager/Doctor (alive) | Dead player | Display client |
|---|---|---|---|---|---|
| Own role | Visible | Visible | Visible | Visible | Hidden |
| Wolf teammates | Visible | Hidden | Hidden | Visible | Hidden |
| Other roles | Hidden | Hidden | Hidden | Visible | Hidden |
| Night actions block | Hidden | Hidden | Hidden | Partially | Hidden |
| Seer's peek history | Hidden | Own only | Hidden | Visible | Hidden |
| Aggregate action count | Visible | Visible | Visible | Visible | Visible (`"3/4 acted"`) |

---

## Testing

The test suite is organized into three tiers, each with a pytest marker:

| Marker | Count | Requires | Command |
|---|---|---|---|
| *(no marker)* unit | 154 | Nothing | `pytest -m "not integration and not e2e"` |
| `integration` | 38 | Nothing (fakeredis) | `pytest -m "integration"` |
| `e2e` | 11 | Real Redis | `REDIS_URL=redis://localhost:6379/15 pytest -m "e2e"` |
| Frontend (Vitest) | 116 | None | `cd frontend-display && npm run test -- --run` |
| **Total** | **319** | | |

E2E tests automatically skip when Redis is unreachable, so `pytest` without `REDIS_URL` set is always safe to run locally.

---

## CI/CD

GitHub Actions runs five jobs on every push and pull request:

| Job | Marker / Tool | Redis service |
|---|---|---|
| `backend-unit` | `not integration and not e2e` | No |
| `backend-integration` | `integration` | No (fakeredis) |
| `backend-e2e` | `e2e` | Yes (`redis:7-alpine`) |
| `frontend-display` | Vitest | No |
| `frontend-mobile` | TypeScript build | No |

See `.github/workflows/ci.yml` and `docs/architecture/adr/ADR-006_integration_e2e_cicd.md`.

---

## Documentation

| Type | Location | Contents |
|---|---|---|
| **PRD-001** | `docs/requirements/PRD-001_werewolf_core_system.md` | Game rules, phase machine, state schema, WebSocket payloads, phase-gate plan |
| **PRD-002** | `docs/requirements/PRD-002_werewolf_ui_design.md` | Display TV + Mobile UX/UI screen-by-screen design spec |
| **PRD-003** | `docs/requirements/PRD-003_werewolf_visual_design_system.md` | Typography tokens, CSS keyframes, color palette, layer architecture |
| **ADR-001** | `docs/architecture/adr/ADR-001_werewolf_tech_stack.md` | Tech stack decisions (FastAPI, Redis, DOM-only Display, server-owned timers) |
| **ADR-005** | `docs/architecture/adr/ADR-005_test_infrastructure.md` | Unit test infrastructure (Vitest, fakeredis, docker-compose.test.yml) |
| **ADR-006** | `docs/architecture/adr/ADR-006_integration_e2e_cicd.md` | Integration + E2E test tiers and GitHub Actions CI/CD pipeline |
| **Runbook** | `docs/ops/runbook.md` | Setup, test commands, deployment, Redis ops, WebSocket troubleshooting |
| **Data Dictionary** | `docs/architecture/data_dictionary.md` | Full `MasterGameState` schema + state-stripper field removal map per view type |

---

## Phase-Gate Plan

| Phase | Gate | Status |
|---|---|---|
| 0 — Architecture | ADR-001 approved | ✅ Complete |
| 1 — Backend Core | 203 backend tests passing, CI green | ✅ Complete |
| 2 — Mobile MVP | Manual QA | Not started |
| 3 — Display MVP | Manual QA | Not started |
| 4 — Integration | End-to-end game completes | Not started |
| 5 — Polish | UX review | Not started |
