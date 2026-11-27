/**
 * Fixture mode: answers the API in the browser from the sample data in tuebingen.json.
 *
 * It imitates the API of S1.4 and the fit proposal of methodology §6 (S1.3, not yet confirmed),
 * so the app can be built and tested before S1.10. It is not the fit of reach: the real API
 * computes the fit on the server (architecture rule 5) and this file is never used with an API.
 * Also used by Playwright (tests/fixtures.ts) to answer /api/* requests.
 */
import { cellCentre } from '../../geo/laea.ts'
import {
  ApiError,
  type AddressHit,
  type Area,
  type CellDetail,
  type CellFits,
  type FitPart,
  type FitRequest,
  type FitResponse,
  type LonLat,
  type Mode,
  type Reason,
  type Trip,
} from '../types.ts'
import data from './tuebingen.json' with { type: 'json' }
import type { Transport } from '../client.ts'

type TimeRow = number[] // [dest, walk_s, bike_s, transit_s, access_s, wait_s, ride_s, egress_s, transfers, stop, route]

const D = data as unknown as {
  meta: unknown
  destination_types: {
    destination_type: string
    trip_window: string
    fine_time_min: number
    trips_per_week: number
    label: { en: string }
    labels?: { label: string; kind: string }[]
  }[]
  campus_sites: { site_id: string; default_share: number }[]
  programmes: { programme: string; sites: string[] }[]
  personas: unknown[]
  areas: { area_id: string; name: string }[]
  destinations: { id: string; type: string; name: string; point: LonLat; labels: string[] }[]
  stops: string[]
  routes: string[]
  last_night: (string | null)[]
  addresses: AddressHit[]
  targets: string[]
  cells: [string, string, 0 | 1][]
  times: TimeRow[][]
}

const MODE_COL: Record<Mode, number> = { walk: 1, bike: 2, transit: 3, bike_transit: 3 }
const cellIndex = new Map(D.cells.map((c, i) => [c[0], i]))
const targetIndex = new Map(D.targets.map((t, i) => [t, i]))
const typeInfo = new Map(D.destination_types.map((t) => [t.destination_type, t]))
const areaName = new Map(D.areas.map((a) => [a.area_id, a.name]))
const isContainer = (type: string) => !!typeInfo.get(type)?.labels?.some((l) => l.kind === 'category')

/** A profile key (`grocery`, `sport:tennis`) → its type, category and term defaults. */
function keyInfo(key: string) {
  const [type, category = null] = key.split(':') as [string, string?]
  const info = typeInfo.get(type)
  if (!info) return null
  if (category == null ? isContainer(type) : !targetIndex.has(key)) return null
  return {
    type,
    category,
    trip_window: info.trip_window,
    fine_time_min: info.fine_time_min,
    // categories never count in the weekly travel time (methodology §6, QF4)
    trips_per_week: category == null ? info.trips_per_week : 0,
  }
}

// Fit proposal (methodology §6): s = 1 / (1 + (T / (a·t))^p); 0.9 at the fine time, 0.1 at twice.
const P = Math.log2(81)
const A = Math.SQRT2
const score = (min: number | null, fine: number) => (min == null ? 0 : 1 / (1 + (min / (A * fine)) ** P))

interface TypeTime {
  type: string
  weight: number
  fine: number
  trips: number
  minutes: number | null
  mode: Mode | null
  /** target row used (for reasons): the fastest campus site, or the nearest destination */
  row: TimeRow | null
}

function validate(p: FitRequest): void {
  if (!Array.isArray(p.modes) || p.modes.length === 0) throw new ApiError(422, 'modes: at least one mode')
  for (const [t, v] of Object.entries(p.destinations ?? {})) {
    if (!keyInfo(t)) throw new ApiError(422, `destinations.${t}: unknown destination type or category`)
    if (![0, 1, 2, 3].includes(v.importance)) throw new ApiError(422, `destinations.${t}.importance: 0–3`)
  }
  for (const l of p.labels?.grocery ?? []) {
    if (!targetIndex.has(`grocery:${l}`)) throw new ApiError(422, `labels.grocery: unknown supermarket ${l}`)
  }
  if (p.programme && !D.programmes.some((x) => x.programme === p.programme))
    throw new ApiError(422, `programme: unknown programme ${p.programme}`)
}

