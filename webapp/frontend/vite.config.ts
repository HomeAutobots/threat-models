import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// In dev, the back end (started with --dev) listens on 127.0.0.1:8765. changeOrigin makes it see
// Host: 127.0.0.1:8765; Origin: http://localhost:5199 is allowed only under its --dev flag.
const backend = 'http://127.0.0.1:8765'

export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist' },
  server: {
    port: 5199, // the port the back end's --dev flag expects
    strictPort: true,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/signin': { target: backend, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
  },
})
