// Unit tests for the EPSG:3035 projection (`npm run test:unit`, node --test).
// Reference values computed with pyproj 3.8 (PROJ), 24 Nov 2026.
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { cellCentre, cellIdAt, cellRing, fromLaea, toLaea } from './laea.ts'

const REF: { lonLat: [number, number]; en: [number, number] }[] = [
  { lonLat: [9.056, 48.52], en: [4251239.140609921, 2823398.6803368283] },
  { lonLat: [9.035, 48.537], en: [4249711.520560862, 2825308.295445739] },
  { lonLat: [9.025, 48.495], en: [4248912.521916421, 2820649.7732071243] },
]

test('forward projection matches PROJ within 1 mm', () => {
  for (const { lonLat, en } of REF) {
    const [e, n] = toLaea(lonLat)
    assert.ok(Math.abs(e - en[0]) < 0.001, `easting ${e} vs ${en[0]}`)
    assert.ok(Math.abs(n - en[1]) < 0.001, `northing ${n} vs ${en[1]}`)
  }
})

test('inverse projection matches PROJ within 1e-7 degrees (≈ 1 cm)', () => {
  // pyproj: (4250500, 2822200) → (9.04620395, 48.50913176)
  const [lon, lat] = fromLaea([4250500, 2822200])
  assert.ok(Math.abs(lon - 9.04620395) < 1e-7, `lon ${lon}`)
  assert.ok(Math.abs(lat - 48.50913176) < 1e-7, `lat ${lat}`)
  for (const { lonLat, en } of REF) {
    const back = fromLaea(en)
    assert.ok(Math.abs(back[0] - lonLat[0]) < 1e-7)
    assert.ok(Math.abs(back[1] - lonLat[1]) < 1e-7)
  }
})

test('cell id of a point is the containing 100 m cell (lower-left corner)', () => {
  assert.equal(cellIdAt([9.056, 48.52]), 'CRS3035RES100mN2823300E4251200')
  const centre = cellCentre('CRS3035RES100mN2823300E4251200')
  assert.ok(centre)
  assert.equal(cellIdAt(centre), 'CRS3035RES100mN2823300E4251200')
})

test('cell ring is closed and malformed ids give null', () => {
  const ring = cellRing('CRS3035RES100mN2822200E4250500')
  assert.ok(ring)
  assert.equal(ring.length, 5)
  assert.deepEqual(ring[0], ring[4])
  assert.equal(cellRing('not-a-cell'), null)
})
