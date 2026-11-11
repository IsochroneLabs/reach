// Flexible accessibility score (methodology §4b), computed in the browser from the sorted
// times of `GET /api/cells/times`, so the sliders need no request. With the defaults and one
// category it equals 100 · (1 − deficit / population) of `/api/cells`.
import { SCORE_CLASSES } from './palette'
import type { Category, CellTimes, Cells } from './types'

/** Per-category overrides; a missing field means "default". */
export interface CategoryParams {
  /** Time threshold in minutes (at most the facility budget). */
  t?: number
  /** Facilities needed. */
  k?: number
  /** Weight (≥ 0). */
  w?: number
}

export interface ScoreParams {
  /** Global time threshold in minutes, null = the facility budget. */
  t: number | null
  cats: Record<string, CategoryParams>
}

export const DEFAULT_PARAMS: ScoreParams = { t: null, cats: {} }

export interface Effective {
  t: number
  k: number
  w: number
}

/** Facilities per category the API delivers times for (config `api.score`, default); the
 * facilities needed cannot exceed it, or the score could never reach 100. */
export const DEFAULT_MAX_K = 5

/** The values used for one category: its override, else the global threshold, else the default.
 * `k` is kept between 1 and `maxK`. */
export function effective(params: ScoreParams, cat: Category, budgetMin: number, maxK = DEFAULT_MAX_K): Effective {
  const o = params.cats[cat.id] ?? {}
  const k = Math.round(o.k ?? cat.k)
  return { t: Math.min(budgetMin, o.t ?? params.t ?? budgetMin), k: Math.min(maxK, Math.max(1, k)), w: o.w ?? 1 }
}

/** True if the selected categories use exactly the default settings (threshold = budget,
 * `k` from the config, weight 1): then one category is the plain class map. Values of categories
 * that are not selected, or equal to the default, do not count. */
export function isEffectiveDefault(p: ScoreParams, selected: Category[], budgetMin: number, maxK = DEFAULT_MAX_K): boolean {
  return selected.every((c) => {
    const e = effective(p, c, budgetMin, maxK)
    return e.t === budgetMin && e.k === Math.min(maxK, Math.max(1, c.k)) && e.w === 1
  })
}

export function isDefault(p: ScoreParams): boolean {
  return p.t === null && Object.values(p.cats).every((o) => o.t === undefined && o.k === undefined && o.w === undefined)
}

/** `t=10;grocery.k=1;grocery.t=8;pharmacy.w=2` for the URL hash; null for the defaults. */
export function encodeParams(p: ScoreParams): string | null {
  const parts: string[] = []
  if (p.t !== null) parts.push(`t=${p.t}`)
  for (const [id, o] of Object.entries(p.cats).sort(([a], [b]) => a.localeCompare(b)))
    for (const f of ['t', 'k', 'w'] as const) if (o[f] !== undefined) parts.push(`${id}.${f}=${o[f]}`)
  return parts.length ? parts.join(';') : null
}

/** Inverse of `encodeParams`; anything malformed is ignored (a shared link must not break). */
export function decodeParams(s: string | null): ScoreParams {
  const out: ScoreParams = { t: null, cats: {} }
  for (const part of (s ?? '').split(';')) {
    const [key, raw] = part.split('=')
    const value = Number(raw)
    if (!key || raw === undefined || raw === '' || !Number.isFinite(value) || value < 0) continue
    if (key === 't') out.t = value
    else {
      const [id, field] = key.split('.')
      // category ids only (no `__proto__` and the like)
      if (/^[a-z][a-z0-9_]*$/.test(id) && (field === 't' || field === 'k' || field === 'w'))
        out.cats[id] = { ...out.cats[id], [field]: value }
    }
  }
  return out
}

/** Share (0–1) of the need met: facilities within `t` minutes over the `k` needed, at most 1. */
export function coverage(times: number[] | undefined, e: Effective): number {
  if (e.k <= 0) return 1
  const within = (times ?? []).filter((s) => s <= e.t * 60).length
  return Math.min(1, within / e.k)
}

/** Weighted mean coverage × 100 over the selected categories; null if all weights are 0. */
export function scoreOf(times: Record<string, number[]>, selected: [string, Effective][]): number | null {
  let sum = 0
  let weights = 0
  for (const [id, e] of selected) {
    sum += e.w * coverage(times[id], e)
    weights += e.w
  }
  return weights > 0 ? (100 * sum) / weights : null
}

export const binOf = (score: number) => Math.min(SCORE_CLASSES.length - 1, Math.floor(score / 20))

/** The cells of the map with `score`, `class` (bin `s0`…`s4`) and `full` filled in (geometry and
 * residents come from `/api/cells`, times from `/api/cells/times`). Cells without times data are
 * dropped. */
export function scoreCells(
  cells: Cells,
  times: CellTimes,
  categories: Category[],
  params: ScoreParams,
  budgetMin: number,
): Cells {
  const maxK = times.max_times_per_category
  const eff: [string, Effective][] = categories.map((c) => [c.id, effective(params, c, budgetMin, maxK)])
  const byCell = new Map(times.cells.map((c) => [c.cell_id, c.times]))
  const features = cells.features.flatMap((f) => {
    const t = byCell.get(f.properties.cell_id)
    const raw = t ? scoreOf(t, eff) : null
    if (raw === null) return []
    // rounded, so a sum like 59.999999999 does not fall into the lower bin or miss the outline
    const score = Math.round(raw * 1e6) / 1e6
    return [{ ...f, properties: { ...f.properties, score, class: SCORE_CLASSES[binOf(score)], full: score >= 100 } }]
  })
  return { ...cells, features }
}

export interface ScoreSummary {
  /** Residents per bin `s0`…`s4`. */
  residents: number[]
  total: number
  /** Share (0–1) of residents whose score is 100: everything selected is within reach. */
  fullShare: number
}

export function summarise(cells: Cells | null): ScoreSummary {
  const residents = SCORE_CLASSES.map(() => 0)
  let total = 0
  let full = 0
  for (const f of cells?.features ?? []) {
    const p = f.properties
    residents[binOf(p.score ?? 0)] += p.population
    total += p.population
    if (p.full) full += p.population
  }
  return { residents, total, fullShare: total > 0 ? full / total : 0 }
}

/** Population-weighted mean score of one district, null without scored residents. */
export function districtMean(cells: Cells | null, districtId: string): number | null {
  let sum = 0
  let total = 0
  for (const f of cells?.features ?? []) {
    if (f.properties.district_id !== districtId) continue
    sum += (f.properties.score ?? 0) * f.properties.population
    total += f.properties.population
  }
  return total > 0 ? sum / total : null
}
