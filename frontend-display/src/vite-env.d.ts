/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** LAN IP baked at Docker build time (e.g. http://192.168.1.100). Legacy/LAN mode. */
  readonly VITE_HOST_IP?: string
  /** Public HTTPS URL of the backend tunnel for the display's own API/WS calls.
   *  Set in Vercel project env vars when deploying display to Vercel.
   *  Never set via Docker build — use VITE_QR_BACKEND_URL for the QR embed instead. */
  readonly VITE_BACKEND_URL?: string
  /** Tunnel URL embedded in the QR code ?b= param (Docker build only).
   *  Baked from BACKEND_URL in .env via docker-compose QR_BACKEND_URL build arg.
   *  Keeps display API/WS calls on the LAN while still telling mobile players
   *  where the backend is. */
  readonly VITE_QR_BACKEND_URL?: string
  /** Vercel URL of the mobile frontend (e.g. https://my-game.vercel.app).
   *  When set, the QR code points here instead of the local IP. */
  readonly VITE_MOBILE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
