import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev mode base is '/' so http://localhost:5173/ works directly.
// In production build base is '/display/' so nginx can proxy /display/* to this service.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/display/' : '/',
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        rewriteWsOrigin: true,
      },
    },
  },
}))
