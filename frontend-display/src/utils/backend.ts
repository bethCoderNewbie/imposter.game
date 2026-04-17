/**
 * Backend URL utilities for hybrid deployment (local backend + Vercel/remote frontend).
 *
 * For the display client the priority is simpler — no QR-param injection, just:
 *   1. VITE_BACKEND_URL  — baked at Docker build time from BACKEND_URL in .env
 *   2. ''                — relative paths (LAN mode, default)
 *
 * getApiBase() also controls what URL the QR code embeds via ?b= so that mobile
 * clients scanning the code know where to reach the backend.
 */

/** Returns the base URL for all REST API calls. Empty string in LAN mode. */
export function getApiBase(): string {
  return (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/$/, '')
}

/** Returns the WebSocket base URL for the display connection. */
export function getWsBase(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const env = import.meta.env.VITE_BACKEND_URL
  if (env) return env.replace(/^https?:\/\//, `${proto}//`)
  return `${proto}//${window.location.host}`
}
