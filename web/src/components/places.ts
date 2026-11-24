import type { useI18n } from '../i18n/i18n'
import { cityRank } from '../logic/rank'
import { useFit } from '../remote/fit'
import type { Place } from '../state/profile'

/** Display name of a place: its label, or "Place A (Dropped pin)". */
export function placeName(p: Place, t: ReturnType<typeof useI18n>['t']): string {
  return p.label ?? `${t('check.place', { id: p.id })} (${t('check.pin')})`
}

/** Rank in the city of a fit, from the cell fits of the current fit response. */
export function useRank(fit: number | null | undefined): number | null {
  const f = useFit()
  if (!f.data || fit == null) return null
  return cityRank(f.data.cells, fit)
}
