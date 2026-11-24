import { expect, test, type Page } from '@playwright/test'

// Check with two or three places (S2.6): comparison in plain language, shareable link.

const LINK =
  '/check#v=1&p=prog:biology;m:wt;d:campus_site.3,climbing.2..2,grocery.2,main_station.1,mensa.2' +
  '&pl=9.05650,48.51080,Hechinger%2520Stra%25C3%259Fe%252012|9.05750,48.53180,Mohlstra%25C3%259Fe%25208&r=370,450'

test.beforeEach(async ({ page }) => {
  if (!process.env.BASE_URL) {
    await page.route('**/api/health', (route) =>
      route.fulfill({ json: { status: 'ok', version: '0.0.0', build_sha: 'fixture' } }),
    )
  }
})

async function showResults(page: Page) {
  const tab = page.getByRole('tab', { name: 'Results' })
  if (await tab.isVisible()) await tab.click()
}

test('a shared link restores both places, the rents and the comparison', async ({ page }) => {
  await page.goto(LINK)
  await showResults(page)
  await expect(page.getByTestId('place')).toHaveCount(2)
  const short = page.getByTestId('in-short')
  await expect(short).toContainText('fits your profile better')
  await expect(short).toContainText(/costs €80 more per month but saves about .* per week/)
  await expect(page.getByLabel('Include rents in the link')).toBeChecked()
  await expect(page).toHaveURL(/&r=370,450/)
})

test('rents leave the link when unticked', async ({ page }) => {
  await page.goto(LINK)
  await showResults(page)
  await page.getByLabel('Include rents in the link').uncheck()
  await expect(page).not.toHaveURL(/&r=/)
  await expect(page.getByTestId('compare')).toContainText('€450')
})

test('a fourth place is refused with a message', async ({ page }) => {
  await page.goto(LINK.replace('&r=370,450', '|9.0628,48.5262,Wilhelmstr'))
  await showResults(page)
  await expect(page.getByTestId('place')).toHaveCount(3)
  const toggle = page.getByRole('button', { name: 'Search an address' })
  if (await toggle.isVisible()) await toggle.click()
  await page.getByRole('combobox', { name: 'Address search' }).fill('nürtinger')
  await page.getByRole('option', { name: 'Nürtinger Straße 20, Tübingen' }).click()
  await expect(page.getByText('You can compare up to 3 places. Remove one first.')).toBeVisible()
  await expect(page.getByTestId('place')).toHaveCount(3)
})

test('removing a place relabels the others', async ({ page }) => {
  await page.goto(LINK)
  await showResults(page)
  await page.getByRole('button', { name: 'Remove place A' }).click()
  await expect(page.getByTestId('place')).toHaveCount(1)
  await expect(page.getByTestId('place')).toContainText('Mohlstraße 8')
  await expect(page.getByRole('button', { name: 'Remove place A' })).toBeVisible()
})
