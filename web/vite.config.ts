import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Build-time config (web/AGENTS.md): VITE_BUILD_SHA is set by CI to the commit SHA,
// VITE_API_BASE to the public API URL once the backend is deployed (S1.5).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  process.env.VITE_BUILD_SHA = env.VITE_BUILD_SHA || 'dev' // also fills %VITE_BUILD_SHA% in index.html
  const apiPort = env.API_PORT || '8000'
  return {
    plugins: [react()],
    server: {
      // `npm run dev`: /api goes to the local API from `make up` (compose.yaml)
      proxy: { '/api': `http://127.0.0.1:${apiPort}` },
    },
  }
})
