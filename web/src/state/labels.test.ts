// Unit tests for destination labels in the profile (`npm run test:unit`).
import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { DestinationType } from '../api/types.ts'
import { choosableKeys, groceryLabels, resolveKey } from './labels.ts'
import { normalise, sanitize, type StudentProfile } from './profile.ts'

const types: DestinationType[] = [
  {
    destination_type: 'grocery', label: { en: 'Supermarket', de: 'Supermarkt' }, trip_window: 'evening', fine_time_min: 10, trips_per_week: 2,
    labels: [
      { label: 'lidl', kind: 'brand', name: { en: 'Lidl', de: 'Lidl' }, destinations: 2 },
      { label: 'organic', kind: 'group', name: { en: 'Organic', de: 'Bio' }, destinations: 1 },
      { label: 'norma', kind: 'brand', name: { en: 'Norma', de: 'Norma' }, destinations: 0 },
    ],
  },
  {
    destination_type: 'sport', label: { en: 'Sport', de: 'Sport' }, trip_window: 'evening', fine_time_min: 20, trips_per_week: 0,
    labels: [{ label: 'tennis', kind: 'category', name: { en: 'Tennis', de: 'Tennis' }, destinations: 2 }],
  },
]

test('keys resolve to types and categories; containers are never a key', () => {
  assert.equal(resolveKey('grocery', types)?.category, null)
  assert.equal(resolveKey('sport:tennis', types)?.name.en, 'Tennis')
  assert.equal(resolveKey('sport', types), null)
  assert.equal(resolveKey('sport:golf', types), null)
  assert.deepEqual(choosableKeys(types).map((k) => k.key), ['grocery', 'sport:tennis'])
  assert.deepEqual(groceryLabels(types).map((l) => l.label), ['lidl', 'organic'])
})

test('normalise drops trips for categories and sorts favourites', () => {
  const p: StudentProfile = {
    programme: null, modes: ['walk'],
    destinations: { 'sport:tennis': { importance: 2, fine_time_min: 20, trips_per_week: 3 } },
    labels: { grocery: ['organic', 'lidl', 'lidl'] },
  }
  assert.deepEqual(normalise(p, types), {
    programme: null, modes: ['walk'], destinations: { 'sport:tennis': { importance: 2 } }, labels: { grocery: ['lidl', 'organic'] },
  })
})

test('sanitize drops unknown categories and supermarkets', () => {
  const p: StudentProfile = {
    programme: null, modes: ['walk'],
    destinations: { 'sport:golf': { importance: 2 }, 'sport:tennis': { importance: 1 } },
    labels: { grocery: ['lidl', 'norma'] },
  }
  const { profile, dropped } = sanitize(p, { types, programmes: [], modes: ['walk'] })
  assert.equal(dropped, true)
  assert.deepEqual(Object.keys(profile.destinations), ['sport:tennis'])
  assert.deepEqual(profile.labels, { grocery: ['lidl'] })
})
