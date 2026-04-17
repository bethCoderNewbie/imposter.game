# Hybrid Deployment Guide: Vercel + Cloudflare Tunnel

Players join from any network. Backend runs on your machine. Mobile frontend is public on Vercel.

---

## How It Works

```
Player phone  ──HTTPS──▶  Vercel (frontend-mobile)
                                  │
                          reads backend URL from ?b= param in QR
                                  │
                         HTTPS/WSS ──▶  Cloudflare Tunnel
                                               │
                                       nginx (your machine :80)
                                               │
                                       FastAPI + Redis (Docker)

TV / Display  ──LAN──▶  nginx  ──▶  frontend-display (Docker, unchanged)
```

The display QR code embeds the tunnel URL as `?b=<url>`. When a player scans it, their phone stores the URL in sessionStorage and uses it for all API and WebSocket calls. **No Vercel redeploy is needed between sessions** when using the ephemeral Quick Tunnel.

---

## Part 1: Vercel (Mobile Frontend)

### Prerequisites
- Node.js installed locally
- Vercel CLI: `npm i -g vercel`
- Vercel account (free): https://vercel.com/signup

### Step 1 — Deploy

```bash
cd frontend-mobile
vercel
```

Vercel will ask a few questions:

| Prompt | Answer |
|---|---|
| Set up and deploy? | `Y` |
| Which scope? | Your username |
| Link to existing project? | `N` |
| Project name | `werewolf-mobile` (or anything) |
| In which directory is your code? | `./` |
| Want to override settings? | `N` |

Wait for the deploy to finish. You will get a URL like:

```
https://werewolf-mobile-abc123.vercel.app
```

**Copy this URL.** This is your `MOBILE_URL`.

### Step 2 — Set the production domain (optional but recommended)

In the Vercel dashboard → your project → Settings → Domains, you can add a custom subdomain or just use the auto-generated URL.

### Step 3 — Set environment variables

In the Vercel dashboard → your project → Settings → Environment Variables, add:

| Name | Value | Environments |
|---|---|---|
| `VITE_BACKEND_URL` | *(leave blank for now — fill after Step 4)* | Production |

> You will come back and fill `VITE_BACKEND_URL` after you have a tunnel URL (Part 2).
> For the ephemeral Quick Tunnel you can leave this blank — the `?b=` QR param handles it automatically.

### Step 4 — Redeploy after setting env vars

```bash
cd frontend-mobile
vercel --prod
```

Or trigger a redeploy from the Vercel dashboard.

### Verify

Open your Vercel URL in a browser. You should see the Werewolf join screen.

---

## Part 2: Cloudflare Tunnel

Two options — pick one.

---

### Option A: Quick Tunnel (recommended for getting started)

**No account needed. Free. URL changes each session.**

The URL is automatically embedded in the QR code via `?b=`, so players always get the right URL just by scanning — no Vercel redeploy needed between sessions.

#### Start

```bash
./start.sh --tunnel-quick
```

#### Get the tunnel URL

```bash
docker compose logs cloudflared-quick 2>&1 | grep -o 'https://[^ ]*trycloudflare[^ ]*'
```

Output looks like:
```
https://random-words-here.trycloudflare.com
```

#### Verify

```bash
curl https://random-words-here.trycloudflare.com/api/health
# Expected: {"status": "ok", ...}
```

#### Set `.env` so the QR code is correct

Add to your `.env`:
```
MOBILE_URL=https://werewolf-mobile-abc123.vercel.app
```

Restart to rebuild the display image with the correct QR target:
```bash
./start.sh --tunnel-quick
```

The QR code now encodes:
```
https://werewolf-mobile-abc123.vercel.app/?g=ABCD&b=https%3A%2F%2Frandom-words-here.trycloudflare.com
```

Players scan → land on Vercel → backend URL extracted from `?b=` → game works.

---

### Option B: Named Tunnel (stable URL, recommended for regular use)

**Free Cloudflare account required. URL is permanent.**

#### Prerequisites

1. A domain managed by Cloudflare (or a free `*.pages.dev` subdomain via Cloudflare Pages).
2. `cloudflared` CLI installed:
   ```bash
   # Windows (Winget)
   winget install Cloudflare.cloudflared

   # macOS (Homebrew)
   brew install cloudflared

   # Linux
   curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
   chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/
   ```

#### One-Time Setup

```bash
# 1. Authenticate (opens browser to Cloudflare login)
cloudflared tunnel login

# 2. Create the tunnel
cloudflared tunnel create werewolf-backend
# Prints: Created tunnel werewolf-backend with id <UUID>

# 3. Route a subdomain to the tunnel (replace with your domain)
cloudflared tunnel route dns werewolf-backend backend.yourdomain.com
# This creates a CNAME record in Cloudflare DNS automatically.

# 4. Get the tunnel token (used by Docker)
cloudflared tunnel token werewolf-backend
# Prints a long token string — copy it
```

