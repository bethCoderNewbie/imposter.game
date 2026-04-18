# INC-002: Cloudflare Page Rule (SSL: Off) Causes WebSocket 301 HTTPS→HTTP Redirect

| Field | Value |
|---|---|
| **Date** | 2026-04-17 |
| **Duration** | ~1 hour (same session as INC-001) |
| **Severity** | P1 — All players stuck on "Reconnecting…" after joining |
| **Status** | Resolved |
| **Affected surface** | `wss://backend-imposter.notist.cc/ws/*` (hybrid/internet-player path only) |
| **LAN mode affected** | No |

---

## Summary

After the CORS Worker fix (INC-001), players could join the lobby via `POST /api/players/register` but the mobile app showed "Reconnecting…" immediately after. The WebSocket upgrade to `wss://backend-imposter.notist.cc/ws/*` was returning a 301 redirect to `http://` (downgrade), which browsers refuse to follow for WebSocket connections. The root cause was a Page Rule (`SSL: Off`) that was created during the INC-001 investigation and was never deleted. It overrode the zone-level SSL mode (`Full`) for all traffic on `backend-imposter.notist.cc/*`, including WebSocket upgrade requests.

---

## Timeline

| Time (UTC) | Event |
|---|---|
| ~21:50 | INC-001 resolved — REST API calls working, players can join lobby |
| ~21:55 | Players report "Reconnecting…" — game never loads after join |
| ~22:00 | WS upgrade headers test: `curl -H "Upgrade: websocket" ...` → 301 to `http://` |
| ~22:05 | Confirmed: plain GET to `/ws/` → 502 (expected); WS upgrade → 301 (not expected) |
| ~22:10 | Zone SSL setting confirmed `full` via Cloudflare API |
| ~22:12 | Active Page Rules queried — found `backend-imposter.notist.cc/*` → `ssl: off` (active) |
| ~22:13 | Page Rule deleted via Cloudflare API (`DELETE /pagerules/<id>`) |
| ~22:14 | **All clear**: `wss://` no longer redirects; players connect and stay connected |

---

## Root Cause — 5 Whys

**Symptom:** Mobile app shows "Reconnecting…" indefinitely after joining lobby.

| # | Why? | Answer |
|---|---|---|
| 1 | Why did the app stay on "Reconnecting…"? | The WebSocket connection never upgraded — browser received a 301 redirect and aborted |
| 2 | Why did the WebSocket upgrade return 301? | Cloudflare redirected `wss://` to `http://` (HTTPS→HTTP downgrade) |
| 3 | Why did Cloudflare downgrade the connection? | An active Page Rule set `SSL: Off` for `backend-imposter.notist.cc/*`, overriding the zone-level `Full` SSL mode |
| 4 | Why was there a `SSL: Off` Page Rule? | It was created during the INC-001 investigation as a misguided attempt to fix the CORS 502. It was "deleted" in the dashboard but the deletion may not have saved. |
| 5 | Why wasn't it caught before the session ended? | INC-001 was verified by checking REST API responses (200), not WebSocket upgrade behavior. The 301 was only visible when a WS upgrade was attempted. |

**True root cause:** A stale Page Rule (`SSL: Off`) left over from the INC-001 investigation overrode the zone SSL mode and caused Cloudflare to downgrade WebSocket upgrade requests to HTTP. REST calls (which follow 301 redirects) appeared to work, masking the issue until WS upgrade was tested.

---

## Resolution

Deleted the stale Page Rule via the Cloudflare REST API:

```bash
curl -s -X DELETE \
  -H "Authorization: Bearer <TOKEN>" \
  "https://api.cloudflare.com/client/v4/zones/1bdc0047d1beaeb9e41cc9fff7a1b1a5/pagerules/fa0b463563e682c4d31b1a1201edfa34"
# Returns: {"result":{"id":"fa0b463563e682c4d31b1a1201edfa34"},"success":true,...}
```

No code changes required. The zone-level SSL mode was already correctly set to `Full`.

---

## Diagnosis Commands Used

```bash
# 1. Check zone SSL mode
curl -s -H "Authorization: Bearer <TOKEN>" \
  "https://api.cloudflare.com/client/v4/zones/<ZONE_ID>/settings/ssl"
# Expected: "value":"full"

# 2. List active page rules
curl -s -H "Authorization: Bearer <TOKEN>" \
  "https://api.cloudflare.com/client/v4/zones/<ZONE_ID>/pagerules?status=active"
# Found: id=fa0b..., action ssl:off, target=backend-imposter.notist.cc/*

# 3. Reproduce the 301
curl -s -w "\nHTTP:%{http_code}" \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  "https://backend-imposter.notist.cc/ws/TESTGAME/TESTPLAYER"
# Before fix: HTTP:301, Location: http://...
# After fix:  HTTP:101 or 502 (502 = no such game, 101 = valid game)
```

---

## Required API Token Permissions

Minimum read + delete permissions to diagnose and fix this class of issue:

| Scope | Permission | Level |
|---|---|---|
| Zone | Zone Settings | Read |
| Zone | Page Rules | Edit |

**How to create at `dash.cloudflare.com`:**
1. My Profile → API Tokens → Create Token → Create Custom Token
2. Add two permission rows above, scoped to `notist.cc` (specific zone)
3. Create Token → copy the token string

---

## Follow-up Actions

- [x] Delete the `SSL: Off` Page Rule
- [ ] Add WebSocket upgrade test to pre-game checklist: `curl -H "Upgrade: websocket" ... | grep HTTP:101`
- [ ] Document the Page Rule danger in `hybrid-deploy.md` "What not to do" section
- [ ] Add runbook entry for WebSocket 301 symptom *(done in this session)*
