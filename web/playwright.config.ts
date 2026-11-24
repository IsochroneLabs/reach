import { defineConfig, devices } from '@playwright/test'

const PORT = 4173

/**
 * Smoke tests against the production build (`vite preview`). The API is never called for real:
 * tests answer /api requests with fixtures (page.route). BASE_URL runs the same tests against a
 * deployed site (deploy.yml) instead of the local build.
 */
export default defineConfig({
  testDir: 'tests',
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.BASE_URL ?? `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: process.env.BASE_URL
    ? undefined
    : {
        command: `npm run build && npm run preview -- --host 127.0.0.1 --port ${PORT} --strictPort`,
        url: `http://127.0.0.1:${PORT}`,
        reuseExistingServer: !process.env.CI,
        env: { VITE_API_BASE: '/api', VITE_BUILD_SHA: 'playwright' },
      },
})
