// Unit tests for the programme search (`npm run test:unit`).
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { fold, matchProgrammes, shortName } from './programmes.ts'

const list = [
  { id: 'b-wi', text: 'Wirtschaftsinformatik (Bachelor)' },
  { id: 'b-eba', text: 'Economics and Business Administration (Bachelor)' },
  { id: 'm-oek', text: 'Ökonomie und Gesellschaft (Master)' },
  { id: 'b-i', text: 'Informatik (Bachelor)' },
]

test('fold drops case, accents and ß', () => {
  assert.equal(fold('Ökonomie Straße'), 'okonomie strasse')
})

test('every word must match, shortest label first', () => {
  assert.deepEqual(matchProgrammes(list, 'informatik'), ['b-i', 'b-wi'])
  assert.deepEqual(matchProgrammes(list, 'bachelor ECON'), ['b-eba'])
  assert.deepEqual(matchProgrammes(list, 'okonomie'), ['m-oek'])
  assert.deepEqual(matchProgrammes(list, 'xyz'), [])
})

test('short building names drop the address in brackets', () => {
  assert.equal(shortName('WiWi Sem Mohl (Mohlstraße 36)'), 'WiWi Sem Mohl')
  assert.equal(shortName('Hölderlinstraße 5 – Kupferbau'), 'Hölderlinstraße 5 – Kupferbau')
})
