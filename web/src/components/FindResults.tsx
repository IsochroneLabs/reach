import type { Area } from '../api/types'
import { cellCentre } from '../geo/laea'
import { useI18n } from '../i18n/i18n'
import { useFit } from '../remote/fit'
import { MAX_PLACES, NEARBY_RADIUS_M } from '../settings'
import { nearbyCells } from '../logic/nearby'
import { useStore } from '../state/store'
import { DataNote } from './DataNote'
import { Reasons } from './Reasons'
import { useToast } from './Toast'

/** The fit as a number in mono, tabular (docs/design.md §6 "big number"); never a coloured badge. */
export function FitBadge({ fit, size = 'm' }: { fit: number | null; size?: 's' | 'm' | 'l' }) {
  return <span className={`fit-num fit-${size}`}>{fit ?? '–'}</span>
}

function AreaCard({ area, rank }: { area: Area; rank: number }) {
  const { t, duration } = useI18n()
  const { state, dispatch } = useStore()
  const toast = useToast()
  const check = () => {
    if (state.places.length >= MAX_PLACES) {
      toast(t('check.max'))
      return
    }
    const point = cellCentre(area.best_cell_id)
    if (!point) return
    dispatch({ type: 'addPlace', place: { point, cellId: area.best_cell_id, label: area.name } })
  }
  return (
    <li className="card area-card" data-testid="area">
      <div className="area-head">
        <span className="area-rank" aria-hidden="true">{String(rank).padStart(2, '0')}</span>
        <h3 className="area-name">
          <span className="visually-hidden">{rank}. </span>
          {area.name}
        </h3>
        <span title={t('find.area.fit')}>
          <span className="visually-hidden">{t('find.area.fit')}: </span>
          <FitBadge fit={area.fit} />
        </span>
      </div>
      <Reasons reasons={area.reasons} />
      <div className="area-foot">
        <span className="muted small">{t('weekly.short', { time: duration(area.weekly_min) })}</span>
        <button type="button" className="btn btn-small" onClick={check} aria-label={t('find.area.checkLabel', { name: area.name })}>
          {t('find.area.check')} →
        </button>
      </div>
    </li>
  )
}

/** Find: the three best areas with 2–4 reasons each (docs/app_screens.md §1.1). */
function NearbyNote() {
  const { t, num } = useI18n()
  const { state, dispatch } = useStore()
  const fit = useFit()
  const place = state.places.find((p) => p.id === state.nearbyOf)
  if (!place || !fit.data) return null
  const n = nearbyCells(state, fit.data.cells).length
  const vars = { n, km: num(NEARBY_RADIUS_M / 1000, 1), place: place.label ?? t('check.place', { id: place.id }) }
  return (
    <div className="note nearby" role="status" data-testid="nearby-note">
      <strong>{t('find.nearby', { place: vars.place })}</strong>
      <p>{n ? t('find.nearby.count', vars) : t('find.nearby.none', vars)}</p>
      <button type="button" className="btn-link small" onClick={() => dispatch({ type: 'nearby', id: null })}>
        {t('find.nearby.clear')}
      </button>
    </div>
  )
}

export function FindResults() {
  const { t } = useI18n()
  const fit = useFit()
  return (
    <section className="results" aria-labelledby="find-title" aria-busy={fit.updating}>
      <h2 id="find-title">{t('find.results')}</h2>
      <NearbyNote />
      {fit.noWeight && <p className="note note-sample">{t('find.noneImportant')}</p>}
      {!fit.noWeight && !fit.data && !fit.error && (
        <ol className="plain">
          {[1, 2, 3].map((i) => (
            <li key={i} className="card skeleton" aria-hidden="true" />
          ))}
          <li className="visually-hidden">{t('status.loading')}</li>
        </ol>
      )}
      {!fit.noWeight && fit.data && (
        <ol className={`plain areas${fit.updating ? ' dim' : ''}`}>
          {fit.data.areas.slice(0, 3).map((a, i) => (
            <AreaCard key={a.area_id} area={a} rank={i + 1} />
          ))}
        </ol>
      )}
      <DataNote />
    </section>
  )
}