/** Campus site weights: campus_days, else the programme's sites equally, else the default mix. */
function campusWeights(p: FitRequest): [string, number][] {
  if (p.campus_days && Object.keys(p.campus_days).length) return Object.entries(p.campus_days)
  const prog = D.programmes.find((x) => x.programme === p.programme)
  if (prog) return prog.sites.map((s) => [s, 1])
  return D.campus_sites.filter((s) => s.default_share > 0).map((s) => [s.site_id, s.default_share])
}

function bestMode(row: TimeRow, modes: Mode[]): [number | null, Mode | null] {
  let best: [number | null, Mode | null] = [null, null]
  for (const m of modes) {
    const min = row[MODE_COL[m]] / 60
    if (min >= 0 && (best[0] == null || min < best[0])) best = [min, m]
  }
  return best
}

/** Targets of one key: grocery with favourites → the nearest of each chosen label (QF3). */
function targetsOf(key: string, p: FitRequest): string[] {
  if (key === 'grocery' && p.labels?.grocery?.length) return p.labels.grocery.map((l) => `grocery:${l}`)
  return [key]
}

function typeTimes(ci: number, p: FitRequest): TypeTime[] {
  const rows = D.times[ci]
  const out: TypeTime[] = []
  for (const [type, v] of Object.entries(p.destinations)) {
    if (v.importance === 0) continue
    const info = keyInfo(type)!
    const fine = v.fine_time_min ?? info.fine_time_min
    const trips = info.category == null ? (v.trips_per_week ?? info.trips_per_week) : 0
    if (type === 'campus_site') {
      // M7: weighted mean over the sites; mode chosen per site
      let sum = 0
      let wsum = 0
      let fastest: { min: number; mode: Mode | null; row: TimeRow } | null = null
      for (const [site, w] of campusWeights(p)) {
        const row = rows[targetIndex.get(`campus_site/${site}`)!]
        const [min, mode] = bestMode(row, p.modes)
        if (min == null) continue
        sum += w * min
        wsum += w
        if (!fastest || min < fastest.min) fastest = { min, mode, row }
      }
      out.push({ type, weight: v.importance, fine, trips, minutes: wsum ? sum / wsum : null, mode: fastest?.mode ?? null, row: fastest?.row ?? null })
    } else {
      // the minimum over the targets (one, or the chosen supermarkets)
      let best: { min: number | null; mode: Mode | null; row: TimeRow } | null = null
      for (const target of targetsOf(type, p)) {
        const row = rows[targetIndex.get(target)!]
        const [min, mode] = bestMode(row, p.modes)
        if (!best || (min != null && (best.min == null || min < best.min))) best = { min, mode, row }
      }
      out.push({ type, weight: v.importance, fine, trips, minutes: best?.min ?? null, mode: best?.mode ?? null, row: best?.row ?? null })
    }
  }
  return out
}

function fitOf(tt: TypeTime[]): { fit: number | null; weekly: number | null; parts: FitPart[] } {
  const wsum = tt.reduce((s, t) => s + t.weight, 0)
  if (!wsum) return { fit: null, weekly: null, parts: [] }
  const scored = tt.map((t) => ({ t, s: score(t.minutes, t.fine) }))
  const points = scored.reduce((s, x) => s + x.t.weight * x.s, 0)
  const weekly = tt.reduce((s, t) => s + (t.minutes == null ? 0 : t.trips * 2 * t.minutes), 0)
  return {
    fit: Math.round((100 * points) / wsum),
    weekly: Math.round(weekly),
    parts: scored.map(({ t, s }) => ({
      destination_type: t.type,
      minutes: t.minutes == null ? null : Math.round(t.minutes),
      mode: t.mode,
      score: Math.round(s * 100) / 100,
      weight: t.weight,
      share: points ? (t.weight * s) / points : 0,
    })),
  }
}

