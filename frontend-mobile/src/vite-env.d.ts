/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public HTTPS URL of the backend tunnel (e.g. https://my-tunnel.trycloudflare.com).
   *  Leave unset for pure LAN mode — all API/WS calls will use relative paths. */
  readonly VITE_BACKEND_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
