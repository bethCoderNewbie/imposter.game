# CLI Reference — Bash & PowerShell

All commands assume you are in the project root `C:\Users\bichn\MSBA\Imposter\` unless noted.

---

## Environment Setup

### Create Python virtual environment (run once)

| | Command |
|---|---|
| **Bash** | `python -m venv .venv` |
| **PowerShell** | `python -m venv .venv` |

### Activate virtual environment

| | Command |
|---|---|
| **Bash** | `source .venv/Scripts/activate` |
| **PowerShell** | `.\.venv\Scripts\Activate.ps1` |

> If PowerShell blocks activation: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### Install dependencies (after activating)

| | Command |
|---|---|
| **Bash** | `pip install -e ".[dev,test]"` |
| **PowerShell** | `pip install -e ".[dev,test]"` |

### Deactivate virtual environment

| | Command |
|---|---|
| **Bash** | `deactivate` |
| **PowerShell** | `deactivate` |

---

### Copy `.env.example` → `.env`

| | Command |
|---|---|
| **Bash** | `cp .env.example .env` |
| **PowerShell** | `Copy-Item .env.example .env` |

### Generate a secure `SECRET_KEY` (≥ 32 chars)
key=secrets.token_urlsafe(32)

| | Command |
|---|---|
| **Bash** | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| **PowerShell** | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

### Set `SECRET_KEY` in `.env` directly from terminal

| | Command |
|---|---|
| **Bash** | `echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env` |
| **PowerShell** | `"SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \| Add-Content .env` |

### View current `.env` (redact nothing — for local dev only)

| | Command |
|---|---|
| **Bash** | `cat .env` |
| **PowerShell** | `Get-Content .env` |

---

## Redis

### Start Redis via Docker

| | Command |
|---|---|
| **Bash** | `docker run -d --name redis -p 6379:6379 redis` |
| **PowerShell** | `docker run -d --name redis -p 6379:6379 redis` |

### Stop Redis container

| | Command |
|---|---|
| **Bash** | `docker stop redis && docker rm redis` |
| **PowerShell** | `docker stop redis; docker rm redis` |

### Open Redis CLI

| | Command |
|---|---|
| **Bash** | `redis-cli` |
| **PowerShell** | `redis-cli` |

### Inspect all active game keys

| | Command |
|---|---|
| **Bash** | `redis-cli KEYS "wolf:game:*"` |
| **PowerShell** | `redis-cli KEYS "wolf:game:*"` |

### Read a specific game state (pretty-printed)

| | Command |
|---|---|
| **Bash** | `redis-cli GET wolf:game:<GAME_ID> \| python -m json.tool` |
| **PowerShell** | `redis-cli GET wolf:game:<GAME_ID> \| python -m json.tool` |

### Delete a stuck game

| | Command |
|---|---|
| **Bash** | `redis-cli DEL wolf:game:<GAME_ID>` |
| **PowerShell** | `redis-cli DEL wolf:game:<GAME_ID>` |

### Flush all wolf keys (dev only — destructive)

| | Command |
|---|---|
| **Bash** | `redis-cli --scan --pattern "wolf:*" \| xargs redis-cli DEL` |
| **PowerShell** | `redis-cli --scan --pattern "wolf:*" \| ForEach-Object { redis-cli DEL $_ }` |

### Check a session token

| | Command |
|---|---|
| **Bash** | `redis-cli GET wolf:token:<TOKEN>` |
| **PowerShell** | `redis-cli GET wolf:token:<TOKEN>` |

---

## Running the Server

### Install Python dependencies

| | Command |
|---|---|
| **Bash** | `pip install -e ".[dev]"` (run from `backend-engine/`) |
| **PowerShell** | `pip install -e ".[dev]"` (run from `backend-engine/`) |

### Start the backend (dev, with reload)

| | Command |
|---|---|
| **Bash** | `uvicorn api.main:app --reload --app-dir backend-engine` |
| **PowerShell** | `uvicorn api.main:app --reload --app-dir backend-engine` |

### Start the backend (explicit host + port)

