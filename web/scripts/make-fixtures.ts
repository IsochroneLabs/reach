/**
 * Generates the sample data of fixture mode: src/api/fixtures/tuebingen.json.
 *
 *   node scripts/make-fixtures.ts        (from web/; Node ≥ 22.18 strips the types)
 *
 * SAMPLE DATA, NOT RESULTS. Cells are real EPSG:3035 grid ids around Tübingen, places and stops
 * are placed at roughly the right spots, but every travel time comes from the simple model below
 * (distance × detour, a hand-made height model, six made-up bus lines). The app labels the data
 * "Sample data". Deterministic: the same script always writes the same file.
 *
 * Destination types, trip windows, campus sites, programmes and personas mirror config/*.yaml
 * (24 Nov 2026); keep them in step by hand when those files change.
 */
import { writeFileSync } from 'node:fs'

import { cellCentre, cellIdAt, fromLaea, toLaea, type LonLat } from '../src/geo/laea.ts'

const OUT = new URL('../src/api/fixtures/tuebingen.json', import.meta.url)

// --- config mirrors (config/config.yaml, config/campus.yaml, config/personas.yaml) -------------

const TRIP_WINDOWS = [
  { trip_window: 'morning_lecture', weekday: 'tuesday', time: '08:10', kind: 'arrive_by', direction: 'to', reference_date: '2026-11-24' },
  { trip_window: 'midday', weekday: 'tuesday', time: '12:00', kind: 'depart_at', direction: 'to', reference_date: '2026-11-24' },
  { trip_window: 'evening', weekday: 'tuesday', time: '18:00', kind: 'depart_at', direction: 'to', reference_date: '2026-11-24' },
  { trip_window: 'night_return', weekday: 'saturday', time: '00:30', kind: 'depart_at', direction: 'back', reference_date: '2026-11-21' },
  { trip_window: 'weekend_station', weekday: 'saturday', time: '10:00', kind: 'depart_at', direction: 'to', reference_date: '2026-11-21' },
] as const

const TYPES: [string, string, string, string, number, number][] = [
  // key, en, de, trip window, fine_time_min, trips_per_week
  ['campus_site', 'Campus', 'Campus', 'morning_lecture', 20, 5],
  ['mensa', 'Mensa', 'Mensa', 'midday', 15, 3],
  ['library', 'Library', 'Bibliothek', 'midday', 20, 2],
  ['university_sports', 'University sports', 'Hochschulsport', 'evening', 20, 1],
  ['grocery', 'Supermarket', 'Supermarkt', 'evening', 10, 2],
  ['pharmacy', 'Pharmacy', 'Apotheke', 'midday', 15, 0.1],
  ['doctor', 'Doctor', 'Arztpraxis', 'midday', 15, 0.1],
  ['main_station', 'Main station', 'Hauptbahnhof', 'weekend_station', 25, 0.5],
  ['park', 'Park', 'Park', 'evening', 10, 1],
  ['gym', 'Gym', 'Fitnessstudio', 'evening', 20, 2],
  ['climbing', 'Climbing', 'Klettern', 'evening', 20, 2],
  ['swimming', 'Swimming', 'Schwimmen', 'evening', 20, 1],
  ['sports_club', 'Sports club', 'Sportverein', 'evening', 20, 2],
  ['music', 'Music', 'Musik', 'evening', 20, 1],
  ['nightlife', 'Going out', 'Ausgehen', 'night_return', 20, 1],
  ['cinema_theatre', 'Cinema and theatre', 'Kino und Theater', 'evening', 25, 0.5],
  ['place_of_worship', 'Place of worship', 'Gotteshaus', 'weekend_station', 20, 1],
]

const SITES: [string, string, LonLat][] = [
  ['tal', 'Tal (Wilhelmstraße, Neue Aula, Kupferbau)', [9.062, 48.525]],
  ['morgenstelle', 'Morgenstelle', [9.035, 48.537]],
  ['sand', 'Sand', [9.067, 48.534]],
  ['schnarrenberg', 'Schnarrenberg (University Hospital)', [9.04, 48.532]],
]
// campus.default_mix (decided 24 Nov 2026): Tal + Morgenstelle, equal.
const DEFAULT_MIX: Record<string, number> = { tal: 0.5, morgenstelle: 0.5 }

