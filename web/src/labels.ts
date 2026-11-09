import { TRANSIT } from './palette'
import type { Meta, Profile } from './types'

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

/** Short explanations behind the "What does this show?" toggles of the sidebar cards. */
export const CARD_HELP = {
  map: 'Each square is a 100 m cell of the Zensus 2022 grid. Its colour says how many facilities of the chosen category its residents reach within the time budget, routed along real paths from the cell centre. "Enough" means at least the number needed for that category.',
  inspector:
    'Everything reachable from the centre of the clicked cell, per category: how many facilities, how far the nearest one is, and the route to it. The rings show where you get in a few minutes up to the budget; they are for orientation only, counts come from the routing matrix.',
  recommendations:
    'The best 100 m zones for one new facility of the chosen category: placing it there removes the largest shortfall of residents, counted along real paths. Click a zone to see who would reach it.',
  district:
    'Share of residents per class in one district, the residents with no facility within the budget, and the shortfall ("deficit") used to rank districts: rank 1 is the district with the largest shortfall.',
} as const
