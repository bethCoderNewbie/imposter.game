import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vercel sets VERCEL=1 at build time — serve from root.
// Docker build (nginx alias strips /display/ prefix) uses /display/.
// Dev mode always uses /.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: process.env.VERCEL ? '/' : command === 'build' ? '/display/' : '/',
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
