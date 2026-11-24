import { expect, test, type Page } from '@playwright/test'

// Check for one place (S2.5) on sample data.

test.beforeEach(async ({ page }) => {
  if (!process.env.BASE_URL) {
    await page.route('**/api/health', (route) =>
      route.fulfill({ json: { status: 'ok', version: '0.0.0', build_sha: 'fixture' } }),
    )
  }
})

async function search(page: Page, q: string, pick: string) {
  const toggle = page.getByRole('button', { name: 'Search an address' })
  if (await toggle.isVisible()) await toggle.click()
  await page.getByRole('combobox', { name: 'Address search' }).fill(q)
  await page.getByRole('option', { name: pick }).click()
}

async function showResults(page: Page) {
  const tab = page.getByRole('tab', { name: 'Results' })
  if (await tab.isVisible()) await tab.click()
}

test('search suggests addresses after 3 characters and says when nothing is found', async ({ page }) => {
  await page.goto('/')
  const toggle = page.getByRole('button', { name: 'Search an address' })
  if (await toggle.isVisible()) await toggle.click()
  const box = page.getByRole('combobox', { name: 'Address search' })
  await box.fill('he')
  await expect(page.getByText('Type at least 3 characters')).toBeVisible()
  await box.fill('hechinger')
  await expect(page.getByRole('option', { name: 'Hechinger Straße 12, Tübingen' })).toBeVisible()
  await box.fill('Nirgendwostraße')
  await expect(page.locator('.search-status')).toHaveText(/No address found in Tübingen/)
})

test('an address opens Check with fit, rank, weekly time, trips and data date', async ({ page }) => {
  await page.goto('/')
  await search(page, 'hechinger', 'Hechinger Straße 12, Tübingen')
  await expect(page).toHaveURL(/\/check#.*&pl=/)
  await showResults(page)
  const card = page.getByTestId('place')
  await expect(card).toContainText('Hechinger Straße 12, Tübingen')
  await expect(card.getByTestId('rank')).toContainText(/Better than \d+ % of places in Tübingen|Among the best 5 %/)
  await expect(card.getByTestId('weekly')).toContainText('per week on the way')
  await expect(card.getByTestId('trip-row').first()).toContainText(/Tue, arrive by 8:10/)
  await expect(card.getByTestId('data-note')).toContainText('Sample data')
})

test('rent stays in the browser: not in the link unless asked', async ({ page }) => {
  await page.goto('/')
  await search(page, 'wilhelm', 'Wilhelmstraße 30, Tübingen')
  await showResults(page)
  await page.getByLabel('Rent per month (optional)').fill('450')
  await expect(page).not.toHaveURL(/&r=/)
  await page.reload()
  await showResults(page)
  await expect(page.getByLabel('Rent per month (optional)')).toHaveValue('450')
})

test('a place outside the sample cells says there is no data', async ({ page }) => {
  await page.goto('/check#v=1&p=m:wbt;d:campus_site.3&pl=9.00000,48.48000,')
  await showResults(page)
  await expect(page.getByText('No data for this place — we only cover the city of Tübingen.')).toBeVisible()
})

test('"Better places nearby" switches to Find and outlines better cells', async ({ page }) => {
  await page.goto('/')
  await search(page, 'derendinger', 'Derendinger Straße 60, Tübingen')
  await showResults(page)
  await page.getByRole('button', { name: /Better places nearby/ }).click()
  await expect(page.getByRole('button', { name: 'Find', pressed: true })).toBeVisible()
  await showResults(page)
  await expect(page.getByTestId('nearby-note')).toContainText(/fit you better than Derendinger Straße 60/)
})

test('tapping the map in Check drops a pin', async ({ page, isMobile }) => {
  test.skip(isMobile, 'the bottom sheet covers part of the map; covered on desktop')
  await page.goto('/check')
  await expect(page.locator('.maplibregl-canvas')).toBeVisible()
  await expect(page.getByText('Loading the map…')).toHaveCount(0)
  const box = (await page.locator('.maplibregl-canvas').boundingBox())!
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
  await expect(page.getByTestId('place')).toHaveCount(1)
  await expect(page.getByTestId('place')).toContainText('Dropped pin')
})
