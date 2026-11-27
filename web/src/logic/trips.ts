import type { Mode, Trip } from '../api/types'

export interface ChosenTrip {
  /** the profile key the trip belongs to (`grocery`, `sport:tennis`, `campus_site`) */
  key: string
  trip: Trip
}

const CAMPUS = 'campus_site'

/**
 * The trips a place card shows, routes and labels on the map (N29): per profile key the fastest
 * trip among the student's modes; for the campus every campus site of the student (the API sends
 * only those), largest share first, so the route goes to the student's own campus and never to
 * the nearest site of another programme. `keys` are in display order.
 */
export function chooseTrips(trips: Trip[], modes: Mode[], keys: string[]): ChosenTrip[] {
  const best = new Map<string, Trip>()
  for (const tr of trips) {
    if (tr.minutes == null || !modes.includes(tr.mode)) continue
    const id = tr.destination_type === CAMPUS ? `${CAMPUS}|${tr.destination_id}` : tr.destination_type
    const cur = best.get(id)
    if (!cur || (cur.minutes ?? Infinity) > tr.minutes) best.set(id, tr)
  }
  const out: ChosenTrip[] = []
  for (const key of keys) {
    if (key === CAMPUS) {
      const sites = [...best.entries()].filter(([id]) => id.startsWith(`${CAMPUS}|`)).map(([, tr]) => tr)
      sites.sort((a, b) => (b.share ?? 0) - (a.share ?? 0) || (a.minutes ?? 0) - (b.minutes ?? 0))
      for (const trip of sites) out.push({ key, trip })
      continue
    }
    const trip = best.get(key) ?? best.get(key.split(':')[0])
    if (trip) out.push({ key, trip })
  }
  return out
}