function destName(row: TimeRow | null): string | null {
  return row ? D.destinations[row[0]].name : null
}

function reasonsOf(tt: TypeTime[]): Reason[] {
  const scored = tt.map((t) => ({ t, s: score(t.minutes, t.fine) }))
  const reason = (kind: Reason['kind'], t: TypeTime): Reason => ({
    kind,
    destination_type: t.type,
    name: t.type === 'campus_site' ? null : destName(t.row),
    minutes: t.minutes == null ? null : Math.round(t.minutes),
    mode: t.mode,
    trip_window: keyInfo(t.type)!.trip_window,
  })
  const strengths = scored
    .filter((x) => x.s >= 0.75)
    .sort((a, b) => b.t.weight - a.t.weight || (a.t.minutes ?? 0) - (b.t.minutes ?? 0))
    .slice(0, 2)
    .map((x) => reason('strength', x.t))
  const weakness = scored
    .filter((x) => x.s < 0.6)
    .sort((a, b) => b.t.weight * (1 - b.s) - a.t.weight * (1 - a.s))
    .slice(0, 1)
    .map((x) => reason('weakness', x.t))
  const out = [...strengths, ...weakness]
  const night = tt.find((t) => t.type === 'nightlife')
  if (night?.row && night.mode === 'transit' && night.row[10] >= 0) {
    out.push({ ...reason('reliability', night), value: D.last_night[night.row[10]] ?? undefined })
  }
  if (out.length < 2) {
    const extra = scored.filter((x) => !out.some((r) => r.destination_type === x.t.type)).sort((a, b) => b.s - a.s)[0]
    if (extra) out.push(reason(extra.s >= 0.5 ? 'strength' : 'weakness', extra.t))
  }
  return out.slice(0, 4)
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b)
  const m = s.length >> 1
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

function fit(p: FitRequest): FitResponse {
  validate(p)
  const cells: CellFits = {}
  const byArea = new Map<string, { ids: string[]; fits: number[]; weekly: number[] }>()
  const perCell = D.cells.map(([id, area, pop], ci) => {
    const tt = typeTimes(ci, p)
    const r = fitOf(tt)
    cells[id] = [r.fit, r.weekly, pop]
    if (pop && r.fit != null) {
      const a = byArea.get(area) ?? { ids: [], fits: [], weekly: [] }
      a.ids.push(id)
      a.fits.push(r.fit)
      a.weekly.push(r.weekly ?? 0)
      byArea.set(area, a)
    }
    return tt
  })
  const areas: Area[] = [...byArea.entries()].map(([area_id, a]) => {
    let bi = 0
    a.fits.forEach((f, i) => (f > a.fits[bi] ? (bi = i) : null))
    const best = a.ids[bi]
    return {
      area_id,
      name: areaName.get(area_id) ?? area_id,
      fit: Math.round(median(a.fits)),
      best_cell_id: best,
      best_cell_fit: a.fits[bi],
      weekly_min: Math.round(median(a.weekly)),
      reasons: reasonsOf(perCell[cellIndex.get(best)!]),
    }
  })
  areas.sort((x, y) => y.fit - x.fit || y.best_cell_fit - x.best_cell_fit)
  return { run_id: (D.meta as { run_id: string }).run_id, areas, cells }
}