const PROGRAMMES: [string, string, string, string[]][] = [
  ['computer_science', 'Computer science', 'Informatik', ['sand', 'morgenstelle']],
  ['data_science_ml', 'Data science / machine learning', 'Data Science / Machine Learning', ['sand']],
  ['mathematics', 'Mathematics', 'Mathematik', ['morgenstelle']],
  ['physics', 'Physics', 'Physik', ['morgenstelle']],
  ['chemistry', 'Chemistry', 'Chemie', ['morgenstelle']],
  ['biology', 'Biology', 'Biologie', ['morgenstelle']],
  ['pharmacy', 'Pharmacy', 'Pharmazie', ['morgenstelle']],
  ['medicine', 'Medicine', 'Medizin', ['morgenstelle', 'schnarrenberg']],
  ['economics', 'Economics and business', 'Wirtschaftswissenschaft', ['tal']],
  ['law', 'Law', 'Rechtswissenschaft', ['tal']],
  ['humanities', 'Humanities', 'Geisteswissenschaften', ['tal']],
  ['social_sciences', 'Social sciences', 'Sozialwissenschaften', ['tal']],
  ['psychology', 'Psychology', 'Psychologie', ['tal']],
  ['sports_science', 'Sports science', 'Sportwissenschaft', ['tal']],
]

type PersonaDest = Record<string, number | { importance: number; trips_per_week?: number; fine_time_min?: number }>
const PERSONAS: [string, string, string, string, string[], PersonaDest][] = [
  ['lena', 'Lena, first semester biology', 'Lena, Biologie im ersten Semester', 'biology', ['walk', 'transit'],
    { campus_site: 3, mensa: 2, grocery: 2, climbing: { importance: 2, trips_per_week: 2 }, main_station: 1 }],
  ['arjun', "Arjun, exchange master's in computer science", 'Arjun, Austausch-Master Informatik', 'computer_science', ['walk', 'bike', 'transit'],
    { campus_site: 3, gym: { importance: 2, trips_per_week: 3 }, nightlife: { importance: 2, trips_per_week: 1 }, grocery: 2, library: 1 }],
  ['marie', 'Marie, medicine with early hospital days', 'Marie, Medizin mit frühen Klinikdiensten', 'medicine', ['bike', 'transit'],
    { campus_site: { importance: 3, fine_time_min: 15 }, swimming: { importance: 2, trips_per_week: 2 }, grocery: 1, main_station: 2 }],
  ['tom', 'Tom, economics, goes out a lot', 'Tom, Wirtschaft, oft unterwegs', 'economics', ['walk', 'bike'],
    { campus_site: 2, nightlife: { importance: 3, trips_per_week: 2 }, sports_club: 1, mensa: 2 }],
]

// --- places (approximate; names of real places, but sample data) -----------------------------

const AREAS: [string, string, LonLat, number][] = [
  // id, name, centre, radius (m) of the sample cells
  ['altstadt', 'Altstadt', [9.0545, 48.5205], 280],
  ['universitaet', 'Universität', [9.0625, 48.5265], 300],
  ['oesterberg', 'Österberg', [9.068, 48.5215], 250],
  ['wanne', 'Wanne', [9.056, 48.5345], 330],
  ['waldhaeuser_ost', 'Waldhäuser-Ost', [9.047, 48.5395], 300],
  ['schoenblick', 'Schönblick/Winkelwiese', [9.04, 48.529], 300],
  ['weststadt', 'Weststadt', [9.037, 48.517], 380],
  ['suedstadt', 'Südstadt', [9.059, 48.511], 400],
  ['derendingen', 'Derendingen', [9.048, 48.501], 380],
  ['lustnau', 'Lustnau', [9.08, 48.526], 400],
]
// Cells with an address but no residents (origin kind "address", A1).
const ADDRESS_CELL_SPOTS: LonLat[] = [
  [9.0685, 48.5345], [9.0695, 48.5352], [9.0675, 48.5338], [9.0362, 48.5368], [9.0372, 48.5378],
  [9.0412, 48.5322], [9.0555, 48.5160], [9.0548, 48.5152],
]