#### Configure `.env`

```bash
CLOUDFLARE_TUNNEL_TOKEN=<paste token here>
BACKEND_URL=https://backend.yourdomain.com
MOBILE_URL=https://werewolf-mobile-abc123.vercel.app
```

#### Set Vercel environment variable

In Vercel dashboard → Settings → Environment Variables:

| Name | Value |
|---|---|
| `VITE_BACKEND_URL` | `https://backend.yourdomain.com` |

Redeploy:
```bash
cd frontend-mobile && vercel --prod
```

#### Start

```bash
./start.sh --tunnel
```

#### Verify

```bash
curl https://backend.yourdomain.com/api/health
# Expected: {"status": "ok", ...}
```

The QR code now encodes:
```
https://werewolf-mobile-abc123.vercel.app/?g=ABCD&b=https%3A%2F%2Fbackend.yourdomain.com
```

---

## Part 3: Full Config Reference

### `.env` (host machine)

```bash
# ── Required ──────────────────────────────────────────────────────────────────
SECRET_KEY=<at-least-32-random-chars>

# ── Hybrid deployment ─────────────────────────────────────────────────────────

# Public HTTPS URL of your tunnel (ngrok, Cloudflare, port-forward, etc.)
# Baked into the display Docker image so the QR ?b= param is correct.
# Also set as VITE_BACKEND_URL in your Vercel project env vars.
BACKEND_URL=https://backend.yourdomain.com       # Named tunnel
# BACKEND_URL=                                   # Leave blank for Quick Tunnel

# Vercel URL of the mobile frontend.
# When set, the display QR points here instead of your LAN IP.
MOBILE_URL=https://werewolf-mobile-abc123.vercel.app

# Named tunnel only: token from `cloudflared tunnel token werewolf-backend`
CLOUDFLARE_TUNNEL_TOKEN=<token>
# Leave blank for Quick Tunnel — token not needed
```

### Vercel project env vars (`frontend-mobile`)

| Variable | Quick Tunnel | Named Tunnel |
|---|---|---|
| `VITE_BACKEND_URL` | *(leave blank)* | `https://backend.yourdomain.com` |

> Quick Tunnel: leave `VITE_BACKEND_URL` unset. The `?b=` QR param is the source of truth each session.
> Named Tunnel: set it once and forget it.

### `frontend-mobile/vercel.json` (already committed)

```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }],
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite"
}
```

This is the only Vercel config file needed. Vercel auto-detects the `vite.config.ts`.

---

## Part 4: Session-by-Session Checklist

### Quick Tunnel (every game session)

```bash
# 1. Start the stack with tunnel
./start.sh --tunnel-quick

# 2. Confirm tunnel is up (takes ~5 seconds)
docker compose logs cloudflared-quick 2>&1 | grep trycloudflare

# 3. Confirm backend is reachable
curl https://<printed-url>/api/health

# 4. Open display on TV
# http://<LAN-IP>/display/

# 5. Players scan QR — done
```

### Named Tunnel (one-time setup, then same as LAN)

```bash
./start.sh --tunnel
# That's it — tunnel URL is stable, Vercel has it baked in
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Player scans QR, sees blank page | Vercel deploy not live | `vercel --prod` from `frontend-mobile/` |
| Player scans QR, "Network Error" on join | Backend not reachable | `curl <tunnel-url>/api/health` — check tunnel is running |
| WS closes immediately, browser console shows mixed content error | Mobile served over HTTPS, backend over HTTP | Use a tunnel (HTTPS); never expose backend via plain HTTP to Vercel |
| QR code shows LAN IP, not Vercel URL | `MOBILE_URL` not set in `.env` | Add `MOBILE_URL=<vercel-url>` to `.env` and `./start.sh` again |
| `?b=` missing from QR URL | `BACKEND_URL` not set (Quick Tunnel case) | Leave it blank — Quick Tunnel embeds URL dynamically. Named Tunnel: set `BACKEND_URL` in `.env` |
| Tunnel token error on start | `CLOUDFLARE_TUNNEL_TOKEN` wrong or missing | Re-run `cloudflared tunnel token werewolf-backend` and update `.env` |
| Tunnel starts but `curl` times out | Tunnel routes to wrong port | Tunnel must point to port 80 (nginx). Check your `config.yml` if using a named tunnel config file |
| "Game not found" after host restarts | Old `?b=` URL stored in sessionStorage | Player clears site data or opens a fresh browser tab |
