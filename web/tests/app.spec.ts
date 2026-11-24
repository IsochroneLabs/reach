import { expect, test } from '@playwright/test'

// The app itself. Locally the build runs in fixture mode (playwright.config.ts); against a
// deployed site without a backend the app also runs on sample data, so these tests run there too.

test.beforeEach(async ({ page }) => {
  if (!process.env.BASE_URL) {
    await page.route('**/api/health', (route) =>
      route.fulfill({ json: { status: 'ok', version: '0.0.0', build_sha: 'fixture' } }),
    )
  }
})

test('the app opens on Find with sample data and the best areas', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Find', pressed: true })).toBeVisible()
  await expect(page.getByTestId('sample-badge')).toHaveText('Sample data')
  await expect(page.getByTestId('area').first()).toBeVisible()
})

test('/check loads directly (SPA fallback) and opens Check', async ({ page }) => {
  const res = await page.goto('/check')
  expect(res?.status()).toBe(200)
  await expect(page.getByRole('button', { name: 'Check', pressed: true })).toBeVisible()
})

test('switching the language to German', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Switch the language to German' }).click()
  await expect(page.getByRole('button', { name: 'Finden', pressed: true })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('lang', 'de')
})
