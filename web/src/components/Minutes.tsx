import type { Mode } from '../api/types'
import { useRefs } from '../remote/refs'
import { useI18n } from '../i18n/i18n'

/** Small mode icons (inline SVG, no icon font or third-party assets). */
export function ModeIcon({ mode, title }: { mode: Mode; title?: string }) {
  const { t } = useI18n()
  const label = title ?? t(`mode.${mode}`)
  const paths: Record<Mode, string> = {
    walk: 'M13 4a2 2 0 1 1-4 0 2 2 0 0 1 4 0ZM10 8l-3 3 1.5 1.5L10 11v4l-2 6h2.2l1.8-5 2 2v3h2v-4l-2.5-2.5.7-3.2L16 13h3v-2h-2.2l-2-3.2A2 2 0 0 0 13 7h-1.5Z',
    bike: 'M5 18a3 3 0 1 1 0-6 3 3 0 0 1 0 6Zm14 0a3 3 0 1 1 0-6 3 3 0 0 1 0 6ZM5 16.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Zm14 0a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM12 15l-2-4 3-2 2 3h3v1.5h-3.8L13 11.3l-1 .7 1.5 3Zm3-8.5a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3Z',
    transit: 'M6 4h12a2 2 0 0 1 2 2v10a2 2 0 0 1-1 1.7V20h-2.5v-2h-9v2H5v-2.3A2 2 0 0 1 4 16V6a2 2 0 0 1 2-2Zm0 2v5h12V6Zm1.5 7.5a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4Zm9 0a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4Z',
    bike_transit: 'M6 4h12a2 2 0 0 1 2 2v7H4V6a2 2 0 0 1 2-2Zm0 2v5h12V6ZM6 20a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5Zm12 0a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5Z',
  }
  return (
    <svg className="mode-icon" viewBox="0 0 24 24" width="16" height="16" role="img" aria-label={label}>
      <title>{label}</title>
      <path d={paths[mode]} fill="currentColor" />
    </svg>
  )
}

/** "Tue, arrive by 8:10" for a trip window key. */
export function TripWindowText({ window: key }: { window: string }) {
  const { t } = useI18n()
  const refs = useRefs()
  const w = refs.kind === 'ok' ? refs.refs.meta.trip_windows.find((x) => x.trip_window === key) : null
  if (!w) return <>{key}</>
  const day = t(`window.weekday.${w.weekday}` as 'window.weekday.monday')
  const time = w.time.replace(/^0/, '')
  const k = w.direction === 'back' ? 'window.back' : w.kind === 'arrive_by' ? 'window.arrive_by' : 'window.depart_at'
  return <>{t(k, { day, time })}</>
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
