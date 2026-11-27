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

test('the app opens on Find with the best WGs and the areas behind a summary', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Find', pressed: true })).toBeVisible()
  await expect(page.getByTestId('sample-badge')).toHaveText('Sample data')
  await expect(page.locator('.listing-card').first()).toBeVisible()
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

test('Find opens the best WG immediately and expands the others', async ({ page, isMobile }) => {
  // On phones the list sits in the bottom sheet, so this flow is desktop-only.
  test.skip(!!isMobile, 'bottom sheet peek hides the listing list')
  await page.goto('/')
  await expect(page.locator('.listing-card').first()).toBeVisible()
  await expect(page.getByTestId('listing-detail')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open the ad on WG-Gesucht' })).toHaveAttribute(
    'href',
    /wg-gesucht\.de/,
  )
  await page.locator('.listing-card').first().click()
  await expect(page.getByTestId('listing-detail')).toHaveCount(0)
  await page.locator('.listing-card').nth(1).click()
  await expect(page.getByTestId('listing-detail')).toBeVisible()
})

test('the grid toggle hides the fit cells but keeps the WGs', async ({ page, isMobile }) => {
  test.skip(!!isMobile, 'the bottom sheet peek hides the listing list')
  await page.goto('/')
  await expect(page.locator('.legend')).toBeVisible()
  await page.getByRole('button', { name: 'Grid', exact: true }).click()
  await expect(page.locator('.legend')).toHaveCount(0)
  await expect(page.locator('.listing-card').first()).toBeVisible()
})

test('the trips of a WG are labelled on the map; hover shows details, a click pins them', async ({
  page,
  isMobile,
}) => {
  test.skip(!!isMobile, 'bottom sheet covers the map; covered on desktop')
  await page.goto('/')
  await expect(page.getByTestId('listing-detail')).toBeVisible()
  const pois = page.locator('.poi-marker')
  await expect(pois.first()).toBeVisible()
  const grocery = pois.filter({ hasText: 'Supermarket' }).first()
  await grocery.hover()
  const card = page.locator('.poi-popup')
  await expect(card).toContainText('Opening hours (OSM): Mo-Sa 07:00-22:00')
  await expect(card).toContainText('Open at that time')
  await expect(card.getByRole('button', { name: 'Close' })).toHaveCount(0)
  await grocery.click()
  await page.mouse.move(5, 5)
  await expect(card).toBeVisible() // pinned
  await card.getByRole('button', { name: 'Close' }).click()
  await expect(card).toHaveCount(0)
})
