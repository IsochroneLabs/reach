import { expect, test, type Page } from '@playwright/test'

const live = Boolean(process.env.E2E_LIVE)
// Scored, well-served cell in the old town (Metzgergasse); the inspect fixture was recorded here.
const POINT: [number, number] = [9.0561, 48.5215]

// relative to web/, where `npx playwright test` runs
const fixture = (name: string) => `tests/fixtures/${name}`

const API: [RegExp, string][] = [
  [/\/api\/meta$/, 'meta.json'],
  [/\/api\/districts$/, 'districts.json'],
  [/\/api\/districts\/[^/]+\/scores/, 'district_scores.json'],
  [/\/api\/cells/, 'cells_grocery_walking_339.json'],
  [/\/api\/recommendations/, 'recommendations.json'],
  [/\/api\/inspect$/, 'inspect_walking_339.json'],
]

const BLANK_STYLE = JSON.stringify({
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#f2f1ed' } }],
})

async function mockNetwork(page: Page) {
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    const hit = API.find(([re]) => re.test(path))
    return hit
      ? route.fulfill({ contentType: 'application/json', path: fixture(hit[1]) })
      : route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not mocked"}' })
  })
  // no basemap in CI: a blank style instead of OpenFreeMap, every other external request fails
  await page.route(/^https?:\/\/(?!127\.0\.0\.1|localhost)/, (route) =>
    route.request().url().includes('/styles/')
      ? route.fulfill({ contentType: 'application/json', body: BLANK_STYLE })
      : route.abort(),
  )
}

/** Pixel of a lon/lat in the initial view: the map fits the districts' bbox (padding 20). */
async function initialPixel(page: Page, [lon, lat]: [number, number]) {
  // fetched in the page, so the mocked routes apply
  const districts = (await page.evaluate(() => fetch('/api/districts').then((r) => r.json()))) as {
    features: { geometry: { coordinates: unknown } }[]
  }
  const xs: number[] = []
  const ys: number[] = []
  const visit = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === 'number') {
      xs.push(c[0] as number)
      ys.push(c[1] as number)
    } else if (Array.isArray(c)) c.forEach(visit)
  }
  districts.features.forEach((f) => visit(f.geometry.coordinates))
  const mx = (x: number) => (x + 180) / 360
  const my = (y: number) => (1 - Math.log(Math.tan(Math.PI / 4 + (y * Math.PI) / 360)) / Math.PI) / 2
  const box = (await page.getByTestId('map').boundingBox())!
  const [x0, x1, y0, y1] = [mx(Math.min(...xs)), mx(Math.max(...xs)), my(Math.max(...ys)), my(Math.min(...ys))]
  const scale = Math.min((box.width - 40) / (x1 - x0), (box.height - 40) / (y1 - y0))
  return {
    x: box.x + box.width / 2 + (mx(lon) - (x0 + x1) / 2) * scale,
    y: box.y + box.height / 2 + (my(lat) - (y0 + y1) / 2) * scale,
  }
}

test('loads the class map and inspects a location', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(e.message))
  if (!live) {
    await mockNetwork(page)
  }

  await page.goto('/#/map?profile=walking_339&category=grocery')
  await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
  await expect(page.getByTestId('cells-summary')).toContainText('scored 100 m cells')
  await expect(page.locator('.maplibregl-ctrl-attrib')).toContainText('OpenStreetMap contributors')
  for (const credit of ['Destatis', 'NVBW', 'OpenMapTiles'])
    await expect(page.locator('.maplibregl-ctrl-attrib')).toContainText(credit)

  const { x, y } = await initialPixel(page, POINT)
  await page.mouse.click(x, y)
  const result = page.getByTestId('inspect-result')
  await expect(result).toBeVisible({ timeout: 30_000 })
  await expect(result).toContainText('residents in this 100 m cell')
  await expect(result).toContainText('Grocery')
  // travel time first, length secondary: per facility and for the route to the nearest one
  await result.locator('li.selected .cat-count').click()
  const grocery = result.locator('li.selected details')
  await expect(grocery).toHaveAttribute('open', '')
  if (!live) {
    await expect(grocery.locator('.reach-list li').first()).toContainText('1.0 min')
    const route = result.getByTestId('route-grocery')
    await expect(route.locator('strong')).toHaveText('1.0 min')
    await expect(route).toContainText('57 m')
    await expect(route.locator('.muted')).toContainText('57 m')
  } else {
    await expect(grocery.locator('.reach-list .reach-time').first()).toContainText('min')
  }

  await page.getByRole('link', { name: 'Data & validation' }).click()
  await expect(page.getByTestId('data-page')).toContainText('Known limitations')

  expect(errors).toEqual([])
})

test('labels slow answers and explains timeouts and rate limits', async ({ page }) => {
  test.skip(live, 'error answers are mocked')
  const errors: string[] = []
  // the browser itself logs the mocked 504/429 responses; anything else is an error of the app
  page.on('console', (m) => m.type() === 'error' && !m.text().startsWith('Failed to load resource') && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(e.message))
  await mockNetwork(page)
  const answers: { status: number; body: string; headers: Record<string, string> }[] = [
    { status: 504, body: '{"detail":"live matrix timed out"}', headers: {} },
    { status: 429, body: '{"detail":"rate limit exceeded"}', headers: { 'Retry-After': '7' } },
  ]
  // registered after mockNetwork, so it wins for /api/inspect
  await page.route('**/api/inspect', async (route) => {
    const next = answers.shift()!
    await new Promise((r) => setTimeout(r, 700)) // slower than the spinner delay
    await route.fulfill({ status: next.status, contentType: 'application/json', body: next.body, headers: next.headers })
  })

  await page.goto('/#/map?profile=walking_339&category=grocery')
  await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
  const map = (await page.getByTestId('map').boundingBox())!
  const centre = { x: map.x + map.width / 2, y: map.y + map.height / 2 }

  await page.mouse.click(centre.x, centre.y)
  await expect(page.getByRole('status')).toContainText('Calculating')
  await expect(page.getByRole('alert')).toContainText('took too long (timeout)')

  await page.mouse.click(centre.x + 10, centre.y)
  await expect(page.getByRole('alert')).toContainText('wait 7 seconds')
  expect(errors).toEqual([])
})
