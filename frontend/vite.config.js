import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // Relative base so `npm run build` output can be opened straight from
  // disk (double-click dist/index.html) without a dev server.
  base: './',
  plugins: [react(), tailwindcss()],
})
