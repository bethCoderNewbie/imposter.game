# Hybrid Deployment Guide: Vercel + Cloudflare Tunnel

Players join from any network. Backend runs on the host machine. Mobile frontend is on Vercel.

---

## Architecture

```
Host browser  ──LAN──▶  http://<LAN-IP>/display/       (Docker nginx, as always)
                                │
                        direct LAN → FastAPI + Redis

Player phone  ──HTTPS──▶  https://imposter-mobile.vercel.app
                                │
                        reads ?b= from QR code
                                │
                       WSS/HTTPS ──▶  https://backend.imposter.com  (Cloudflare Tunnel)
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
| Backend tunnel | `https://backend.imposter.com` | Cloudflare Tunnel → local nginx |
| Display | `http://<LAN-IP>/display/` | Host only — served by Docker |

---

## Vercel Environment Variables

### Mobile project (`imposter-mobile`)

Vercel dashboard → `imposter-mobile` → **Settings → Environment Variables**

| Variable | Value |
|---|---|
| `VITE_BACKEND_URL` | `https://backend.imposter.com` |

After adding: click **Redeploy** or run:
```bash
cd frontend-mobile && vercel --prod
```

> `VITE_BACKEND_URL` is a fallback for players who navigate directly to the URL without scanning a QR code. Players who scan the QR always get the backend URL from the `?b=` param embedded by the display.

---

## Host Machine `.env`

```bash
SECRET_KEY=<at-least-32-random-chars>

CLOUDFLARE_TUNNEL_TOKEN=<your token>
BACKEND_URL=https://backend.imposter.com
MOBILE_URL=https://imposter-mobile.vercel.app
```

All three hybrid vars are set. The display Docker build bakes `MOBILE_URL` into the QR code and `BACKEND_URL` into the `?b=` param.

---

## Cloudflare Tunnel — Public Hostname

Zero Trust → Networks → Tunnels → your tunnel → **Public Hostname**:

| Field | Value |
|---|---|
| Subdomain | `backend` |
| Domain | `imposter.com` |
| Service type | `HTTP` |
| URL | `nginx:80` |

---

## Launch

```bash
./start.sh --tunnel
```

---

## Verify

```bash
# 1. Backend reachable
curl https://backend.imposter.com/api/health
# Expected: {"status":"ok",...}

# 2. Open display on TV (local)
# http://<LAN-IP>/display/
# Create a match — the QR should encode:
# https://imposter-mobile.vercel.app/?g=XXXX&b=https%3A%2F%2Fbackend.imposter.com

# 3. Player scans QR on a phone not on your WiFi
# Should load the join form and successfully enter the lobby
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| QR code shows LAN IP, not Vercel URL | `MOBILE_URL` not set or Docker not rebuilt | Set in `.env` and `./start.sh --tunnel` to rebuild |
| `?b=` missing from QR URL | `BACKEND_URL` not set in `.env` | Add `BACKEND_URL=https://backend.imposter.com` and restart |
| Player "Network Error" on join | Tunnel not running | `curl https://backend.imposter.com/api/health` |
| WS closes immediately — mixed content | Backend not HTTPS from player's phone | Confirm tunnel is HTTPS; never use plain HTTP |
| Tunnel token error on start | `CLOUDFLARE_TUNNEL_TOKEN` wrong | Check `.env`; re-get token from Cloudflare dashboard |
| "Game not found" after host restarts | Stale `?b=` in player sessionStorage | Player opens a fresh tab |
