# Werewolf — Operations Runbook

**Audience:** Server operators and on-call engineers.
**Format:** Symptom → Diagnosis → Fix.

---

## Local Dev Setup

### Prerequisites
- Python 3.11+
- Redis 7+ (`redis-server` or Docker)
- Node 18+ (for frontends)

### Backend

```bash
cd backend-engine
pip install -e ".[dev]"
redis-server &          # or: docker run -p 6379:6379 redis
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Mobile frontend

```bash
cd frontend-mobile
npm install
npm run dev             # proxies /api and /ws to localhost:8000
```

### Display frontend

```bash
cd frontend-display
npm install
npm run dev
```

---

## Running Tests

```bash
# Unit tests (no Redis required)
cd backend-engine
pytest tests/ -m "not e2e and not integration" -v

# Stripper security tests (highest priority — run first)
pytest tests/engine/test_stripper.py -v

# Integration tests (requires live Redis at localhost:6379)
pytest tests/ -m "integration" -v

# End-to-end (requires full stack running)
pytest tests/e2e/ -m "e2e" -v
```

---

## Redis Session Management

### View active game keys

```bash
redis-cli KEYS "wolf:game:*"
```

### Inspect a game state

```bash
redis-cli GET wolf:game:<GAME_ID> | python -m json.tool
```

### Delete a stuck game

```bash
redis-cli DEL wolf:game:<GAME_ID>
```

### Check session token

```bash
redis-cli GET wolf:token:<TOKEN>
# Returns "game_id:player_id" or (nil)
```

### Flush all game sessions (⚠ destructive — use only in dev)

```bash
redis-cli --scan --pattern "wolf:*" | xargs redis-cli DEL
```

---

## Match Lifecycle (Step by Step)

1. **Display TV** opens `POST /api/games` → receives `game_id`, `host_player_id`, `session_token`
2. **Display TV** connects WebSocket `/ws/{game_id}/display`
3. **Players** scan QR code → `POST /api/games/{game_id}/join` → receive `player_id`, `session_token`
4. **Players** connect WebSocket `/ws/{game_id}/{player_id}` → send `{"type":"auth","session_token":"..."}`
5. **Host player** sends `{"type":"start_game","player_id":"...","state_id":0}`
6. **Server** assigns roles, transitions to `role_deal` phase, broadcasts stripped state per socket
7. **Players** hold to reveal role → send `confirm_role_reveal` → server auto-advances to `night` when all confirmed
8. **Night loop:** players submit night actions → server auto-resolves when all `wakeOrder>0` players submitted
9. **Day loop:** host sends `advance_phase` (DAY → DAY_VOTE) → players cast votes → server resolves
10. **Repeat** night/day until win condition met

---

## Diagnosing WebSocket Issues

### Symptom: Mobile client stuck on "Connecting..."

**Possible causes:**
- Session token expired (4-hour TTL)
- Game not found in Redis (TTL expired or game deleted)
- Backend not running

**Fix:**
1. Check backend logs: `uvicorn` output
2. Verify Redis: `redis-cli KEYS "wolf:game:*"`
3. Player must `POST /api/games/{game_id}/rejoin` with stored session token

### Symptom: Mobile client shows "Auth Failed"

**Possible causes:**
- Wrong game_id in URL vs session token's game_id
- Stale token from a previous game session

**Fix:**
- Clear `sessionStorage` in browser DevTools
- Rejoin the game via the join URL

### Symptom: Player gets `STALE_STATE` error

**Cause:** Client sent an intent with `state_id` that doesn't match current server `state_id` — this means another action was processed between the client reading state and submitting the intent.

**Fix:** Client should retry automatically after receiving updated `state_update` from the server.

### Symptom: "Phase timeout" fires but phase doesn't advance

**Possible causes:**
- Game already advanced (stale timeout, expected behavior — logged and ignored)
- Backend restarted — all in-memory timer tasks are cleared on restart

**Fix:** On backend restart, active games have no timer tasks. The host can manually advance phase or the next player action will trigger auto-advance.

### Symptom: Display shows wrong phase

**Cause:** Display WebSocket may have reconnected and received a cached `state_update`.

**Fix:** Display client sends `player_id="display"` — no auth required. Disconnect and reconnect to re-receive current state broadcast.

### Symptom: QR code not reachable from phones

**Cause:** Display and phones on different network segments, or firewall blocking port 3001.

**Fix:**
- Verify all devices on same LAN/Wi-Fi
- Check `start.sh` auto-detected LAN IP is correct: `hostname -I | awk '{print $1}'`
- Manually export: `export MOBILE_BASE_URL=http://<correct-ip>:3000`
- Run `./start.sh <correct-ip>` to override

### Symptom: Audio does not play on Display TV

**Cause:** Browser autoplay policy requires a user gesture before AudioContext can be unlocked.

**Fix:** The game host must click "Start Game" (or any interactive element) on the Display client before the first Night phase. The `useAudio()` hook unlocks AudioContext on this gesture.

---

## Deployment (Docker Compose)

### Start all services

```bash
cp .env.example .env
# Edit SECRET_KEY in .env
./start.sh              # auto-detects LAN IP
```

### Service URLs

| Service | URL |
|---------|-----|
| Backend API | `http://<LAN-IP>:8000` |
| Mobile frontend | `http://<LAN-IP>:3000` |
| Display frontend | `http://<LAN-IP>:3001` |
| Health check | `http://<LAN-IP>:8000/health` |

### Stop all services

```bash
docker compose down
```

### View backend logs

```bash
docker compose logs -f backend
```

---

## Configuration Reference

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (required) | App secret — change in production |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |
| `SCHEMA_VERSION` | `0.4` | Game state schema version |
| `NIGHT_TIMER_SECONDS` | `60` | Night phase duration |
| `DAY_TIMER_SECONDS` | `180` | Day discussion duration |
| `VOTE_TIMER_SECONDS` | `90` | Voting phase duration |
| `ROLE_DEAL_TIMER_SECONDS` | `30` | Role reveal timer |
| `HUNTER_PENDING_TIMER_SECONDS` | `30` | Hunter revenge window |
| `DEBUG` | `false` | Enable debug logging |
