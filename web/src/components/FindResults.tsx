import type { Area } from '../api/types'
import { cellCentre } from '../geo/laea'
import { useI18n } from '../i18n/i18n'
import { useFit } from '../remote/fit'
import { MAX_PLACES } from '../settings'
import { useStore } from '../state/store'
import { DataNote } from './DataNote'
import { Reasons } from './Reasons'
import { useToast } from './Toast'

export function FitBadge({ fit, size = 'm' }: { fit: number | null; size?: 's' | 'm' | 'l' }) {
  const bucket = fit == null ? 'none' : Math.min(6, Math.floor(fit / 16.7))
  return (
    <span className={`fit-badge fit-${size}`} data-bucket={bucket}>
      {fit ?? '–'}
    </span>
  )
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
        <span className="area-rank" aria-hidden="true">{rank}</span>
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
export function FindResults() {
  const { t } = useI18n()
  const fit = useFit()
  return (
    <section className="results" aria-labelledby="find-title" aria-busy={fit.updating}>
      <h2 id="find-title">{t('find.results')}</h2>
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
