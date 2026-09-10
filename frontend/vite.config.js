import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // Relative base so `npm run build` output works when served from any
  // path (e.g. mounted under server.py's StaticFiles).
  base: './',
  plugins: [react(), tailwindcss()],
  server: {
    // In dev (`npm run dev`), forward API calls to the FastAPI server so
    // the same relative `/api/...` fetch calls work in both dev and the
    // production build served by server.py -- no separate API base URL
    // or CORS juggling needed.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
