import type { Reason } from '../api/types'
import { useI18n } from '../i18n/i18n'
import { useDestName } from '../remote/refs'
import { Minutes } from './Minutes'

/** Structured reasons from the API, worded in the browser (data contract: wording never in the API). */
export function Reasons({ reasons }: { reasons: Reason[] }) {
  const { t } = useI18n()
  const typeLabel = useDestName()
  return (
    <ul className="reasons">
      {reasons.map((r, i) => {
        const name = r.destination_type === 'campus_site' ? t('reason.campus') : (r.name ?? typeLabel(r.destination_type))
        if (r.kind === 'reliability') {
          return (
            <li key={i} className="reason reason-reliability">
              <span className="reason-index" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
              <span className="reason-mark" aria-hidden="true">·</span>
              <span>{t('reason.reliability.last', { time: String(r.value ?? '–') })}</span>
            </li>
          )
        }
        return (
          <li key={i} className={`reason reason-${r.kind}`}>
            <span className="reason-index" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span>
            <span className="reason-mark" aria-hidden="true">{r.kind === 'strength' ? '+' : '−'}</span>
            <span>
              <span className="visually-hidden">{r.kind === 'strength' ? 'Strength: ' : 'Weakness: '}</span>
              <span className="reason-name">{name}</span>{' '}
              <Minutes minutes={r.minutes} mode={r.mode} window={r.trip_window} />
            </span>
          </li>
        )
      })}
    </ul>
  )
}
