import { useFit } from '../remote/fit'
import { useI18n } from '../i18n/i18n'

/** Find results (S2.2: names and fits only; cards with reasons follow in S2.4). */
export function FindResults() {
  const { t } = useI18n()
  const fit = useFit()
  return (
    <section className="results" aria-labelledby="find-title" aria-busy={fit.updating}>
      <h2 id="find-title">{t('find.results')}</h2>
      {fit.noWeight && <p className="note note-sample">{t('find.noneImportant')}</p>}
      {!fit.data && !fit.noWeight && <p className="muted">{t('status.loading')}</p>}
      <ol>
        {fit.data?.areas.slice(0, 3).map((a) => (
          <li key={a.area_id} data-testid="area">
            {a.name} · {a.fit}
          </li>
        ))}
      </ol>
    </section>
  )
}
