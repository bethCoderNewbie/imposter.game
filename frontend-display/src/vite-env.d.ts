/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_HOST_IP?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