const DESTS: [string, string, LonLat][] = [
  ['mensa', 'Mensa Wilhelmstraße', [9.0616, 48.5262]],
  ['mensa', 'Mensa Morgenstelle', [9.0353, 48.5375]],
  ['mensa', 'Mensa Prinz Karl', [9.056, 48.5205]],
  ['university_sports', 'University sports grounds (Wilhelmstraße)', [9.07, 48.53]],
  ['library', 'University library', [9.0603, 48.5247]],
  ['library', 'City library', [9.0545, 48.5195]],
  ['grocery', 'Supermarket Altstadt', [9.052, 48.519]],
  ['grocery', 'Supermarket Südstadt', [9.06, 48.5115]],
  ['grocery', 'Supermarket Derendingen', [9.044, 48.5]],
  ['grocery', 'Supermarket Weststadt', [9.0365, 48.5165]],
  ['grocery', 'Supermarket Lustnau', [9.079, 48.525]],
  ['grocery', 'Supermarket Waldhäuser-Ost', [9.0475, 48.5405]],
  ['grocery', 'Supermarket Wilhelmstraße', [9.064, 48.5275]],
  ['pharmacy', 'Pharmacy Marktplatz', [9.056, 48.5205]],
  ['pharmacy', 'Pharmacy Lustnau', [9.0795, 48.5262]],
  ['pharmacy', 'Pharmacy Südstadt', [9.059, 48.5108]],
  ['doctor', 'General practice Altstadt', [9.057, 48.5215]],
  ['doctor', 'General practice Weststadt', [9.04, 48.518]],
  ['doctor', 'General practice Lustnau', [9.0785, 48.527]],
  ['doctor', 'General practice Südstadt', [9.06, 48.512]],
  ['main_station', 'Tübingen Hauptbahnhof', [9.0555, 48.5155]],
  ['park', 'Alter Botanischer Garten', [9.057, 48.5235]],
  ['park', 'Anlagenpark', [9.056, 48.517]],
  ['park', 'Park Französisches Viertel', [9.058, 48.5095]],
  ['gym', 'Gym Südstadt', [9.06, 48.513]],
  ['gym', 'Gym Lustnau', [9.079, 48.5245]],
  ['gym', 'Gym Weststadt', [9.045, 48.52]],
  ['climbing', 'Climbing centre Weststadt', [9.033, 48.514]],
  ['climbing', 'University climbing wall', [9.07, 48.5302]],
  ['swimming', 'Indoor pool Nord', [9.049, 48.533]],
  ['swimming', 'Outdoor pool', [9.039, 48.514]],
  ['swimming', 'Uhlandbad', [9.0585, 48.518]],
  ['sports_club', 'Sports club Lustnau', [9.073, 48.529]],
  ['sports_club', 'Sports club Derendingen', [9.046, 48.505]],
  ['sports_club', 'Sports club Weststadt', [9.038, 48.523]],
  ['music', 'Music school', [9.053, 48.517]],
  ['nightlife', 'Bars Altstadt', [9.0545, 48.521]],
  ['nightlife', 'Club near the station', [9.054, 48.515]],
  ['nightlife', 'Pub Lustnau', [9.08, 48.5255]],
  ['cinema_theatre', 'Cinema Museum', [9.0585, 48.5215]],
  ['cinema_theatre', 'Landestheater (LTT)', [9.0535, 48.518]],
  ['place_of_worship', 'Stiftskirche', [9.0565, 48.5205]],
  ['place_of_worship', 'St. Johannes', [9.058, 48.5195]],
  ['place_of_worship', 'Eberhardskirche', [9.062, 48.513]],
]

const ADDRESSES: [string, string, LonLat][] = [
  ['Hechinger Straße', '12', [9.0565, 48.5108]],
  ['Wilhelmstraße', '30', [9.0628, 48.5262]],
  ['Nürtinger Straße', '20', [9.0805, 48.5262]],
  ['Waldhäuser Straße', '50', [9.0468, 48.5392]],
  ['Mohlstraße', '8', [9.0575, 48.5318]],
  ['Herrenberger Straße', '40', [9.0372, 48.5172]],
  ['Stuttgarter Straße', '5', [9.0782, 48.5238]],
  ['Haaggasse', '3', [9.0535, 48.5208]],
  ['Derendinger Straße', '60', [9.0488, 48.5032]],
  ['Gartenstraße', '15', [9.0672, 48.5222]],
  ['Sindelfinger Straße', '10', [9.0405, 48.5292]],
  ['Auf der Morgenstelle', '16', [9.0366, 48.5372]],
]

