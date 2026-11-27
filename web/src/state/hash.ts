/**
 * Profile and places in the URL hash (docs/app_screens.md §3.2). The part after "#" never reaches
 * a server, so a shared link does not put the profile into access logs.
 *
 *   #v=1&p=prog:bachelor-biologie;m:wbt;d:campus_site.3,mensa.2..2&pl=9.05650,48.51080,Hechinger%20Str.%2012|…&r=450,
 *
 * Destinations: key.importance.fine.trips (empty part = type default; key = a type or a sport or
 * hobby category such as `sport:tennis`). Favourite supermarkets: `g:lidl.organic`. Modes: w walk,
 * b bike, t transit, x bike + transit. Rents (r) only when the student ticks "include rents in the link".
 * Standalone (no imports besides types), so node --test can load it.
 */
import type { Importance, Mode } from '../api/types'
import type { Place, PlaceId, StudentProfile } from './profile'

const MODE_CODE: Record<Mode, string> = { walk: 'w', bike: 'b', transit: 't', bike_transit: 'x' }
const CODE_MODE: Record<string, Mode> = { w: 'walk', b: 'bike', t: 'transit', x: 'bike_transit' }
const IDS: PlaceId[] = ['A', 'B', 'C']

export interface HashState {
  profile: StudentProfile | null
  places: Place[] | null
  /** the link carried parts that could not be read */
  bad: boolean
}

const num = (s: string) => (s === '' ? undefined : Number(s))

export function encodeHash(profile: StudentProfile, places: Place[], withRents: boolean): string {
  const d = Object.entries(profile.destinations)
    .map(([k, v]) => {
      const parts = [k, String(v.importance), v.fine_time_min ?? '']
      while (parts.length > 2 && parts[parts.length - 1] === '') parts.pop()
      return parts.join('.')
    })
    .join(',')
  const p = [
    profile.programme ? `prog:${profile.programme}` : '',
    `m:${profile.modes.map((m) => MODE_CODE[m]).join('')}`,
    `d:${d}`,
    profile.labels?.grocery?.length ? `g:${profile.labels.grocery.join('.')}` : '',
  ]
    .filter(Boolean)
    .join(';')
  const params = new URLSearchParams({ v: '1', p })
  if (places.length) {
    params.set(
      'pl',
      places
        .map((x) => [x.point[0].toFixed(5), x.point[1].toFixed(5), encodeURIComponent(x.label ?? '')].join(','))
        .join('|'),
    )
    if (withRents && places.some((x) => x.rentEur != null)) {
      params.set('r', places.map((x) => (x.rentEur == null ? '' : String(x.rentEur))).join(','))
    }
  }
  return '#' + params.toString().replace(/%3A/g, ':').replace(/%3B/g, ';').replace(/%2C/g, ',').replace(/%7C/g, '|')
}

/** Reads the hash. Cell ids are filled in by the caller (cellIdAt), to keep this file standalone. */
export function decodeHash(hash: string, cellIdAt: (p: [number, number]) => string): HashState {
  const out: HashState = { profile: null, places: null, bad: false }
  const h = hash.replace(/^#/, '')
  if (!h) return out
  const params = new URLSearchParams(h)
  if (params.get('v') !== '1') return { ...out, bad: true }
  const p = params.get('p')
  if (p) {
    const profile: StudentProfile = { programme: null, modes: [], destinations: {} }
    for (const part of p.split(';')) {
      const [key, value = ''] = part.split(/:(.*)/s)
      if (key === 'prog') profile.programme = value || null
      else if (key === 'm') {
        for (const c of value) {
          if (CODE_MODE[c]) profile.modes.push(CODE_MODE[c])
          else out.bad = true
        }
      } else if (key === 'd') {
        for (const item of value.split(',').filter(Boolean)) {
          // older links carry a fourth part (trips per week, removed N30): ignored
          const [type, imp, fine = ''] = item.split('.')
          const importance = Number(imp)
          if (!type || ![0, 1, 2, 3].includes(importance)) {
            out.bad = true
            continue
          }
          const v: StudentProfile['destinations'][string] = { importance: importance as Importance }
          const f = num(fine)
          if (f !== undefined && Number.isFinite(f)) v.fine_time_min = f
          else if (f !== undefined) out.bad = true
          profile.destinations[type] = v
        }
      } else if (key === 'g') {
        const grocery = value.split('.').filter((x) => /^[a-z0-9_]+$/.test(x))
        if (grocery.length !== value.split('.').filter(Boolean).length) out.bad = true
        if (grocery.length) profile.labels = { grocery }
      } else out.bad = true
    }
    out.profile = profile
  }
  const pl = params.get('pl')
  if (pl) {
    const rents = (params.get('r') ?? '').split(',')
    const places: Place[] = []
    for (const [i, item] of pl.split('|').entries()) {
      if (i >= IDS.length) {
        out.bad = true
        break
      }
      const [lon, lat, rawLabel = ''] = item.split(',')
      let label: string | null = null
      try {
        label = decodeURIComponent(rawLabel).trim() || null
      } catch {
        out.bad = true
      }
      const point: [number, number] = [Number(lon), Number(lat)]
      if (!point.every(Number.isFinite) || Math.abs(point[0]) > 180 || Math.abs(point[1]) > 90) {
        out.bad = true
        continue
      }
      const rent = num(rents[i] ?? '')
      places.push({
        id: IDS[places.length],
        point,
        cellId: cellIdAt(point),
        label,
        rentEur: rent !== undefined && Number.isFinite(rent) && rent >= 0 ? rent : null,
      })
    }
    out.places = places
  }
  return out
}
