import { useI18n } from '../i18n/i18n'
import { useCellDetails } from '../remote/cells'
import { MAX_PLACES } from '../settings'
import { PLACE_IDS } from '../state/profile'
import { useStore } from '../state/store'
import { PlaceCard } from './PlaceCard'

/** Check: one card per place (S2.5); side by side from two places (S2.6). */
export function CheckResults() {
  const { t } = useI18n()
  const { state } = useStore()
  const cells = useCellDetails(state.places, state.profile)
  return (
    <section className="results" aria-labelledby="check-title">
      <h2 id="check-title">{t('check.title')}</h2>
      {!state.places.length && <p className="empty">{t('check.empty')}</p>}
      {state.places.map((p) => (
        <PlaceCard key={p.id} place={p} cell={cells[p.id]} />
      ))}
      {state.places.length > 0 && state.places.length < MAX_PLACES && (
        <p className="muted small add-hint">{t('check.add.hint', { id: PLACE_IDS[state.places.length] })}</p>
      )}
    </section>
  )
}
