import { defineConfig, devices } from '@playwright/test'

// Browser smoke test (tests/smoke.spec.ts). Default: the production build (`vite preview`) with
// the API replayed from tests/fixtures/ and no basemap (no network; CI). E2E_LIVE=1: the running
// local stack at E2E_BASE_URL (default http://localhost:8080, `make up`) with the current run.
const live = Boolean(process.env.E2E_LIVE)
const previewUrl = 'http://127.0.0.1:4173'

export default defineConfig({
  testDir: 'tests',
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: live ? (process.env.E2E_BASE_URL ?? 'http://localhost:8080') : previewUrl,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: live
    ? undefined
    : {
        // CI builds in its own step before the test
        command: `${process.env.CI ? '' : 'npm run build && '}npx vite preview --port 4173 --strictPort --host 127.0.0.1`,
        url: previewUrl,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
})
