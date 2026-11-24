import type { CellFits } from '../api/types'
import { NEARBY_RADIUS_M } from '../settings'
import type { AppState } from '../state/store'
import { betterNearby } from './rank'

/** Find after "Better places nearby": the cells around the chosen place that fit better. */
export function nearbyCells(state: AppState, cells: CellFits | undefined): string[] {
  if (state.mode !== 'find' || !state.nearbyOf || !cells) return []
  const place = state.places.find((p) => p.id === state.nearbyOf)
  if (!place) return []
  return betterNearby(cells, place.cellId, cells[place.cellId]?.[0] ?? null, NEARBY_RADIUS_M)
}
