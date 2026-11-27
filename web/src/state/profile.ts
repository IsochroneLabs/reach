import type { DestinationType, FitRequest, Importance, Mode, Programme } from '../api/types'
import { groceryLabels, resolveKey } from './labels.ts'

/** The student profile is exactly the body of POST /api/fit (docs/app_screens.md §3.1). */
export type StudentProfile = FitRequest & { programme: string | null }

export type PlaceId = 'A' | 'B' | 'C'
export const PLACE_IDS: PlaceId[] = ['A', 'B', 'C']

export interface Place {
  id: PlaceId
  point: [number, number]
  cellId: string
  /** address label, a name the student typed, or null for a pin */
  label: string | null
  /** listing rent per month in euros; browser only, never sent to the API */
  rentEur: number | null
}

export const ALL_MODES: Mode[] = ['walk', 'bike', 'transit', 'bike_transit']

/** Default profile (docs/product.md): no programme, all modes, campus very important. */
export function defaultProfile(modes: Mode[] = ['walk', 'bike', 'transit']): StudentProfile {
  return {
    programme: null,
    modes: [...modes],
    destinations: {
      campus_site: { importance: 3 },
      mensa: { importance: 2 },
      grocery: { importance: 2 },
      main_station: { importance: 2 },
    },
  }
}

/**
 * Stable form: drops values equal to the type default (categories: no trips per week), sorts keys
 * and favourite supermarkets. Same profile → same key.
 */
export function normalise(p: StudentProfile, types: DestinationType[]): StudentProfile {
  const destinations: StudentProfile['destinations'] = {}
  for (const k of Object.keys(p.destinations).sort()) {
    const v = p.destinations[k]
    const r = resolveKey(k, types)
    const t = r?.type
    const out: StudentProfile['destinations'][string] = { importance: v.importance }
    if (v.fine_time_min != null && v.fine_time_min !== t?.fine_time_min) out.fine_time_min = v.fine_time_min
    destinations[k] = out
  }
  const modes = ALL_MODES.filter((m) => p.modes.includes(m))
  const res: StudentProfile = { programme: p.programme, modes, destinations }
  if (p.campus_days && Object.keys(p.campus_days).length) res.campus_days = p.campus_days
  const grocery = [...new Set(p.labels?.grocery ?? [])].sort()
  if (grocery.length) res.labels = { grocery }
  return res
}

export function profileKey(p: StudentProfile, types: DestinationType[]): string {
  return JSON.stringify(normalise(p, types))
}

/** True if at least one destination counts (importance > 0). */
export function hasWeight(p: StudentProfile): boolean {
  return Object.values(p.destinations).some((d) => d.importance > 0)
}

const isImportance = (x: unknown): x is Importance => x === 0 || x === 1 || x === 2 || x === 3

/**
 * Drops what the reference lists do not know (programme, destination types, modes). Returns the
 * clean profile and whether anything was dropped (→ "invalid link" toast).
 */
export function sanitize(
  p: StudentProfile,
  refs: { types: DestinationType[]; programmes: Programme[]; modes: Mode[] },
): { profile: StudentProfile; dropped: boolean } {
  let dropped = false
  const destinations: StudentProfile['destinations'] = {}
  for (const [k, v] of Object.entries(p.destinations ?? {})) {
    if (!resolveKey(k, refs.types) || !isImportance(v?.importance)) {
      dropped = true
      continue
    }
    const out: StudentProfile['destinations'][string] = { importance: v.importance }
    if (typeof v.fine_time_min === 'number' && v.fine_time_min > 0 && v.fine_time_min <= 120) out.fine_time_min = v.fine_time_min
    else if (v.fine_time_min != null) dropped = true
    destinations[k] = out
  }
  let programme = p.programme ?? null
  if (programme && !refs.programmes.some((x) => x.programme === programme)) {
    programme = null
    dropped = true
  }
  let modes = (p.modes ?? []).filter((m) => refs.modes.includes(m))
  if (modes.length !== (p.modes ?? []).length) dropped = true
  if (!modes.length) modes = [...refs.modes]
  const profile: StudentProfile = { programme, modes, destinations }
  const known = new Set(groceryLabels(refs.types).map((l) => l.label))
  const grocery = (p.labels?.grocery ?? []).filter((l) => known.has(l))
  if (grocery.length !== (p.labels?.grocery ?? []).length) dropped = true
  if (grocery.length) profile.labels = { grocery }
  return { profile, dropped }
}
