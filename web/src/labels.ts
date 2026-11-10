import { TRANSIT } from './palette'
import type { CellStatus, Meta, Profile } from './types'

const modeOf = (p: Profile) => p.profile_id.split('_')[0]
const fmtSpeed = (kmh: number) => `${Number(kmh.toFixed(1))} km/h`

/** `Walking (slow, 3.4 km/h)`: mode from the profile id prefix; where one mode has several
 * profiles, the slowest is "slow" and the others "average" (the budget is in the legend). */
export function profileLabel(p: Profile, profiles: Profile[] = [p]): string {
  const mode = modeOf(p)
  const name = `${mode.charAt(0).toUpperCase()}${mode.slice(1)}`
  const same = profiles.filter((o) => modeOf(o) === mode)
  if (same.length < 2) return `${name} (${fmtSpeed(p.speed_kmh)})`
  const slowest = Math.min(...same.map((o) => o.speed_kmh))
  return `${name} (${p.speed_kmh === slowest ? 'slow' : 'average'}, ${fmtSpeed(p.speed_kmh)})`
}

export function categoryName(meta: Meta, id: string): string {
  if (id === TRANSIT) return 'Public transport'
  return meta.categories.find((c) => c.id === id)?.name ?? id
}

/** Plain-language name of a class next to the technical one (legend, inspector). */
export function classPlain(cls: string, budgetMin: number | null, transit = false): string {
  if (transit)
    return (
      { lack: 'No departures nearby', insufficient: 'Few departures', medium: 'Some departures', high: 'Many departures' }[
        cls
      ] ?? cls
    )
  if (cls === 'lack') return budgetMin === null ? 'None within reach' : `None within ${budgetMin} min`
  return { insufficient: 'Fewer than needed', sufficient: 'Enough' }[cls] ?? cls
}

/** Inspector line for a cell that is not in the published run (W3); scored cells show their
 * residents instead. */
export const CELL_STATUS_TEXT: Record<Exclude<CellStatus, 'scored'>, string> = {
  unpopulated: 'No residents in the Zensus 2022 grid — values computed live',
  outside_city: 'Outside the city boundary — not scored',
}

/** "7 min", or "23 min · beyond 15 min" for a time over the budget (route labels, popups). */
export function timeLabel(minutes: number, budgetMin: number | null, beyond: boolean): string {
  // beyond the budget: round up, so "15 min · beyond 15 min" cannot occur
  const label = `${beyond ? Math.ceil(minutes) : Math.round(minutes)} min`
  return beyond && budgetMin !== null ? `${label} · beyond ${budgetMin} min` : label
}

/** Short explanations behind the "What does this show?" toggles of the sidebar cards. */
export const CARD_HELP = {
  map: 'Each square is a 100 m cell of the Zensus 2022 grid. Its colour says how many facilities of the chosen category its residents reach within the time budget, routed along real paths from the cell centre. "Enough" means at least the number needed for that category.',
  inspector:
    'Everything reachable from the centre of the clicked cell, per category: how many facilities, how far the nearest one is, and the route to it. The rings show where you get in a few minutes up to the budget; they are for orientation only, counts come from the routing matrix.',
  recommendations:
    'The best 100 m zones for one new facility of the chosen category: placing it there removes the largest shortfall of residents, counted along real paths. Click a zone to see who would reach it.',
  score:
    'The score of a cell is 100 when everything selected is within reach: for every category, facilities within the chosen time over the number needed (at most 1), averaged with the weights. 0 means nothing selected is within reach. Moving a slider recomputes the map in your browser; a link keeps your settings.',
  housing:
    'Where would new homes already have good access? Cells of the Zensus 2022 grid without residents, inside the built-up area and its edge, are scored like the residents\' cells with the settings of the score card. Accessibility only: ownership, zoning, noise and flood risk are not considered.',
  district:
    'Share of residents per class in one district, the residents with no facility within the budget, and the shortfall ("deficit") used to rank districts: rank 1 is the district with the largest shortfall.',
} as const
