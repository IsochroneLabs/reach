import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

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
  [/\/api\/catchment$/, 'catchment_candidate.json'],
  [/\/api\/isochrone$/, 'isochrone_reverse_walking_339.json'],
  [/\/api\/route$/, 'route_walking_339.json'],
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

  // green cell: the reachable facilities as pins, no route
  if (!live) {
    await expect(page.getByTestId('map')).toHaveAttribute('data-poi-pins', String(await grocery.locator('.reach-list li').count()))
    await expect(page.getByTestId('map')).toHaveAttribute('data-route', 'none')
  }

  await page.getByRole('link', { name: 'Data & validation' }).click()
  await expect(page.getByTestId('data-page')).toContainText('Known limitations')

  expect(errors).toEqual([])
})

test('lists recommended sites and shows the catchment of one', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(e.message))
  if (!live) await mockNetwork(page)

  await page.goto('/#/map?profile=walking_339&category=grocery')
  await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
  const panel = page.getByRole('region', { name: 'Recommended sites' })
  const items = panel.locator('.rec-list > li')
  await expect(items).toHaveCount(5)
  await expect(items.first()).toContainText('residents gain access')
  await expect(panel).toContainText('Accessibility only')

  // a click on the rank-1 marker on the map selects it and loads its catchment
  const first = (await page.evaluate(() =>
    fetch('/api/recommendations?category=grocery&profile=walking_339').then((r) => r.json()),
  )) as { features: { properties: { point: [number, number]; district_name: string } }[] }
  const { x, y } = await initialPixel(page, first.features[0].properties.point)
  await page.mouse.click(x, y)
  await expect(items.first()).toHaveClass(/selected/)
  await expect(panel.locator('.rec-detail')).toContainText('residents in')
  await expect(panel.locator('.rec-detail')).toContainText('None within 15 min')
  if (!live) {
    await expect(items.first()).toContainText('Lustnau-Zentrum')
    await expect(panel.locator('.rec-detail')).toContainText('6,722 residents in 110 cells')
  }
  // no inspector pin was dropped by the marker click
  await expect(page.getByTestId('inspect-result')).toHaveCount(0)
  await panel.getByRole('button', { name: 'Clear' }).click()
  await expect(panel.locator('.rec-detail')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('map settings switch layers, filter cells and survive a reload', async ({ page }) => {
  test.skip(live, 'checks fixture counts')
  const errors: string[] = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(e.message))
  await mockNetwork(page)

  await page.goto('/#/map?profile=walking_339&category=grocery')
  await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
  await expect(page.getByTestId('cells-shown')).toHaveCount(0)
  await expect(page.locator('.legend')).toContainText('None within 15 min')
  await expect(page.locator('.legend')).toContainText('Enough')

  const gear = page.getByRole('button', { name: 'Map settings' })
  await gear.click()
  await expect(gear).toHaveAttribute('aria-expanded', 'true')
  const panel = page.getByRole('dialog', { name: 'Map settings' })
  const map = page.getByTestId('map')
  await expect(map).toHaveAttribute('data-cell-fill', '0.8')
  await panel.getByLabel('Show cells').uncheck()
  await expect(map).toHaveAttribute('data-cell-fill', '0')
  await panel.getByLabel(/Minimum residents per cell/).fill('10')
  await expect(page.getByTestId('cells-shown')).toContainText(/^[\d,]+ of [\d,]+ cells shown$/)
  const [shown, all] = (await page.getByTestId('cells-shown').innerText()).match(/[\d,]+/g)!.map((n) => Number(n.replaceAll(',', '')))
  expect(shown).toBeLessThan(all)
  await expect(panel.getByLabel('Forward')).toBeChecked()
  await page.keyboard.press('Escape')
  await expect(panel).toHaveCount(0)
  await expect(gear).toBeFocused()

  // collapsed cards and settings are remembered
  await page.getByRole('button', { name: 'District' }).click()
  await page.reload()
  await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
  await expect(page.getByTestId('cells-shown')).toContainText(`${shown.toLocaleString('en')} of`)
  await expect(page.getByRole('button', { name: 'District' })).toHaveAttribute('aria-expanded', 'false')
  await gear.click()
  await expect(page.getByLabel('Show cells')).not.toBeChecked()
  await page.getByRole('button', { name: 'Reset to defaults' }).click()
  await expect(page.getByLabel('Show cells')).toBeChecked()
  await expect(page.getByTestId('cells-shown')).toHaveCount(0)
  await page.keyboard.press('Escape')

  // pin mode: measured from the cell centre; the colour switch in the inspector is the setting
  const { x, y } = await initialPixel(page, POINT)
  await page.mouse.click(x, y)
  const result = page.getByTestId('inspect-result')
  await expect(result).toContainText('Measured from the centre of this 100 m cell')
  const colours = page.getByRole('region', { name: 'Inspector' }).getByLabel('Show cell colours')
  await expect(colours).not.toBeChecked()
  await expect(map).toHaveAttribute('data-cell-fill', '0') // pin mode hides the colours
  await colours.check()
  await expect(map).toHaveAttribute('data-cell-fill', '0.8')
  await gear.click()
  await expect(page.getByRole('dialog', { name: 'Map settings' }).getByLabel('Show cell colours')).toBeChecked()
  // the rings of the isochrone can be switched one by one
  await expect(page.getByRole('dialog', { name: 'Map settings' }).getByLabel('15 min')).toBeChecked()
  await page.keyboard.press('Escape')
  // closing the pin brings the colours back
  await colours.uncheck()
  await expect(map).toHaveAttribute('data-cell-fill', '0')
  await page.getByRole('button', { name: 'Close inspector' }).click()
  await expect(map).toHaveAttribute('data-cell-fill', '0.8')
  expect(errors).toEqual([])
})

