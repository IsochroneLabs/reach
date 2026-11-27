/**
 * Rank in the city and "better places nearby", computed in the browser from the cell fits of
 * POST /api/fit (docs/app_screens.md §4.4, §4.5). Pure; no imports besides types and laea.
 */
import type { CellFits } from '../api/types'
import { cellDistanceM } from '../geo/laea.ts'

/**
 * Share (0–100, rounded down) of populated cells whose fit is strictly below `fit`.
 * Null when there is no fit or no populated cell.
 */
export function cityRank(cells: CellFits, fit: number | null): number | null {
  if (fit == null) return null
  let n = 0
  let below = 0
  for (const [f, populated] of Object.values(cells)) {
    if (!populated || f == null) continue
    n++
    if (f < fit) below++
  }
  return n ? Math.floor((100 * below) / n) : null
}

/** Cells within `radiusM` of `cellId` (EPSG:3035 metres) whose fit is higher than `fit`. */
export function betterNearby(cells: CellFits, cellId: string, fit: number | null, radiusM: number): string[] {
  if (fit == null) return []
  return Object.entries(cells)
    .filter(([id, [f]]) => id !== cellId && f != null && f > fit && cellDistanceM(id, cellId) <= radiusM)
    .map(([id]) => id)
}
