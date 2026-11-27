import { expect, test } from '@playwright/test'

// Both side columns fold away; the results column can be dragged wider (N30). Desktop only: phones
// use the bottom sheet.

test.beforeEach(async ({ page, isMobile }) => {
  test.skip(!!isMobile, 'phones have the bottom sheet, no side columns')
  if (!process.env.BASE_URL) {
    await page.route('**/api/health', (route) =>
      route.fulfill({ json: { status: 'ok', version: '0.0.0', build_sha: 'fixture' } }),
    )
  }
  await page.setViewportSize({ width: 1400, height: 900 })
  await page.goto('/')
})

test('the profile and the results fold away and come back', async ({ page }) => {
  await expect(page.getByTestId('profile-panel')).toBeVisible()
  await page.getByRole('button', { name: 'Hide profile' }).click()
  await expect(page.getByTestId('profile-panel')).toBeHidden()
  await page.getByRole('button', { name: 'Hide results' }).click()
  await expect(page.locator('#results')).toBeHidden()
  await page.reload()
  await expect(page.getByTestId('profile-panel')).toBeHidden() // remembered
  await page.getByRole('button', { name: 'Show profile' }).click()
  await page.getByRole('button', { name: 'Show results' }).click()
  await expect(page.getByTestId('profile-panel')).toBeVisible()
  await expect(page.locator('#results')).toBeVisible()
})

test('the results column can be made wider', async ({ page }) => {
  const results = page.locator('#results')
  const before = (await results.boundingBox())!.width
  const handle = page.getByRole('separator', { name: /resize the results/ })
  const box = (await handle.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + 200)
  await page.mouse.down()
  await page.mouse.move(box.x - 300, box.y + 200, { steps: 5 })
  await page.mouse.up()
  await expect.poll(async () => (await results.boundingBox())!.width).toBeGreaterThan(before + 250)
  await handle.focus()
  await page.keyboard.press('Home') // default width again
  await expect.poll(async () => Math.round((await results.boundingBox())!.width)).toBeLessThan(before + 5)
})
