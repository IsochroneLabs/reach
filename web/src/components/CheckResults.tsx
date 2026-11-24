import { useI18n } from '../i18n/i18n'
import { useStore } from '../state/store'

/** Check results (S2.2: the list of places; place cards follow in S2.5). */
export function CheckResults() {
  const { t } = useI18n()
  const { state, dispatch } = useStore()
  return (
    <section className="results" aria-labelledby="check-title">
      <h2 id="check-title">{t('check.title')}</h2>
      {!state.places.length && <p className="muted">{t('check.empty')}</p>}
      <ul className="plain">
        {state.places.map((p) => (
          <li key={p.id} data-testid="place">
            {p.id} · {p.label ?? t('check.pin')}{' '}
            <button type="button" className="btn btn-small" onClick={() => dispatch({ type: 'removePlace', id: p.id })}>
              {t('check.remove', { id: p.id })}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
