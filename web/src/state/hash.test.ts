// Unit tests for the URL hash (`npm run test:unit`).
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { cellIdAt } from '../geo/laea.ts'
import { decodeHash, encodeHash } from './hash.ts'
import type { Place, StudentProfile } from './profile.ts'

const profile: StudentProfile = {
  programme: 'biology',
  modes: ['walk', 'transit'],
  destinations: {
    campus_site: { importance: 3, fine_time_min: 15 },
    'sport:climbing': { importance: 2, fine_time_min: 25 },
    mensa: { importance: 2 },
  },
  labels: { grocery: ['lidl', 'organic'] },
}
const places: Place[] = [
  { id: 'A', point: [9.0565, 48.5108], cellId: cellIdAt([9.0565, 48.5108]), label: 'Hechinger Straße 12, Tübingen', rentEur: 450 },
  { id: 'B', point: [9.03, 48.53], cellId: cellIdAt([9.03, 48.53]), label: null, rentEur: null },
]

test('profile and places survive a round trip', () => {
  const h = encodeHash(profile, places, false)
  assert.match(h, /^#v=1&p=prog:biology;m:wt;d:campus_site\.3\.15,sport:climbing\.2\.25,mensa\.2;g:lidl\.organic&pl=/)
  const back = decodeHash(h, cellIdAt)
  assert.equal(back.bad, false)
  assert.deepEqual(back.profile, profile)
  assert.equal(back.places?.length, 2)
  assert.equal(back.places?.[0].label, 'Hechinger Straße 12, Tübingen')
  assert.equal(back.places?.[0].rentEur, null, 'rents stay out of the link unless asked')
  assert.equal(back.places?.[1].label, null)
})

test('rents are in the link only when asked', () => {
  const back = decodeHash(encodeHash(profile, places, true), cellIdAt)
  assert.equal(back.places?.[0].rentEur, 450)
  assert.equal(back.places?.[1].rentEur, null)
})

test('broken parts are flagged and skipped, the rest is kept', () => {
  const back = decodeHash('#v=1&p=m:wq;d:mensa.9,grocery.2&pl=abc,def|9.05,48.52,', cellIdAt)
  assert.equal(back.bad, true)
  assert.deepEqual(back.profile?.modes, ['walk'])
  assert.deepEqual(back.profile?.destinations, { grocery: { importance: 2 } })
  assert.equal(back.places?.length, 1)
  assert.equal(back.places?.[0].id, 'A')
})

test('empty or foreign hashes', () => {
  assert.deepEqual(decodeHash('', cellIdAt), { profile: null, places: null, bad: false })
  assert.equal(decodeHash('#v=2&p=x', cellIdAt).bad, true)
})

test('favourite supermarkets: bad names are flagged, the rest is kept', () => {
  const back = decodeHash('#v=1&p=m:w;d:grocery.2;g:rewe.Bad%20x.lidl', cellIdAt)
  assert.equal(back.bad, true)
  assert.deepEqual(back.profile?.labels, { grocery: ['rewe', 'lidl'] })
})