| | Command |
|---|---|
| **Bash** | `uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend-engine` |
| **PowerShell** | `uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend-engine` |

### Health check (requires server running)

| | Command |
|---|---|
| **Bash** | `curl http://localhost:8000/health` |
| **PowerShell** | `Invoke-RestMethod http://localhost:8000/health` |

---

## Testing

### Backend (pytest)

All `pytest` commands run from the project root. No live Redis required — storage tests use `fakeredis`.

### Run all backend tests

| | Command |
|---|---|
| **Bash** | `pytest backend-engine/tests/ -v` |
| **PowerShell** | `pytest backend-engine/tests/ -v` |

### Run stripper security tests only (highest priority)

| | Command |
|---|---|
| **Bash** | `pytest backend-engine/tests/engine/test_stripper.py -v` |
| **PowerShell** | `pytest backend-engine/tests/engine/test_stripper.py -v` |

### Run Redis store tests only

| | Command |
|---|---|
| **Bash** | `pytest backend-engine/tests/storage/ -v` |
| **PowerShell** | `pytest backend-engine/tests/storage/ -v` |

### Run night resolver tests

| | Command |
|---|---|
| **Bash** | `pytest backend-engine/tests/engine/test_night_resolver.py -v` |
| **PowerShell** | `pytest backend-engine/tests/engine/test_night_resolver.py -v` |

### Run a single test by name

| | Command |
|---|---|
| **Bash** | `pytest backend-engine/tests/ -k "test_wolf_majority_kills" -v` |
| **PowerShell** | `pytest backend-engine/tests/ -k "test_wolf_majority_kills" -v` |

### Run with coverage report

| | Command |
|---|---|
| **Bash** | `pytest backend-engine/tests/ --cov=backend-engine --cov-report=term-missing` |
| **PowerShell** | `pytest backend-engine/tests/ --cov=backend-engine --cov-report=term-missing` |

### Stop on first failure

| | Command |
|---|---|
| **Bash** | `pytest backend-engine/tests/ -x` |
| **PowerShell** | `pytest backend-engine/tests/ -x` |

### Show print output during tests

| | Command |
|---|---|
| **Bash** | `pytest backend-engine/tests/ -s -v` |
| **PowerShell** | `pytest backend-engine/tests/ -s -v` |

---

### Frontend (Vitest)

All `npm` commands run from `frontend-display/`.

### Run all frontend tests once

| | Command |
|---|---|
| **Bash** | `cd frontend-display && npm run test` |
| **PowerShell** | `cd frontend-display; npm run test` |

### Watch mode (re-runs on file change)

| | Command |
|---|---|
| **Bash** | `cd frontend-display && npm run test:watch` |
| **PowerShell** | `cd frontend-display; npm run test:watch` |

### With V8 coverage report

| | Command |
|---|---|
| **Bash** | `cd frontend-display && npm run test:coverage` |
| **PowerShell** | `cd frontend-display; npm run test:coverage` |

### Run a specific test file

| | Command |
|---|---|
| **Bash** | `cd frontend-display && npx vitest run src/test/hooks/useWebSocket.test.ts` |
| **PowerShell** | `cd frontend-display; npx vitest run src/test/hooks/useWebSocket.test.ts` |

---

### Full suite via Docker (no local Python/Node required)

### Run backend tests in Docker

| | Command |
|---|---|
| **Bash** | `docker compose -f docker-compose.test.yml run --rm backend-test` |
| **PowerShell** | `docker compose -f docker-compose.test.yml run --rm backend-test` |

### Run frontend tests in Docker

| | Command |
|---|---|
| **Bash** | `docker compose -f docker-compose.test.yml run --rm frontend-test` |
| **PowerShell** | `docker compose -f docker-compose.test.yml run --rm frontend-test` |

### Run both suites (sequential)

| | Command |
|---|---|
| **Bash** | `docker compose -f docker-compose.test.yml run --rm backend-test && docker compose -f docker-compose.test.yml run --rm frontend-test` |
| **PowerShell** | `docker compose -f docker-compose.test.yml run --rm backend-test; docker compose -f docker-compose.test.yml run --rm frontend-test` |

