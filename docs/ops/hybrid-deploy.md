# Hybrid Deployment Guide: Vercel + Cloudflare Tunnel

Players join from any network. Backend runs on the host machine. Mobile frontend is on Vercel.

---

## Architecture

```
Host browser  ──LAN──▶  http://<LAN-IP>/display/       (Docker nginx, unchanged)
                                │
                        direct LAN → FastAPI + Redis

Player phone  ──HTTPS──▶  https://imposter-mobile.vercel.app
                                │
                        reads ?b= from QR code (or VITE_BACKEND_URL fallback)
                                │
                       WSS/HTTPS ──▶  https://backend.imposter.com
                                               │
                                       Cloudflare Tunnel
                                               │
                                       nginx (host machine :80)
                                               │
                                       FastAPI + Redis (Docker)
```

---

## Deployed URLs

| Service | URL | Notes |
|---|---|---|
| Mobile (Vercel) | `https://imposter-mobile.vercel.app` | Players scan QR and land here |
| Backend tunnel | `https://backend.imposter.com` | Cloudflare Named Tunnel → local nginx |
| Display | `http://<LAN-IP>/display/` | Host only — served by Docker, LAN only |

---

## One-Time Cloudflare Setup

### 1. Tunnel token
Already configured. Token stored in `.env` as `CLOUDFLARE_TUNNEL_TOKEN`.

Tunnel ID: `b891dd22-6d40-441d-b60a-6479a61c8b4b`

### 2. DNS record (Cloudflare dashboard)

`dash.cloudflare.com` → `imposter.com` → **DNS → Records → Add record**

| Field | Value |
|---|---|
| Type | `CNAME` |
| Name | `backend` |
| Target | `b891dd22-6d40-441d-b60a-6479a61c8b4b.cfargotunnel.com` |
| Proxy status | **Proxied** (orange cloud ☁️) |

### 3. SSL mode (Cloudflare dashboard)

`dash.cloudflare.com` → `imposter.com` → **SSL/TLS → Overview**

Set encryption mode to: **Full**

> **Why Full?** Cloudflare terminates TLS at its edge. The tunnel forwards plain HTTP to nginx:80 internally — no cert needed on the origin. "Full (Strict)" would fail; "Flexible" causes cipher errors.

### 4. Tunnel public hostname (Zero Trust dashboard)

`one.dash.cloudflare.com` → **Zero Trust → Networks → Tunnels → imposter-backend → Hostname routes**

| Field | Value |
|---|---|
| Subdomain | `backend` |
| Domain | `imposter.com` |
| Service type | `HTTP` |
| URL | `nginx:80` |

---

## Vercel Environment Variables

### Mobile project (`imposter-mobile`)

`vercel.com` → `imposter-mobile` → **Settings → Environment Variables**

| Variable | Value | Purpose |
|---|---|---|
| `VITE_BACKEND_URL` | `https://backend.imposter.com` | Fallback when player navigates directly (no QR scan) |

### Display project (`imposter-game-swart`) — optional, if using Vercel display

| Variable | Value | Purpose |
|---|---|---|
| `VITE_BACKEND_URL` | `https://backend.imposter.com` | Display API/WS calls via tunnel |
| `VITE_MOBILE_URL` | `https://imposter-mobile.vercel.app` | QR code target URL |

> The display is normally served from Docker (LAN), not Vercel. If using the Docker display, these are not needed — `BACKEND_URL` and `MOBILE_URL` in `.env` handle it.

---

## Host Machine `.env`

Full variable reference — all variables and where they flow:

```bash
# ── Required ───────────────────────────────────────────────────────────────────
SECRET_KEY=<at-least-32-random-chars>

# ── Redis / DB ─────────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0      # local dev only; Docker uses redis://redis:6379
SCHEMA_VERSION=0.4

# ── Phase timers (seconds) ─────────────────────────────────────────────────────
NIGHT_TIMER_SECONDS=60
DAY_TIMER_SECONDS=180
VOTE_TIMER_SECONDS=90
ROLE_DEAL_TIMER_SECONDS=30
HUNTER_PENDING_TIMER_SECONDS=30

# ── Narrator ───────────────────────────────────────────────────────────────────
NARRATOR_ENABLED=true
NARRATOR_MODE=prebaked

# ── Hybrid deployment ──────────────────────────────────────────────────────────
CLOUDFLARE_TUNNEL_TOKEN=<token from Cloudflare dashboard>
BACKEND_URL=https://backend.imposter.com
MOBILE_URL=https://imposter-mobile.vercel.app
```

