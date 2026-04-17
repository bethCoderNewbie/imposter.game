/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** LAN IP baked at Docker build time (e.g. http://192.168.1.100). Legacy/LAN mode. */
  readonly VITE_HOST_IP?: string
  /** Public HTTPS URL of the backend tunnel. When set, all API/WS calls use this URL
   *  and the QR code embeds it via ?b= so mobile clients can reach the backend. */
  readonly VITE_BACKEND_URL?: string
  /** Vercel URL of the mobile frontend (e.g. https://my-game.vercel.app).
   *  When set, the QR code points here instead of the local IP. */
  readonly VITE_MOBILE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