### Rebuild test images (after dependency changes)

| | Command |
|---|---|
| **Bash** | `docker compose -f docker-compose.test.yml build --no-cache` |
| **PowerShell** | `docker compose -f docker-compose.test.yml build --no-cache` |

---

## Debugging

### Enable debug logging for the server

| | Command |
|---|---|
| **Bash** | `DEBUG=true uvicorn api.main:app --reload --app-dir backend-engine --log-level debug` |
| **PowerShell** | `$env:DEBUG="true"; uvicorn api.main:app --reload --app-dir backend-engine --log-level debug` |

### Run pytest with verbose output + no capture (see all logs)

| | Command |
|---|---|
| **Bash** | `pytest backend-engine/tests/ -s -v --log-cli-level=DEBUG` |
| **PowerShell** | `pytest backend-engine/tests/ -s -v --log-cli-level=DEBUG` |

### Open Python REPL with project on path

| | Command |
|---|---|
| **Bash** | `PYTHONPATH=backend-engine python` |
| **PowerShell** | `$env:PYTHONPATH="backend-engine"; python` |

### Import and inspect game state manually in REPL

```python
# After opening REPL with PYTHONPATH=backend-engine
from engine.setup import setup_game
from engine.stripper import player_view
G = setup_game("test", "host-1", {})
print(player_view(G, None))   # display view
```

### Test a REST endpoint with curl

| | Command |
|---|---|
| **Bash** | `curl -s -X POST http://localhost:8000/api/games -H "Content-Type: application/json" -d '{"host_display_name":"Beth","avatar_id":"wolf_01"}' \| python -m json.tool` |
| **PowerShell** | `Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/games -ContentType "application/json" -Body '{"host_display_name":"Beth","avatar_id":"wolf_01"}' \| ConvertTo-Json` |

### Connect to WebSocket manually (requires wscat)

| | Command |
|---|---|
| **Bash** | `npx wscat -c "ws://localhost:8000/ws/<GAME_ID>/display"` |
| **PowerShell** | `npx wscat -c "ws://localhost:8000/ws/<GAME_ID>/display"` |

---

## Reading Logs

### Uvicorn logs (server running in terminal)

Logs print directly to stdout. To redirect to a file:

| | Command |
|---|---|
| **Bash** | `uvicorn api.main:app --app-dir backend-engine 2>&1 \| tee server.log` |
| **PowerShell** | `uvicorn api.main:app --app-dir backend-engine 2>&1 \| Tee-Object server.log` |

### Tail a log file (live updates)

| | Command |
|---|---|
| **Bash** | `tail -f server.log` |
| **PowerShell** | `Get-Content server.log -Wait` |

### Search log for errors

| | Command |
|---|---|
| **Bash** | `grep -i "error\|exception" server.log` |
| **PowerShell** | `Select-String -Path server.log -Pattern "error|exception" -CaseSensitive:$false` |

### Docker Compose logs (full stack)

| | Command |
|---|---|
| **Bash** | `docker compose logs -f` |
| **PowerShell** | `docker compose logs -f` |

### Docker logs — backend only

| | Command |
|---|---|
| **Bash** | `docker compose logs -f backend` |
| **PowerShell** | `docker compose logs -f backend` |

### Docker logs — last 100 lines

| | Command |
|---|---|
| **Bash** | `docker compose logs --tail=100 backend` |
| **PowerShell** | `docker compose logs --tail=100 backend` |

### Filter Docker logs by keyword

| | Command |
|---|---|
| **Bash** | `docker compose logs backend 2>&1 \| grep "Intent error"` |
| **PowerShell** | `docker compose logs backend 2>&1 \| Select-String "Intent error"` |

---

## Git

### Initial setup (already done — reference only)

| | Command |
|---|---|
| **Bash** | `git init && git remote add origin https://github.com/bethCoderNewbie/imposter.game.git` |
| **PowerShell** | `git init; git remote add origin https://github.com/bethCoderNewbie/imposter.game.git` |

### Check remote

| | Command |
|---|---|
| **Bash** | `git remote -v` |
| **PowerShell** | `git remote -v` |

