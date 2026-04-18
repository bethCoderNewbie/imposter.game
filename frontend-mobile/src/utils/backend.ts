/**
 * Backend URL utilities for hybrid deployment (local backend + Vercel frontend).
 *
 * Priority chain for locating the backend:
 *   1. sessionStorage['ww_backend_url']  — set when player scans a QR with ?b= param
 *   2. VITE_BACKEND_URL                  — baked at Vercel build time (stable tunnel URL)
 *   3. ''                                — relative paths (LAN mode, default)
 *
 * When empty, all fetch('/api/...') calls resolve relative to the current origin,
 * preserving identical behaviour to the original LAN-only deployment.
 */

/** Returns the base URL for all REST API calls. Empty string in LAN mode. */
export function getApiBase(): string {
  if (typeof window !== 'undefined') {
    const stored = sessionStorage.getItem('ww_backend_url')
    if (stored) return stored.replace(/\/$/, '')
  }
  return (import.meta.env.VITE_BACKEND_URL ?? '').replace(/\/$/, '')
}

/** Returns the WebSocket base URL (e.g. wss://tunnel.example.com or ws://192.168.1.x). */
export function getWsBase(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'

  const stored = sessionStorage.getItem('ww_backend_url')
  if (stored) return stored.replace(/^https?:\/\//, `${proto}//`)

  const env = import.meta.env.VITE_BACKEND_URL
  if (env) return env.replace(/^https?:\/\//, `${proto}//`)

  // LAN fallback — matches original behaviour
  return `${proto}//${window.location.host}`
}

/**
 * Call once at app boot (before any React rendering).
 *
 * If the URL contains ?b=<encodedBackendUrl> (embedded by the display QR code),
 * persists it to sessionStorage so all subsequent API and WS calls use it.
 * Keeps ?b= in the address bar so copy-pasted share links remain self-contained.
 */
export function extractAndStoreBackendUrl(): void {
  const params = new URLSearchParams(window.location.search)
  const b = params.get('b')
  if (!b) return
  try {
    const decoded = decodeURIComponent(b)
    sessionStorage.setItem('ww_backend_url', decoded)
  } catch {
    // Malformed ?b= param — ignore; LAN/env fallback still applies
  }
}
