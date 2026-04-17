# Hybrid Deployment Guide: Vercel + Cloudflare Tunnel

Players join from any network. Backend runs on your machine. Both frontends are on Vercel.

---

## Architecture

```
Host browser  ──HTTPS──▶  Vercel (frontend-display)   https://imposter-game-swart.vercel.app
                                  │
                          VITE_BACKEND_URL → https://backend.imposter.com
                                  │
Player phone  ──HTTPS──▶  Vercel (frontend-mobile)    https://<mobile-url>.vercel.app
                                  │
                          reads backend URL from ?b= param in QR
                                  │
                         HTTPS/WSS ──▶  Cloudflare Tunnel  https://backend.imposter.com
                                               │
                                       nginx (your machine :80)
                                               │
                                       FastAPI + Redis (Docker)
```

The display QR code embeds the tunnel URL as `?b=<url>`. When a player scans it, their phone stores the URL in sessionStorage and uses it for all API and WebSocket calls.

---

## Current State

| Item | Status | Value |
|---|---|---|
| Display Vercel project | ✅ Deployed | `https://imposter-game-swart.vercel.app` |
| Mobile Vercel project | ⬜ Not yet deployed | — |
| Cloudflare Tunnel | ✅ Configured | `https://backend.imposter.com` |
| `CLOUDFLARE_TUNNEL_TOKEN` | ✅ Set in `.env` | — |
| `BACKEND_URL` | ✅ Set in `.env` | `https://backend.imposter.com` |
| `MOBILE_URL` | ⬜ Needs mobile deploy first | — |

---

## Part 1: Vercel — Display Frontend

**Project:** `imposter-game-swart` → `https://imposter-game-swart.vercel.app`
**Source:** `frontend-display/`

### Environment Variables

In Vercel dashboard → `imposter-game-swart` project → **Settings → Environment Variables**:

| Variable | Value | Required |
|---|---|---|
| `VITE_BACKEND_URL` | `https://backend.imposter.com` | ✅ Yes |
| `VITE_MOBILE_URL` | `https://<mobile-url>.vercel.app` | ✅ Yes — fill after mobile deploy |

> **Why `VITE_MOBILE_URL`?** The display generates the QR code. This tells it to point the QR at the mobile Vercel URL instead of defaulting to its own origin.

### Redeploy after setting env vars

```bash
cd frontend-display
vercel --prod
```

Or click **Redeploy** in the Vercel dashboard.

---

## Part 2: Vercel — Mobile Frontend

**Source:** `frontend-mobile/`

### Step 1 — Deploy

```bash
cd frontend-mobile
vercel
```

| Prompt | Answer |
|---|---|
| Set up and deploy? | `Y` |
| Which scope? | Your username |
| Link to existing project? | `N` |
| Project name | `imposter-game-mobile` (or anything) |
| In which directory is your code? | `./` |
| Want to override settings? | `N` |

Copy the resulting URL — e.g. `https://imposter-game-mobile-abc123.vercel.app`

### Step 2 — Set environment variables

In Vercel dashboard → mobile project → **Settings → Environment Variables**:

| Variable | Value | Required |
|---|---|---|
| `VITE_BACKEND_URL` | `https://backend.imposter.com` | ✅ Yes |

### Step 3 — Redeploy

```bash
vercel --prod
```

### Step 4 — Update `.env` on host machine

```
MOBILE_URL=https://imposter-game-mobile-abc123.vercel.app
```

### Step 5 — Update display Vercel env var

In Vercel dashboard → `imposter-game-swart` → **Settings → Environment Variables**:

Set `VITE_MOBILE_URL` = `https://imposter-game-mobile-abc123.vercel.app`

Then redeploy the display:
```bash
cd frontend-display && vercel --prod
```

---

## Part 3: Complete Variable Reference

### `.env` (host machine — never commit this file)

```bash
SECRET_KEY=<at-least-32-random-chars>

# ── Hybrid deployment ─────────────────────────────────────────────────────────
CLOUDFLARE_TUNNEL_TOKEN=<token from Cloudflare dashboard>
BACKEND_URL=https://backend.imposter.com
MOBILE_URL=https://imposter-game-mobile-abc123.vercel.app
```

### Vercel — Display project (`imposter-game-swart`)

| Variable | Value | Effect |
|---|---|---|
| `VITE_BACKEND_URL` | `https://backend.imposter.com` | All display API/WS calls go to the tunnel |
| `VITE_MOBILE_URL` | `https://imposter-game-mobile-abc123.vercel.app` | QR code points to the mobile join page |

### Vercel — Mobile project

| Variable | Value | Effect |
|---|---|---|
| `VITE_BACKEND_URL` | `https://backend.imposter.com` | Fallback if player didn't scan QR (typed URL directly) |

> **Note:** `VITE_BACKEND_URL` on the mobile project is a fallback only. Players who scan the QR always get the backend URL from the `?b=` param, which is embedded dynamically by the display — no redeploy needed when the tunnel URL changes.

### Cloudflare Tunnel — Public Hostname config

In Zero Trust → Networks → Tunnels → your tunnel → **Public Hostname**:

| Field | Value |
|---|---|
| Subdomain | `backend` |
| Domain | `imposter.com` |
| Service type | `HTTP` |
| URL | `nginx:80` |

---

## Part 4: Launch

### Named tunnel (your current setup)

```bash
./start.sh --tunnel
```

### Verify everything is wired up

```bash
# 1. Backend reachable via tunnel
curl https://backend.imposter.com/api/health
# Expected: {"status": "ok", ...}

# 2. Display loads
# Open https://imposter-game-swart.vercel.app in browser
# Should show Create Match screen

# 3. Create a match — check the QR URL
# QR should encode: https://imposter-game-mobile-abc123.vercel.app/?g=XXXX&b=https%3A%2F%2Fbackend.imposter.com

# 4. Player scans QR on a phone not on your WiFi
# Should reach the mobile join form and successfully join the lobby
```

---

## Part 5: Session Checklist

```bash
# Start the stack
./start.sh --tunnel

# Check tunnel is up
curl https://backend.imposter.com/api/health

# Open display in browser (any device, any network)
# https://imposter-game-swart.vercel.app

# Players scan QR from the lobby screen — done
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Display shows blank page / broken styles | `VITE_BACKEND_URL` not set in Vercel | Add env var in dashboard and redeploy |
| QR code points to display URL, not mobile join page | `VITE_MOBILE_URL` not set in display project | Add env var in dashboard and redeploy |
| Player scans QR, "Network Error" on join | Backend tunnel not running | `./start.sh --tunnel` and `curl https://backend.imposter.com/api/health` |
| WS closes immediately — mixed content error | Backend not HTTPS | Tunnel must be HTTPS; check Cloudflare dashboard |
| `?b=` missing from QR URL | `VITE_BACKEND_URL` not baked into display | Set env var in display Vercel project and redeploy |
| Tunnel token error on `./start.sh --tunnel` | `CLOUDFLARE_TUNNEL_TOKEN` missing or wrong | Check `.env`; re-run `cloudflared tunnel token werewolf-backend` |
| "Game not found" after host restarts | Stale `?b=` URL in player's sessionStorage | Player opens a fresh tab or clears site data |
| Display API calls fail (create match, kick, etc.) | `VITE_BACKEND_URL` not set | Set in display Vercel project env vars |