### Status

| | Command |
|---|---|
| **Bash** | `git status` |
| **PowerShell** | `git status` |

### Short status

| | Command |
|---|---|
| **Bash** | `git status --short` |
| **PowerShell** | `git status --short` |

### Stage specific files

| | Command |
|---|---|
| **Bash** | `git add path/to/file.py` |
| **PowerShell** | `git add path/to/file.py` |

### Stage all changes (tracked + untracked, excluding .gitignore)

| | Command |
|---|---|
| **Bash** | `git add .` |
| **PowerShell** | `git add .` |

### Unstage a file

| | Command |
|---|---|
| **Bash** | `git restore --staged path/to/file.py` |
| **PowerShell** | `git restore --staged path/to/file.py` |

### Commit

| | Command |
|---|---|
| **Bash** | `git commit -m "your message"` |
| **PowerShell** | `git commit -m "your message"` |

### Amend last commit message (before push)

| | Command |
|---|---|
| **Bash** | `git commit --amend -m "corrected message"` |
| **PowerShell** | `git commit --amend -m "corrected message"` |

### Push (first time — sets upstream)

| | Command |
|---|---|
| **Bash** | `git push -u origin main` |
| **PowerShell** | `git push -u origin main` |

### Push (subsequent)

| | Command |
|---|---|
| **Bash** | `git push` |
| **PowerShell** | `git push` |

### Pull (rebase — avoids merge commits)

| | Command |
|---|---|
| **Bash** | `git pull --rebase origin main` |
| **PowerShell** | `git pull --rebase origin main` |

### View commit log (one line each)

| | Command |
|---|---|
| **Bash** | `git log --oneline` |
| **PowerShell** | `git log --oneline` |

### View last 5 commits with diff stat

| | Command |
|---|---|
| **Bash** | `git log --oneline --stat -5` |
| **PowerShell** | `git log --oneline --stat -5` |

### View diff of staged changes (what will be committed)

| | Command |
|---|---|
| **Bash** | `git diff --staged` |
| **PowerShell** | `git diff --staged` |

### View diff of working tree (unstaged changes)

| | Command |
|---|---|
| **Bash** | `git diff` |
| **PowerShell** | `git diff` |

### Create and switch to a new branch

| | Command |
|---|---|
| **Bash** | `git checkout -b phase-2-mobile` |
| **PowerShell** | `git checkout -b phase-2-mobile` |

### Switch branch

| | Command |
|---|---|
| **Bash** | `git checkout main` |
| **PowerShell** | `git checkout main` |

### List branches

| | Command |
|---|---|
| **Bash** | `git branch -a` |
| **PowerShell** | `git branch -a` |

### Delete a local branch (after merge)

| | Command |
|---|---|
| **Bash** | `git branch -d phase-2-mobile` |
| **PowerShell** | `git branch -d phase-2-mobile` |

### Stash uncommitted changes

| | Command |
|---|---|
| **Bash** | `git stash` |
| **PowerShell** | `git stash` |

### Restore stash

| | Command |
|---|---|
| **Bash** | `git stash pop` |
| **PowerShell** | `git stash pop` |

### See who last changed a line

| | Command |
|---|---|
| **Bash** | `git blame backend-engine/engine/stripper.py` |
| **PowerShell** | `git blame backend-engine/engine/stripper.py` |

### Search all commits for a string

| | Command |
|---|---|
| **Bash** | `git log -S "player_view" --oneline` |
| **PowerShell** | `git log -S "player_view" --oneline` |

### Reset working tree to last commit (discard all local changes — destructive)

| | Command |
|---|---|
| **Bash** | `git reset --hard HEAD` |
| **PowerShell** | `git reset --hard HEAD` |

### Show what's in a specific commit

| | Command |
|---|---|
| **Bash** | `git show <commit-hash>` |
| **PowerShell** | `git show <commit-hash>` |

### Tag a release

| | Command |
|---|---|
| **Bash** | `git tag v0.1.0 && git push origin v0.1.0` |
| **PowerShell** | `git tag v0.1.0; git push origin v0.1.0` |