// --- model -------------------------------------------------------------------------------------

const STOPS: Record<string, [string, LonLat]> = {
  derendingen: ['Derendingen', [9.048, 48.5015]],
  suedstadt: ['Französisches Viertel', [9.0595, 48.5105]],
  zob: ['Hauptbahnhof (ZOB)', [9.0555, 48.5163]],
  neckar: ['Neckarbrücke', [9.0575, 48.5195]],
  uni: ['Uni/Neue Aula', [9.062, 48.525]],
  wanne: ['Wanne', [9.0565, 48.533]],
  who: ['Waldhäuser-Ost', [9.047, 48.5395]],
  weststadt: ['Westbahnhof', [9.038, 48.5175]],
  lustnau: ['Lustnau Zentrum', [9.079, 48.5265]],
  oesterberg: ['Österberg', [9.0665, 48.521]],
  schoenblick: ['Schönblick', [9.042, 48.528]],
  schnarrenberg: ['Klinikum Schnarrenberg', [9.0405, 48.5325]],
  morgenstelle: ['Morgenstelle', [9.0355, 48.5375]],
  sand: ['Sand', [9.069, 48.5345]],
}
const LINES: Record<string, string[]> = {
  '1': ['derendingen', 'suedstadt', 'zob', 'neckar', 'uni', 'wanne', 'who'],
  '2': ['weststadt', 'zob', 'neckar', 'uni', 'lustnau'],
  '4': ['zob', 'neckar', 'oesterberg', 'lustnau'],
  '5': ['zob', 'schoenblick', 'schnarrenberg', 'morgenstelle'],
  '7': ['suedstadt', 'zob', 'neckar', 'uni', 'morgenstelle', 'who'],
  '13': ['lustnau', 'sand', 'wanne', 'morgenstelle', 'schnarrenberg'],
}
const NIGHT_LINES = new Set(['1', '2', '5'])
// mean wait at the stop per trip window (min); night: 40-min headway
const WAIT: Record<string, number> = { morning_lecture: 4, midday: 7, evening: 7, weekend_station: 10, night_return: 20 }
const LAST_NIGHT: Record<string, string> = { '1': '01:12', '2': '00:47', '5': '00:55' }

const HILLS: [LonLat, number, number][] = [
  // centre, height above the valley (m), sigma (m)
  [[9.035, 48.537], 110, 900], [[9.047, 48.54], 100, 700], [[9.04, 48.532], 90, 600],
  [[9.067, 48.522], 60, 300], [[9.04, 48.528], 70, 500], [[9.057, 48.535], 70, 600],
  [[9.05, 48.519], 40, 250],
]

const en = (p: LonLat) => toLaea(p)
const dist = (a: LonLat, b: LonLat) => {
  const [ax, ay] = en(a)
  const [bx, by] = en(b)
  return Math.hypot(ax - bx, ay - by)
}
const height = (p: LonLat) =>
  HILLS.reduce((h, [c, top, s]) => h + top * Math.exp(-(dist(p, c) ** 2) / (2 * s * s)), 0)
const climb = (from: LonLat, to: LonLat) => Math.max(0, height(to) - height(from))

/** Deterministic noise in [1 - a, 1 + a] from a string. */
function noise(key: string, a = 0.06): number {
  let h = 2166136261
  for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619)
  return 1 + a * ((((h >>> 0) % 1000) / 1000) * 2 - 1)
}

const walkS = (a: LonLat, b: LonLat) => (dist(a, b) * 1.3) / (5 / 3.6) + climb(a, b) * 6
const bikeS = (a: LonLat, b: LonLat) => 60 + (dist(a, b) * 1.35) / (15 / 3.6) + climb(a, b) * 8

