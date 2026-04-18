# INC-001: Cloudflare Blocks CORS OPTIONS Preflights — Players Cannot Join via Vercel

| Field | Value |
|---|---|
| **Date** | 2026-04-17 |
| **Duration** | ~3 hours (active investigation) |
| **Severity** | P1 — All remote players unable to join any game |
| **Status** | Resolved |
| **Affected surface** | `https://imposter-mobile.vercel.app` (hybrid/internet-player path only) |
| **LAN mode affected** | No |

---

## Summary

Players navigating to `https://imposter-mobile.vercel.app/?g=<CODE>` saw "Network error. Is the server running?" immediately on form submit. The Cloudflare Named Tunnel, nginx, FastAPI backend, and Redis were all healthy. The failure was entirely at Cloudflare's edge: it returned 502 for every HTTP OPTIONS preflight request before the request reached the origin.

---

## Timeline

| Time (UTC) | Event |
|---|---|
| ~20:00 | First report: player cannot join at Vercel URL |
| 20:10 | Confirmed backend reachable: `curl https://backend-imposter.notist.cc/api/health` → 200 |
| 20:15 | `VITE_BACKEND_URL` confirmed baked into current Vercel build |
| 20:25 | OPTIONS preflight test → 502; POST directly → 200. CORS preflight identified as root cause |
| 20:30 | Confirmed OPTIONS is blocked *before* reaching nginx (no log entry in `imposter-nginx-1`) |
| 20:35 | Confirmed nginx + cloudflared handle OPTIONS correctly when accessed directly from Docker network |
| 20:50 | WAF Custom Rule (Skip OPTIONS) created — no effect |
| 21:00 | Browser Integrity Check disabled — no effect |
| 21:10 | Zaraz disabled — no effect |
| 21:20 | Page Rule `SSL: Off` created (incorrect — broke GET/POST) |
| 21:35 | Cloudflare Worker `cors-proxy-backend` deployed; route bound to `backend-imposter.notist.cc/*` |
| 21:40 | OPTIONS → 204 ✓; but GET/POST → 502 (SSL: Off page rule now breaking pass-through) |
| 21:45 | SSL: Off page rule deleted |
| 21:50 | **All clear**: OPTIONS → 204, GET → 200, POST → 200 |

---

## Root Cause — 5 Whys

**Symptom:** "Network error. Is the server running?" on form submit at Vercel mobile app.

| # | Why? | Answer |
|---|---|---|
| 1 | Why did the browser throw a network error? | `fetch()` threw a JavaScript exception — not an HTTP error code |
| 2 | Why did `fetch()` throw instead of returning a response? | The browser blocked the request because the CORS OPTIONS preflight returned 502, not 200 |
| 3 | Why did the CORS OPTIONS preflight return 502? | Cloudflare's edge returned 502 for all OPTIONS requests before forwarding them to the tunnel origin |
| 4 | Why did Cloudflare block OPTIONS preflights? | Cloudflare's security layer (WAF managed rules or HTTP DDoS protection) treats `OPTIONS + Access-Control-Request-Method: POST` as a suspicious pattern on the free plan |
| 5 | Why wasn't this caught before go-live? | The hybrid deployment was only tested with LAN-local direct requests and same-machine curl; no cross-origin browser test was run from outside the network before players attempted to join |

**True root cause:** No cross-origin end-to-end test of the browser join flow from a different network before players attempted to use it. The CORS preflight path was only exercised by real browser traffic.

---

## Resolution

A **Cloudflare Worker** (`cors-proxy-backend`) was added as a route on `backend-imposter.notist.cc/*`. The Worker runs at the edge *before* Cloudflare's security inspection layer and:

1. If `request.method === 'OPTIONS'` → returns a synthetic 204 response with CORS headers directly.
2. All other methods → `return fetch(request)` (passes through to the tunnel unchanged).

```js
export default {
  async fetch(request) {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          'Access-Control-Max-Age': '86400',
        },
      })
    }
    return fetch(request)
  },
}
```

**Contributing mistake:** During investigation a `SSL: Off` Page Rule was created on `backend-imposter.notist.cc/*`. This broke GET/POST pass-through because it overrode the tunnel's SSL negotiation. It was deleted before final resolution.

---

## Code Changes Made (same session)

| File | Change | Why |
|---|---|---|
| `frontend-mobile/src/utils/backend.ts` | Removed `history.replaceState` that stripped `?b=` from address bar | Shared URLs (copy-paste from address bar) now carry the backend param, making them self-contained |

---

## Follow-up Actions

- [ ] Add cross-origin browser join test to CI (or pre-game checklist) that runs from a device not on the host LAN
- [ ] Document the Worker setup in `hybrid-deploy.md` as a required one-time step
- [ ] Add runbook entry for `OPTIONS → 502` symptom
- [ ] Delete the stale `?b=`-stripping comment in `backend.ts` JSDoc *(done in this session)*
