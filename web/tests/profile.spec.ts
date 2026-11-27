import { expect, test, type Page } from '@playwright/test'

// Profile panel (S2.3) on sample data. On phones the panel is the "Profile" tab of the sheet.

test.beforeEach(async ({ page }) => {
  if (!process.env.BASE_URL) {
    await page.route('**/api/health', (route) =>
      route.fulfill({ json: { status: 'ok', version: '0.0.0', build_sha: 'fixture' } }),
    )
  }
  await page.goto('/')
})

async function openProfile(page: Page) {
  const tab = page.getByRole('tab', { name: 'Profile' })
  if (await tab.isVisible()) await tab.click()
  await expect(page.getByTestId('profile-panel')).toBeVisible()
}

test('opens with the default profile and the programme hint', async ({ page }) => {
  await openProfile(page)
  await expect(page.getByTestId('programme-hint-panel')).toBeVisible()
  await expect(page.getByText('Campus: mix of Tal and Morgenstelle (no programme chosen)')).toBeVisible()
  for (const t of ['campus_site', 'mensa', 'grocery', 'main_station']) {
    await expect(page.getByTestId(`dest-${t}`)).toBeVisible()
  }
})

test('choosing a programme removes the hint and keeps it in the link', async ({ page }) => {
  await openProfile(page)
  await page.getByLabel('Programme').selectOption('biology')
  await expect(page.getByTestId('programme-hint-panel')).toHaveCount(0)
  await expect(page).toHaveURL(/#v=1&p=prog:biology;/)
  await page.reload()
  await openProfile(page)
  await expect(page.getByLabel('Programme')).toHaveValue('biology')
})

test('an example profile replaces the profile and can be undone', async ({ page }) => {
  await openProfile(page)
  await page.getByText('Example profiles').click()
  await page.getByRole('button', { name: 'Lena, first semester biology' }).click()
  await expect(page.getByTestId('dest-sport:climbing')).toBeVisible()
  await page.getByRole('button', { name: 'Undo' }).click()
  await expect(page.getByTestId('dest-sport:climbing')).toHaveCount(0)
})

test('the last mode cannot be switched off', async ({ page }) => {
  await openProfile(page)
  await page.getByRole('button', { name: 'Bike', exact: true }).click()
  await page.getByRole('button', { name: 'Bus', exact: true }).click()
  const walk = page.getByRole('button', { name: 'Walk', exact: true })
  await expect(walk).toHaveAttribute('aria-disabled', 'true')
  await walk.click({ force: true })
  await expect(walk).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('Choose at least one way of getting around')).toBeVisible()
})

test('all destinations "not important" asks for one', async ({ page }) => {
  await openProfile(page)
  for (const name of ['Campus', 'Mensa', 'Supermarket', 'Main station']) {
    await page.getByRole('radiogroup', { name: `How important is ${name}?` }).getByTitle('Not important').click()
  }
  const tab = page.getByRole('tab', { name: 'Results' })
  if (await tab.isVisible()) await tab.click()
  await expect(page.getByText('Mark at least one destination as important to see where you fit')).toBeVisible()
})

test('favourite supermarkets and a sport category: reasons, map and link', async ({ page }) => {
  await openProfile(page)
  // only the supermarket and tennis count
  for (const name of ['Campus', 'Mensa', 'Main station']) {
    await page.getByRole('radiogroup', { name: `How important is ${name}?` }).getByTitle('Not important').click()
  }
  await page.getByRole('button', { name: 'Details for Supermarket' }).click()
  const favourites = page.getByTestId('favourite-supermarkets')
  await favourites.getByRole('button', { name: 'Lidl', exact: true }).click()
  await expect(favourites.getByRole('button', { name: 'Lidl', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('dest-grocery').getByText('Lidl', { exact: true }).first()).toBeVisible()

  await page.getByLabel('Add destination').selectOption('sport:tennis')
  const tennis = page.getByTestId('dest-sport:tennis')
  await expect(tennis).toBeVisible()
  await page.getByRole('button', { name: 'Details for Tennis' }).click()
  await expect(tennis.getByText('Trips per week')).toHaveCount(0)
  await expect(page).toHaveURL(/d:[^;&]*sport:tennis\.2[^;&]*;g:lidl/)

  const tab = page.getByRole('tab', { name: 'Results' })
  if (await tab.isVisible()) await tab.click()
  const first = page.getByTestId('area').first()
  await expect(first.getByText(/Lidl/)).toBeVisible()
  await expect(first.getByText(/Tennis club/)).toBeVisible()
  await expect(page.locator('.poi', { hasText: 'Lidl Südstadt' })).toHaveCount(1)

  await page.reload()
  await openProfile(page)
  await expect(page.getByTestId('dest-sport:tennis')).toBeVisible()
  await expect(page.getByTestId('dest-grocery').getByText('Lidl', { exact: true }).first()).toBeVisible()
})
