import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Trip } from '../api/types.ts'
import { chooseTrips } from './trips.ts'

const trip = (destination_type: string, destination_id: string, mode: Trip['mode'], minutes: number, share?: number): Trip => ({
  destination_type,
  destination_id,
  name: null,
  mode,
  trip_window: 'morning_lecture',
  minutes,
  ...(share != null ? { share } : {}),
})

test('every campus site of the student, largest share first, not just the nearest', () => {
  const trips = [
    trip('campus_site', 'campus_site:tal', 'bike', 6, 0.15),
    trip('campus_site', 'campus_site:morgenstelle', 'bike', 14, 0.65),
    trip('campus_site', 'campus_site:morgenstelle', 'walk', 30, 0.65),
    trip('campus_site', 'campus_site:sand', 'bike', 9, 0.2),
  ]
  const out = chooseTrips(trips, ['walk', 'bike'], ['campus_site'])
  assert.deepEqual(
    out.map((c) => [c.trip.destination_id, c.trip.mode]),
    [
      ['campus_site:morgenstelle', 'bike'],
      ['campus_site:sand', 'bike'],
      ['campus_site:tal', 'bike'],
    ],
  )
})

test('label keys keep their own trips and modes outside the profile are ignored', () => {
  const trips = [
    trip('sport:tennis', 'sport:tennis:w1', 'walk', 12),
    trip('grocery', 'grocery:n1', 'transit', 3),
    trip('grocery', 'grocery:n1', 'walk', 7),
  ]
  const out = chooseTrips(trips, ['walk'], ['grocery', 'sport:tennis', 'mensa'])
  assert.deepEqual(
    out.map((c) => [c.key, c.trip.minutes]),
    [
      ['grocery', 7],
      ['sport:tennis', 12],
    ],
  )
})
