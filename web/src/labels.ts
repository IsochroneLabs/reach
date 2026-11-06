import { TRANSIT } from './palette'
import type { Meta, Profile } from './types'

/** `Walking · 3.39 km/h` from the profile id prefix and its speed (budget: see the legend). */
export function profileLabel(p: Profile): string {
  const mode = p.profile_id.split('_')[0]
  return `${mode.charAt(0).toUpperCase()}${mode.slice(1)} · ${p.speed_kmh} km/h`
}

export function categoryName(meta: Meta, id: string): string {
  if (id === TRANSIT) return 'Public transport'
  return meta.categories.find((c) => c.id === id)?.name ?? id
}