### Where each hybrid variable flows

| `.env` variable | Backend container | Display Docker build | cloudflared |
|---|---|---|---|
| `SECRET_KEY` | ✅ `SECRET_KEY` | — | — |
| `BACKEND_URL` | ✅ `BACKEND_PUBLIC_URL` → absolute photo/TTS URLs | ✅ `VITE_QR_BACKEND_URL` → QR `?b=` embed | — |
| `MOBILE_URL` | — | ✅ `VITE_MOBILE_URL` → QR target URL | — |
| `CLOUDFLARE_TUNNEL_TOKEN` | — | — | ✅ tunnel auth |

> **`VITE_QR_BACKEND_URL` vs `VITE_BACKEND_URL`:** The display Docker build intentionally does NOT set `VITE_BACKEND_URL`. Display API/WS calls always use LAN-relative paths. Only the QR code's `?b=` param uses the tunnel URL (via `VITE_QR_BACKEND_URL`). This prevents display from breaking when running without `--tunnel`.

---

## Launch

```bash
./start.sh --tunnel
```

### What `--tunnel` does
1. Reads `CLOUDFLARE_TUNNEL_TOKEN` from `.env`
2. Starts the `cloudflared` Docker service (profile: `tunnel`)
3. Rebuilds display image with `VITE_QR_BACKEND_URL` and `VITE_MOBILE_URL` baked in
4. Passes all `.env` vars to the backend container

---

## Verify

```bash
# 1. Backend reachable via tunnel
curl -s https://backend.imposter.com/api/health
# Expected: {"status":"ok","schema_version":"0.4"}

# 2. Open display on TV (LAN)
# http://<LAN-IP>/display/
# Create a match — QR should encode:
# https://imposter-mobile.vercel.app/?g=XXXX&b=https%3A%2F%2Fbackend.imposter.com

# 3. Player scans QR on a phone NOT on your WiFi
# Should load join form at imposter-mobile.vercel.app and join the lobby

# 4. Check WSS in browser devtools (mobile)
# Network → WS → should show: wss://backend.imposter.com/ws/...
```

---

## Session Checklist

```bash
# Each time you want to host with internet players:
./start.sh --tunnel

# Confirm tunnel is up:
curl -s https://backend.imposter.com/api/health

# Open display (LAN):
# http://<LAN-IP>/display/

# Players anywhere scan the QR — done
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `curl` health returns nothing / SSL error | DNS CNAME missing or SSL mode wrong | Add CNAME in Cloudflare DNS; set SSL/TLS to **Full** |
| DNS resolves to home IP (`64.x.x.x`) | A record instead of CNAME | Delete A record, add CNAME to `cfargotunnel.com` |
| `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` | SSL mode not set to Full | `dash.cloudflare.com` → `imposter.com` → SSL/TLS → Overview → **Full** |
| Tunnel shows "Down" in Zero Trust dashboard | Container not running | `./start.sh --tunnel` |
| "Network error. Is the server running?" on Vercel mobile | `VITE_BACKEND_URL` not set or tunnel down | Set env var in Vercel project; confirm `curl` health passes |
| QR code shows LAN IP, not Vercel URL | `MOBILE_URL` not in `.env` or not rebuilt | Set `MOBILE_URL` in `.env` and `./start.sh --tunnel` |
| `?b=` missing from QR URL | `BACKEND_URL` not in `.env` | Add `BACKEND_URL=https://backend.imposter.com` and rebuild |
| Display "Network error" in LAN mode (no tunnel) | Old bug — fixed | Ensure you have latest code (`git pull`) |
| WS closes immediately after connect | Mixed content — backend not HTTPS | Confirm tunnel CNAME + SSL Full are both set |
| Player avatar photos broken for remote players | `BACKEND_PUBLIC_URL` not set | Ensure `BACKEND_URL` is in `.env` (forwarded automatically) |
| "Game not found" after restart | Stale `?b=` in player sessionStorage | Player opens a fresh browser tab |
| Docker "network not found" error | Stale Docker network | `docker network prune -f && ./start.sh --tunnel` |