test('shows the reverse isochrone when chosen in the settings', async ({ page }) => {
  test.skip(live, 'checks the recorded request')
  const errors: string[] = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(e.message))
  await mockNetwork(page)
  const requests: unknown[] = []
  page.on('request', (r) => r.url().endsWith('/api/isochrone') && requests.push(r.postDataJSON()))

  await page.goto('/#/map?profile=walking_339&category=grocery')
  await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
  const { x, y } = await initialPixel(page, POINT)
  await page.mouse.click(x, y)
  const legend = page.getByTestId('isochrone-legend')
  await expect(legend).toContainText('Forward (dashed)')
  await expect(legend).not.toContainText('Reverse')
  expect(requests).toEqual([]) // forward only: no extra request

  await page.getByRole('button', { name: 'Map settings' }).click()
  await page.getByRole('dialog', { name: 'Map settings' }).getByLabel('Both').check()
  await expect(legend).toContainText('Reverse (dotted): from where people reach this point')
  await expect.poll(() => requests.length).toBe(1)
  expect(requests[0]).toMatchObject({ profile: 'walking_339', direction: 'reverse' })
  await page.getByRole('dialog', { name: 'Map settings' }).getByLabel('Reverse').check()
  await expect(legend).not.toContainText('Forward')
  expect(errors).toEqual([])
})

test('says so when the reverse isochrone fails', async ({ page }) => {
  test.skip(live, 'the error answer is mocked')
  await mockNetwork(page)
  // registered after mockNetwork, so it wins for /api/isochrone
  await page.route('**/api/isochrone', (route) =>
    route.fulfill({ status: 502, contentType: 'application/json', body: '{"detail":"valhalla down"}' }),
  )
  await page.goto('/#/map?profile=walking_339&category=grocery')
  await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
  await page.getByRole('button', { name: 'Map settings' }).click()
  await page.getByRole('dialog', { name: 'Map settings' }).getByLabel('Both').check()
  await page.keyboard.press('Escape')
  const { x, y } = await initialPixel(page, POINT)
  await page.mouse.click(x, y)
  const legend = page.getByTestId('isochrone-legend')
  await expect(legend).toContainText('Forward (dashed)')
  await expect(legend).toContainText('Reverse isochrone unavailable: The routing engine did not answer')
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

test('names the status of a cell without published values', async ({ page }) => {
  test.skip(live, 'cell statuses are mocked')
  await mockNetwork(page)
  const recorded = JSON.parse(readFileSync(fixture('inspect_walking_339.json'), 'utf8'))
  let status = 'unpopulated'
  // registered after mockNetwork, so it wins for /api/inspect: the recorded answer as a live one
  await page.route('**/api/inspect', (route) => {
    const cell = { ...recorded.cell, scored: false, status, population: null, district_id: null }
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ ...recorded, cell, source: 'live', precomputed: null, weakest_category: null }),
    })
  })

  const line = page.getByTestId('cell-status')
  for (const [next, text] of [
    ['unpopulated', 'No residents in the Zensus 2022 grid — values computed live'],
    ['outside_city', 'Outside the city boundary — not scored'],
  ]) {
    status = next
    // a fresh view each time, so the click never lands on a marker after the zoom to the pin
    await page.goto('/#/map?profile=walking_339&category=grocery')
    await page.reload()
    await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
    const { x, y } = await initialPixel(page, POINT)
    await page.mouse.click(x, y)
    await expect(line).toHaveText(text)
    await expect(page.getByTestId('inspect-result')).toContainText('live result')
  }
})

/** Click the cell of the recorded answer `file` (served for /api/inspect) and wait for it. */
async function inspectAnswer(page: Page, file: string) {
  await page.route('**/api/inspect', (route) => route.fulfill({ contentType: 'application/json', path: fixture(file) }))
  await page.goto('/#/map?profile=walking_339&category=grocery')
  await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
  const { x, y } = await initialPixel(page, POINT)
  await page.mouse.click(x, y)
  await expect(page.getByTestId('inspect-result')).toBeVisible()
}