function cell(id: string, p: FitRequest): CellDetail {
  validate(p)
  const ci = cellIndex.get(id)
  if (ci == null) throw new ApiError(404, `cell ${id} not found`)
  const [, area, pop] = D.cells[ci]
  const rows = D.times[ci]
  const trips: Trip[] = []
  const types = Object.entries(p.destinations).filter(([, v]) => v.importance > 0).map(([t]) => t)
  for (const type of types) {
    const w = keyInfo(type)!.trip_window
    const targets = type === 'campus_site' ? campusWeights(p).map(([s]) => `campus_site/${s}`) : targetsOf(type, p)
    const seen = new Set<number>()
    for (const target of targets) {
      const row = rows[targetIndex.get(target)!]
      if (seen.has(row[0])) continue // two chosen labels, same supermarket
      seen.add(row[0])
      const dest = D.destinations[row[0]]
      for (const mode of ['walk', 'bike', 'transit'] as Mode[]) {
        const s = row[MODE_COL[mode]]
        const t: Trip = { destination_type: type, destination_id: dest.id, name: dest.name, mode, trip_window: w, minutes: s >= 0 ? Math.round(s / 60) : null }
        if (mode === 'transit') {
          const walkOnly = row[9] < 0
          t.legs = {
            access_min: walkOnly ? 0 : Math.round(row[4] / 60),
            wait_min: walkOnly ? 0 : Math.round(row[5] / 60),
            in_vehicle_min: walkOnly ? 0 : Math.round(row[6] / 60),
            egress_min: walkOnly ? 0 : Math.round(row[7] / 60),
            transfers: row[8],
            first_stop: walkOnly ? null : D.stops[row[9]],
            first_route: walkOnly ? null : D.routes[row[10]],
            walk_only: walkOnly,
            last_departure: w === 'night_return' && !walkOnly ? D.last_night[row[10]] : null,
          }
        }
        trips.push(t)
      }
    }
  }
  const tt = typeTimes(ci, p)
  const r = fitOf(tt)
  return {
    cell_id: id,
    district: areaName.get(area) ?? null,
    point: cellCentre(id)!,
    trips,
    fit: r.fit,
    reasons: reasonsOf(tt),
    weekly_min: r.weekly,
    fit_parts: r.parts,
    populated: pop === 1,
  }
}

const norm = (s: string) =>
  s.toLowerCase().normalize('NFC').replace(/straße/g, 'str').replace(/strasse/g, 'str').replace(/str\./g, 'str').replace(/[^a-z0-9äöüß]+/g, ' ').trim()

function search(q: string): AddressHit[] {
  if (typeof q !== 'string' || q.trim().length < 3) throw new ApiError(422, 'q: at least 3 characters')
  const words = norm(q).split(' ')
  return D.addresses.filter((a) => words.every((w) => norm(a.label).includes(w))).slice(0, 10)
}

/** Latency of the sample API, so loading states are visible as with a real server. */
const DELAY_MS = 120

/** A JSON response for a method + path, or an ApiError (also used by Playwright). */
export function handle(method: string, path: string, body?: unknown): unknown {
  const p = body as FitRequest
  if (method === 'GET') {
    switch (path) {
      case '/meta': return D.meta
      case '/destination-types': return D.destination_types
      case '/campus-sites': return D.campus_sites
      case '/programmes': return D.programmes
      case '/personas': return D.personas
      case '/label-destinations':
        return D.destinations
          .filter((d) => d.labels.length)
          .map((d) => ({ destination_id: d.id, destination_type: d.type, labels: d.labels, name: d.name, point: d.point }))
      case '/health': return { status: 'ok', version: '0.0.0', build_sha: 'fixtures' }
    }
  }
  if (method === 'POST') {
    if (path === '/fit') return fit(p)
    if (path === '/addresses/search') return search((body as { q: string }).q)
    const m = /^\/cell\/([^/]+)$/.exec(path)
    if (m) return cell(decodeURIComponent(m[1]), p)
  }
  throw new ApiError(404, `${method} ${path}: not found`)
}

export const fixtureTransport: Transport = (method, path, body, signal) =>
  new Promise((resolve, reject) => {
    const t = setTimeout(() => {
      try {
        resolve(structuredClone(handle(method, path, body)))
      } catch (e) {
        reject(e)
      }
    }, DELAY_MS)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })
