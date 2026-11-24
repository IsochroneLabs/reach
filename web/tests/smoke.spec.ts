import { expect, test } from '@playwright/test'

// Against a deployed site (deploy.yml) EXPECTED_SHA is the deployed commit; locally the
// webServer in playwright.config.ts builds with VITE_BUILD_SHA=playwright.
const deployed = !!process.env.BASE_URL
const expectedSha = process.env.EXPECTED_SHA ?? 'playwright'

// The local build calls /api/health: answer it with a fixture, never a real API. Tests that need
// another answer register their own route, which takes precedence.
test.beforeEach(async ({ page }) => {
  if (!deployed) {
    await page.route('**/api/health', (route) =>
      route.fulfill({ json: { status: 'ok', version: '0.0.0', build_sha: 'fixture' } }),
    )
  }
})

test('placeholder shows the name and the build SHA', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'reach' })).toBeVisible()
  await expect(page.getByTestId('build-sha')).toHaveText(expectedSha)
  await expect(page.locator('meta[name="build-sha"]')).toHaveAttribute('content', expectedSha)
})

test('unknown paths fall back to the app', async ({ page }) => {
  const res = await page.goto('/some/deep/link')
  expect(res?.status()).toBe(200)
  await expect(page.getByRole('heading', { level: 1, name: 'reach' })).toBeVisible()
})

test.describe('API status (fixtures)', () => {
  test.skip(deployed, 'fixtures only apply to the local build with VITE_API_BASE=/api')

  test('healthy API', async ({ page }) => {
    await page.route('**/api/health', (route) =>
      route.fulfill({ json: { status: 'ok', version: '0.0.0', build_sha: 'abc1234' } }),
    )
    await page.goto('/')
    await expect(page.getByTestId('api-status')).toHaveText('ok (build abc1234)')
  })

  test('API down is shown, not hidden', async ({ page }) => {
    await page.route('**/api/health', (route) => route.fulfill({ status: 503 }))
    await page.goto('/')
    await expect(page.getByTestId('api-status')).toHaveText('unreachable (HTTP 503)')
  })
})