function rideS(line: string[], i: number, j: number): number {
  let s = 0
  const [lo, hi] = i < j ? [i, j] : [j, i]
  for (let k = lo; k < hi; k++) s += (dist(STOPS[line[k]][1], STOPS[line[k + 1]][1]) * 1.3) / (20 / 3.6) + 30
  return s
}

interface TransitLeg { total: number; access: number; wait: number; ride: number; egress: number; transfers: number; stop: string; route: string }

function transit(from: LonLat, to: LonLat, window: string): TransitLeg | null {
  const night = window === 'night_return'
  const lines = Object.entries(LINES).filter(([id]) => !night || NIGHT_LINES.has(id))
  const near = (p: LonLat) =>
    Object.keys(STOPS).map((k) => [k, (dist(p, STOPS[k][1]) * 1.3) / (5 / 3.6)] as const)
      .sort((x, y) => x[1] - y[1]).slice(0, 3)
  let best: TransitLeg | null = null
  for (const [sa, access] of near(from)) {
    for (const [sb, egress] of near(to)) {
      if (sa === sb) continue
      for (const [id, l] of lines) {
        const i = l.indexOf(sa)
        const j = l.indexOf(sb)
        if (i >= 0 && j >= 0) {
          const ride = rideS(l, i, j)
          const total = access + WAIT[window] * 60 + ride + egress
          if (!best || total < best.total) best = { total, access, wait: WAIT[window] * 60, ride, egress, transfers: 0, stop: sa, route: id }
        }
        // one transfer
        if (i < 0) continue
        for (const [id2, l2] of lines) {
          if (id2 === id) continue
          const j2 = l2.indexOf(sb)
          if (j2 < 0) continue
          for (const x of l) {
            const xi = l2.indexOf(x)
            if (xi < 0 || x === sa) continue
            const ride = rideS(l, i, l.indexOf(x)) + rideS(l2, xi, j2)
            const wait = WAIT[window] * 60 + 4 * 60
            const total = access + wait + ride + egress
            if (!best || total < best.total) best = { total, access, wait, ride, egress, transfers: 1, stop: sa, route: id }
          }
        }
      }
    }
  }
  return best
}

// --- build -------------------------------------------------------------------------------------

const cells = new Map<string, { area: string; pop: 0 | 1 }>()
for (const [id, , centre, r] of AREAS) {
  const [cx, cy] = en(centre)
  for (let x = cx - r; x <= cx + r; x += 100) {
    for (let y = cy - r; y <= cy + r; y += 100) {
      if (Math.hypot(x - cx, y - cy) > r) continue
      const cellId = cellIdAt(fromLaea([x, y]))
      if (noise(cellId, 1) < 0.18) continue // gaps: not every cell has residents
      if (!cells.has(cellId)) cells.set(cellId, { area: id, pop: 1 })
    }
  }
}
const nearestArea = (p: LonLat) => AREAS.map(([id, , c]) => [id, dist(p, c)] as const).sort((a, b) => a[1] - b[1])[0][0]
for (const p of [...ADDRESS_CELL_SPOTS, ...ADDRESSES.map((a) => a[2])]) {
  const id = cellIdAt(p)
  if (!cells.has(id)) cells.set(id, { area: nearestArea(p), pop: 0 })
}

const cellIds = [...cells.keys()].sort()
const destinations = [
  ...SITES.map(([id, name, point]) => ({ id: `campus_site/${id}`, type: 'campus_site', name, point })),
  ...DESTS.map(([type, name, point], i) => ({ id: `${type}/s${i + 1}`, type, name, point })),
]
// Targets: every campus site on its own (M7 mean per programme), every other type by nearest.
const targets = [...SITES.map(([id]) => `campus_site/${id}`), ...TYPES.filter((t) => t[0] !== 'campus_site').map((t) => t[0])]
const windowOf = (target: string) => TYPES.find((t) => t[0] === (target.startsWith('campus_site/') ? 'campus_site' : target))![3]
const stopKeys = Object.keys(STOPS)
const routeKeys = Object.keys(LINES)

