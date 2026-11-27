import { expect, test } from '@playwright/test'

// Find (S2.4) on sample data: map, legend, best areas with reasons, Find → Check.

test.beforeEach(async ({ page }) => {
  if (!process.env.BASE_URL) {
    await page.route('**/api/health', (route) =>
      route.fulfill({ json: { status: 'ok', version: '0.0.0', build_sha: 'fixture' } }),
    )
  }
  await page.goto('/')
})

test('three best areas with 2–4 reasons and the data date', async ({ page }) => {
  const areas = page.getByTestId('area')
  await expect(areas).toHaveCount(3)
  for (const a of await areas.all()) {
    const n = await a.locator('.reason').count()
    expect(n).toBeGreaterThanOrEqual(2)
    expect(n).toBeLessThanOrEqual(4)
  }
  await expect(page.getByTestId('data-note').first()).toContainText('Sample data')
})

test('the map draws and shows the legend', async ({ page }) => {
  await expect(page.locator('.maplibregl-canvas')).toBeVisible()
  // wait for the best WG to open (it hides the grid), then the toggle brings the legend back
  await expect(page.getByTestId('listing-detail')).toBeVisible()
  await page.getByRole('button', { name: 'Grid', exact: true }).click()
  await expect(page.getByText('Fit for you')).toBeVisible()
  await expect(page.getByText('Loading the map…')).toHaveCount(0)
})

test('"Check here" opens Check at the best place of the area', async ({ page }) => {
  const first = page.getByTestId('area').first()
  const name = (await first.locator('h3').innerText()).replace(/^\d+\.\s*/, '')
  await first.getByRole('button', { name: /Check the best place in/ }).click()
  await expect(page).toHaveURL(/\/check#/)
  await expect(page.getByRole('button', { name: 'Check', pressed: true })).toBeVisible()
  await expect(page.getByTestId('place').first()).toContainText(name)
})

test('a persona recolours the results', async ({ page }) => {
  const before = await page.getByTestId('area').first().innerText()
  const tab = page.getByRole('tab', { name: 'Profile' })
  if (await tab.isVisible()) await tab.click()
  await page.getByText('Example profiles').click()
  await page.getByRole('button', { name: 'Lena, first semester biology' }).click()
  const res = page.getByRole('tab', { name: 'Results' })
  if (await res.isVisible()) await res.click()
  await expect.poll(() => page.getByTestId('area').first().innerText()).not.toBe(before)
})
