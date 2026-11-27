import type { Mode } from '../api/types'
import { useRefs } from '../remote/refs'
import { useI18n } from '../i18n/i18n'

/** The mode as a tag ("BIKE"): micro text in an ink frame (docs/design.md §6, no icons). */
export function ModeIcon({ mode, title }: { mode: Mode; title?: string }) {
  const { t } = useI18n()
  if (title === '') return null // decorative: the text next to it names the mode
  return <span className="tag mode-tag">{title ?? t(`mode.${mode}`)}</span>
}

/** "Tue, arrive by 8:10" for a trip window key. */
/** Trip window key → "Tue, arrive by 8:10" (the key itself while the reference data load). */
// eslint-disable-next-line react-refresh/only-export-components
export function useWindowText(): (key: string) => string {
  const { t } = useI18n()
  const refs = useRefs()
  return (key: string) => {
    const w = refs.kind === 'ok' ? refs.refs.meta.trip_windows.find((x) => x.trip_window === key) : null
    if (!w) return key
    const day = t(`window.weekday.${w.weekday}` as 'window.weekday.monday')
    const time = w.time.replace(/^0/, '')
    const k = w.direction === 'back' ? 'window.back' : w.kind === 'arrive_by' ? 'window.arrive_by' : 'window.depart_at'
    return t(k, { day, time })
  }
}

export function TripWindowText({ window: key }: { window: string }) {
  const text = useWindowText()
  return <>{text(key)}</>
}

/** Every travel time on screen renders through here, so mode and trip window are never missing. */
export function Minutes({
  minutes,
  mode,
  window: w,
  showWindow = true,
}: {
  minutes: number | null
  mode: Mode | null
  window?: string
  showWindow?: boolean
}) {
  const { t, duration } = useI18n()
  return (
    <span className="minutes">
      {mode && <ModeIcon mode={mode} />}
      <span className="minutes-value">{minutes == null ? t('trips.unreachable') : duration(minutes)}</span>
      {showWindow && w && (
        <span className="minutes-window">
          {' · '}
          <TripWindowText window={w} />
        </span>
      )}
    </span>
  )
}