const round = (s: number) => Math.round(s)
const times = cellIds.map((cellId) => {
  const c = cellCentre(cellId)!
  return targets.map((target) => {
    const candidates = target.startsWith('campus_site/')
      ? destinations.filter((d) => d.id === target)
      : destinations.filter((d) => d.type === target)
    const w = windowOf(target)
    const back = w === 'night_return'
    // nearest by walking time (the API takes the minimum over the k nearest per mode)
    const d = candidates
      .map((x) => ({ x, s: back ? walkS(x.point, c) : walkS(c, x.point) }))
      .sort((a, b) => a.s - b.s)[0].x
    const [from, to] = back ? [d.point, c] : [c, d.point]
    const k = `${cellId}|${target}`
    const walk = walkS(from, to) * noise(k + 'w')
    const bike = bikeS(from, to) * noise(k + 'b')
    const t = transit(from, to, w)
    const destIdx = destinations.indexOf(d)
    if (!t || t.total >= walk) {
      // no bus beats walking: transit = walking, legs empty (walk_only)
      return [destIdx, round(walk), round(bike), round(walk), -1, 0, 0, 0, 0, -1, -1]
    }
    const f = noise(k + 't')
    return [destIdx, round(walk), round(bike), round(t.total * f), round(t.access), round(t.wait),
      round(t.ride * f), round(t.egress), t.transfers, stopKeys.indexOf(t.stop), routeKeys.indexOf(t.route)]
  })
})

const all = cellIds.map((id) => cellCentre(id)!)
const lons = all.map((p) => p[0])
const lats = all.map((p) => p[1])
const r5 = (x: number) => Math.round(x * 1e5) / 1e5

const data = {
  _note: 'SAMPLE DATA generated by web/scripts/make-fixtures.ts; travel times are modelled, not routed.',
  meta: {
    run_id: '20261120T030000Z',
    sources: [
      { source: 'osm', date: '2026-11-20' },
      { source: 'gtfs', date: '2026-11-20', valid_to: '2026-12-12' },
      { source: 'zensus', date: '2022-05-15' },
    ],
    trip_windows: TRIP_WINDOWS,
    bounds: [[r5(Math.min(...lons) - 0.01), r5(Math.min(...lats) - 0.006)], [r5(Math.max(...lons) + 0.01), r5(Math.max(...lats) + 0.006)]],
    modes: ['walk', 'bike', 'transit'],
  },
  destination_types: TYPES.map(([k, e, de, w, fine, trips]) => ({ destination_type: k, label: { en: e, de }, trip_window: w, fine_time_min: fine, trips_per_week: trips })),
  campus_sites: SITES.map(([id, name, point]) => ({
    site_id: id, name, point,
    programmes: PROGRAMMES.filter((p) => p[3].includes(id)).map((p) => p[0]),
    default_share: DEFAULT_MIX[id] ?? 0,
  })),
  programmes: PROGRAMMES.map(([k, e, de, sites]) => ({ programme: k, label: { en: e, de }, sites })),
  personas: PERSONAS.map(([k, e, de, programme, modes, dests]) => ({
    persona: k, label: { en: e, de },
    profile: {
      programme, modes,
      destinations: Object.fromEntries(Object.entries(dests).map(([t, v]) => [t, typeof v === 'number' ? { importance: v } : v])),
    },
  })),
  areas: AREAS.map(([id, name, centre]) => ({ area_id: id, name, centre })),
  destinations: destinations.map((d) => ({ id: d.id, type: d.type, name: d.name, point: [r5(d.point[0]), r5(d.point[1])] })),
  stops: stopKeys.map((k) => STOPS[k][0]),
  routes: routeKeys,
  last_night: routeKeys.map((r) => LAST_NIGHT[r] ?? null),
  addresses: ADDRESSES.map(([street, no, p]) => ({ label: `${street} ${no}, Tübingen`, cell_id: cellIdAt(p), point: p })),
  targets,
  cells: cellIds.map((id) => [id, cells.get(id)!.area, cells.get(id)!.pop]),
  // per cell, per target: [dest, walk_s, bike_s, transit_s, access_s, wait_s, ride_s, egress_s, transfers, stop, route]
  times,
}

writeFileSync(OUT, JSON.stringify(data))
console.log(`wrote ${OUT.pathname}: ${cellIds.length} cells (${cellIds.filter((c) => cells.get(c)!.pop === 0).length} address cells), ${destinations.length} destinations, ${JSON.stringify(data).length} bytes`)
