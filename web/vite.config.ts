import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Static build served by Caddy (infra/web.Dockerfile); `npm run dev` proxies /api to the stack.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.')
  return {
    plugins: [react()],
    server: {
      proxy: env.VITE_DEV_API_PROXY ? { '/api': env.VITE_DEV_API_PROXY } : undefined,
    },
    build: {
      // maplibre-gl alone is ~1 MB minified; keep it in its own long-cached chunk.
      chunkSizeWarningLimit: 1200,
      rolldownOptions: {
        output: {
          codeSplitting: { groups: [{ name: 'maplibre', test: /node_modules[\\/]maplibre-gl/ }] },
        },
      },
    },
  }
})
