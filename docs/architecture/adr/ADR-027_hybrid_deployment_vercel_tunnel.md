# ADR-027: Hybrid Deployment — Local Backend + Vercel Frontends

## Status
Accepted

## Date
2026-04-16

## Context

The original deployment model requires all player devices to be on the same Wi-Fi network as the host machine. The entire stack (nginx, FastAPI backend, both React frontends) runs locally. The QR code encodes the host's LAN IP; WebSocket and API URLs are derived from `window.location.host`. Players not on the LAN cannot join.

The desired improvement: serve the mobile frontend from Vercel (public internet) while keeping the backend running locally on the host's machine. This eliminates the same-network requirement — players can join from anywhere by scanning a public QR code.

### Constraints

1. **LAN mode must continue to work identically.** No regressions for the existing party-game-on-one-network use case.
2. **HTTPS requirement.** Vercel serves frontends over HTTPS. Browsers block HTTP REST calls and `ws://` WebSocket connections from HTTPS pages (mixed content). The local backend must be reachable via HTTPS.
3. **Backend IP privacy.** The host's home IP should not be exposed to players. A tunnel service places a public HTTPS URL in front of the local backend without revealing the origin IP.
4. **Display client stays local.** The TV/projector display is always on the LAN; only mobile goes to Vercel by default.

---

## Decision

### 1. `getApiBase()` / `getWsBase()` utility modules

Introduce a single `src/utils/backend.ts` in each frontend that centralises all backend URL resolution:

```
Priority chain (mobile):
  1. sessionStorage['ww_backend_url']  ← read from ?b= QR param on scan
  2. VITE_BACKEND_URL                  ← baked at Vercel build time
  3. ''                                ← relative paths (LAN mode, unchanged)

Priority chain (display):
  1. VITE_BACKEND_URL                  ← baked at Docker build time from BACKEND_URL in .env
  2. ''                                ← relative paths (LAN mode)
```

When the priority chain resolves to `''`, `fetch('/api/...')` becomes `fetch('' + '/api/...')` which is identical to the original relative-path call — zero regression in LAN mode.

**Rejected alternative:** Touching every `fetch` call without a shared utility would scatter the logic across 13 call sites and make it hard to change the priority chain later.

### 2. `?b=` QR param for backend URL propagation

The display client embeds the backend URL in the QR code as `?b=<encodedUrl>` whenever `VITE_BACKEND_URL` is set. The mobile client reads this param on app boot (`extractAndStoreBackendUrl()` called before React renders), persists it to `sessionStorage`, then strips it from the address bar.

This covers the **ephemeral tunnel** case where no stable URL exists to bake into Vercel env vars — players just scan the current-session QR and everything works without any Vercel redeploy.

**Rejected alternative:** A server-side `/config.json` endpoint on the backend itself — circular dependency (mobile would need to know the backend URL to fetch the backend URL).

### 3. Cloudflare Tunnel for HTTPS exposure

The local backend must be reachable over HTTPS from the public internet. Cloudflare Tunnel is the recommended option:

| Method | Why preferred / rejected |
|---|---|
| **Cloudflare Quick Tunnel** | Zero-config, no account, free, ephemeral URL printed in logs |
| **Cloudflare Named Tunnel** | Free with account, permanent subdomain, production-grade |
| **ngrok free** | Similar to Cloudflare Quick Tunnel but URL shown less conveniently |
| **Port forwarding + Let's Encrypt** | Exposes host IP, requires router access and TLS config |
| **Tailscale** | Players must install Tailscale — not suitable for party game strangers |

Cloudflare Tunnel hides the host's real IP behind Cloudflare's edge, which is strictly more private than port forwarding.

For a party game with up to ~18 players, traffic is negligible (a few MB per session), so all free-tier options are well within limits.

Two Docker Compose profiles are added (`tunnel`, `tunnel-quick`) so the tunnel starts alongside the stack with `./start.sh --tunnel` or `./start.sh --tunnel-quick`.

### 4. `VITE_MOBILE_URL` for QR target

The display needs to know the Vercel URL of the mobile frontend so the QR code points there instead of the local LAN IP. A new `VITE_MOBILE_URL` env var is baked into the display Docker image (from `MOBILE_URL` in `.env`). Fallback chain: `VITE_MOBILE_URL` → `VITE_HOST_IP` (LAN) → `window.location.origin`.

---

## Consequences

### Positive
- Players can join from any network, not just the host's Wi-Fi.
- Host's real IP is never exposed when using a tunnel.
- Full backward compatibility: LAN mode works exactly as before when `BACKEND_URL` / `MOBILE_URL` are unset.
- No backend code changes required (CORS is already `allow_origins=["*"]`).
- No nginx changes required (tunnel terminates upstream; nginx already proxies `/api/` and `/ws/`).

### Negative / Trade-offs
- In hybrid mode, the display's own API calls are routed through the tunnel (outbound + inbound on the same machine). This is functionally correct but slightly less efficient than a direct LAN call.
- Ephemeral tunnel URLs change each session. If `VITE_BACKEND_URL` is baked into Vercel, it must be updated whenever the tunnel URL changes. The `?b=` QR param sidesteps this, but requires a fresh scan each session.
- Named tunnels require a one-time Cloudflare account setup and a token stored in `.env`.

### No changes required
- `backend-engine/` — CORS already permissive, no auth changes needed
- `nginx.conf` — tunnel terminates upstream; no routing changes needed
- `frontend-display/vite.config.ts` — display stays local in Docker; `base: '/display/'` preserved
