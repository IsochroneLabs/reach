// Unit tests for rank and comparison (`npm run test:unit`).
import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { CellFits } from '../api/types.ts'
import { compareTwo, type PlaceFacts } from './compare.ts'
import { betterNearby, cityRank } from './rank.ts'

const cells: CellFits = {
  CRS3035RES100mN2823300E4251200: [50, 300, 1],
  CRS3035RES100mN2823400E4251200: [60, 280, 1],
  CRS3035RES100mN2823500E4251200: [70, 260, 1],
  CRS3035RES100mN2823600E4251200: [90, 200, 0], // address cell: not ranked
  CRS3035RES100mN2833600E4251200: [99, 100, 1], // 10 km away
  CRS3035RES100mN2823700E4251200: [null, null, 1], // no fit
}

test('rank counts populated cells with a lower fit, rounded down', () => {
  assert.equal(cityRank(cells, 70), 50) // 50, 60 below of 4 ranked (50, 60, 70, 99)
  assert.equal(cityRank(cells, 100), 100)
  assert.equal(cityRank(cells, 0), 0)
  assert.equal(cityRank(cells, null), null)
  assert.equal(cityRank({}, 50), null)
})

test('better places nearby stay within the radius and exclude the place', () => {
  const near = betterNearby(cells, 'CRS3035RES100mN2823300E4251200', 50, 1500)
  assert.deepEqual(near.sort(), [
    'CRS3035RES100mN2823400E4251200',
    'CRS3035RES100mN2823500E4251200',
    'CRS3035RES100mN2823600E4251200',
  ])
})

const a: PlaceFacts = { id: 'A', name: 'A', fit: 71, weeklyMin: 335, rentEur: 370, minutes: { Campus: 18, Climbing: 30 } }
const b: PlaceFacts = { id: 'B', name: 'B', fit: 82, weeklyMin: 310, rentEur: 450, minutes: { Campus: 12, Climbing: 12 } }

test('comparison: fit, rent against weekly time, largest gaps', () => {
  const facts = compareTwo(a, b, 3)
  assert.deepEqual(facts[0], { kind: 'fitBetter', a: 'B', b: 'A', fa: 82, fb: 71 })
  assert.deepEqual(facts[1], { kind: 'rentVsTime', a: 'B', eur: 80, min: 25 })
  assert.deepEqual(facts[2], { kind: 'destDiff', a: 'B', dest: 'Climbing', min: 18 })
  assert.deepEqual(facts[3], { kind: 'destDiff', a: 'B', dest: 'Campus', min: 6 })
})

test('comparison without rents and with nearly equal fits', () => {
  const facts = compareTwo({ ...a, fit: 80, rentEur: null }, { ...b, fit: 81 }, 3)
  assert.equal(facts[0].kind, 'fitEqual')
  assert.deepEqual(facts[1], { kind: 'timeOnly', a: 'B', min: 25 })
})