test('a cell without a facility gets a dashed route beyond the budget', async ({ page }) => {
  test.skip(live, 'uses a recorded answer')
  await mockNetwork(page)
  await inspectAnswer(page, 'inspect_walking_339_lack.json')
  const map = page.getByTestId('map')
  // nothing reachable: only the next missing facility, marked, with its route
  await expect(map).toHaveAttribute('data-poi-pins', '1')
  await expect(map).toHaveAttribute('data-route', 'beyond')
  const next = page.getByTestId('next-grocery')
  await expect(next).toContainText('Nearest')
  await expect(next).toContainText('Aldi Süd')
  await expect(next).toContainText('40 min · beyond 15 min')
  // other categories keep their own answer: school has none within the budget either
  await expect(page.getByTestId('next-school')).toContainText('beyond 15 min')
  // the settings switch hides pins and routes
  await page.getByRole('button', { name: 'Map settings' }).click()
  await page.getByRole('dialog', { name: 'Map settings' }).getByLabel('Facility pins and routes').uncheck()
  await expect(map).toHaveAttribute('data-poi-pins', '0')
  await expect(map).toHaveAttribute('data-route', 'none')
})

test('an insufficient cell shows its pin and the route to the next facility', async ({ page }) => {
  test.skip(live, 'uses a recorded answer')
  await mockNetwork(page)
  await inspectAnswer(page, 'inspect_walking_339_insufficient.json')
  const map = page.getByTestId('map')
  await expect(map).toHaveAttribute('data-poi-pins', '2') // the reachable one and the next missing
  await expect(map).toHaveAttribute('data-route', 'beyond')
  await expect(page.getByTestId('next-grocery')).toContainText('Next missing')
})

test('a facility in the list shows its route; a second click clears it', async ({ page }) => {
  test.skip(live, 'checks the recorded request')
  const errors: string[] = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(e.message))
  await mockNetwork(page)
  const requests: unknown[] = []
  page.on('request', (r) => r.url().endsWith('/api/route') && requests.push(r.postDataJSON()))
  const recorded = JSON.parse(readFileSync(fixture('inspect_walking_339.json'), 'utf8'))
  const first = recorded.categories.find((c: { category: string }) => c.category === 'grocery').reachable[0]

  await page.goto('/#/map?profile=walking_339&category=grocery')
  await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
  const { x, y } = await initialPixel(page, POINT)
  await page.mouse.click(x, y)
  const map = page.getByTestId('map')
  await page.getByTestId('inspect-result').locator('li.selected .cat-count').click()
  const entry = page.getByTestId('inspect-result').locator('li.selected .reach-list li').first()
  const button = entry.getByRole('button')
  await expect(button).toHaveAttribute('aria-pressed', 'false')
  expect(requests).toEqual([]) // no route request before a pick

  // hover highlights the pin
  await button.hover()
  await expect(map).toHaveAttribute('data-highlighted', first.facility_id)
  await page.mouse.move(0, 0)
  await expect(map).toHaveAttribute('data-highlighted', '')

  await button.click()
  await expect(button).toHaveAttribute('aria-pressed', 'true')
  await expect(map).toHaveAttribute('data-route', 'within')
  await expect(page.getByTestId('facility-route')).toContainText('Route to')
  expect(requests).toEqual([expect.objectContaining({ profile: 'walking_339', facility_id: first.facility_id })])
  await expect(map).toHaveAttribute('data-highlighted', first.facility_id)

  await button.click()
  await expect(button).toHaveAttribute('aria-pressed', 'false')
  await expect(map).toHaveAttribute('data-route', 'none')
  await expect(page.getByTestId('facility-route')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('says so when the route to a picked facility fails', async ({ page }) => {
  test.skip(live, 'the error answer is mocked')
  await mockNetwork(page)
  await page.route('**/api/route', (route) =>
    route.fulfill({ status: 502, contentType: 'application/json', body: '{"detail":"valhalla down"}' }),
  )
  await page.goto('/#/map?profile=walking_339&category=grocery')
  await expect(page.getByTestId('map')).toHaveAttribute('data-ready', 'true', { timeout: 30_000 })
  const { x, y } = await initialPixel(page, POINT)
  await page.mouse.click(x, y)
  await page.getByTestId('inspect-result').locator('li.selected .cat-count').click()
  await page.getByTestId('inspect-result').locator('li.selected .reach-list li').first().getByRole('button').click()
  await expect(page.getByTestId('facility-route')).toContainText('The routing engine did not answer')
  await expect(page.getByTestId('map')).toHaveAttribute('data-route', 'none')
})
