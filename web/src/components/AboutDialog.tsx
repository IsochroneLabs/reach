import { useEffect, useRef, useState } from 'react'

import type { Health } from '../api/types'
import { API_BASE, BUILD_SHA, USE_FIXTURES } from '../config'
import { useRefs } from '../remote/refs'
import { fetchHealth, type ApiState } from '../health'
import { useI18n } from '../i18n/i18n'
import { storage } from '../state/storage'
import { TripWindowText } from './Minutes'

function apiText(state: ApiState, t: ReturnType<typeof useI18n>['t']): string {
  switch (state.kind) {
    case 'none':
      return t('api.none')
    case 'loading':
      return t('api.loading')
    case 'ok':
      return t('api.ok', { status: state.health.status, sha: (state.health as Health).build_sha })
    case 'error':
      return t('api.error', { message: state.message })
  }
}

/**
 * "About these numbers": data dates, trip windows, the fit in one paragraph, privacy, build SHA and
 * API status. Its content stays in the DOM while closed, so the deploy smoke test can read the
 * build SHA and the API state (tests/smoke.spec.ts).
 */
export function AboutDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, date } = useI18n()
  const refs = useRefs()
  const ref = useRef<HTMLDialogElement>(null)
  const [api, setApi] = useState<ApiState>(API_BASE ? { kind: 'loading' } : { kind: 'none' })

  useEffect(() => {
    if (!API_BASE) return
    const ctrl = new AbortController()
    fetchHealth(API_BASE, ctrl.signal).then(setApi)
    return () => ctrl.abort()
  }, [])

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  const meta = refs.kind === 'ok' ? refs.refs.meta : null
  const src = (s: 'osm' | 'gtfs' | 'zensus') => meta?.sources.find((x) => x.source === s)

  return (
    <dialog ref={ref} className="about" aria-labelledby="about-title" onClose={onClose} onCancel={onClose}>
      <div className="about-head">
        <h2 id="about-title">{t('about.title')}</h2>
        <button type="button" className="btn-icon" aria-label={t('about.close')} onClick={onClose}>
          ×
        </button>
      </div>
      {USE_FIXTURES && <p className="note note-sample">{t('data.demo.explain')}</p>}
      <p>{t('about.fit')}</p>
      <h3>{t('about.windows')}</h3>
      <ul className="plain">
        {meta?.trip_windows.map((w) => (
          <li key={w.trip_window}>
            <TripWindowText window={w.trip_window} /> · {t('window.reference', { date: date(w.reference_date) })}
          </li>
        ))}
      </ul>
      <h3>{t('about.sources')}</h3>
      <ul className="plain">
        {src('osm') && <li>{t('source.osm', { date: date(src('osm')!.date) })}</li>}
        {src('gtfs') && (
          <li>{t('source.gtfs', { date: date(src('gtfs')!.date), validTo: date(src('gtfs')!.valid_to ?? src('gtfs')!.date) })}</li>
        )}
        <li>{t('source.zensus')}</li>
      </ul>
      <p className="muted">{t('about.privacy')}</p>
      {storage.blocked && <p className="muted">{t('about.storageBlocked')}</p>}
      <dl className="about-tech">
        <dt>{t('about.build')}</dt>
        <dd data-testid="build-sha">{BUILD_SHA}</dd>
        <dt>{t('about.api')}</dt>
        <dd data-testid="api-status" data-state={api.kind}>
          {apiText(api, t)}
        </dd>
      </dl>
      <p className="muted small">
        {t('footer.course')} · <a href="https://github.com/IsochroneLabs/reach">{t('footer.source')}</a>
      </p>
    </dialog>
  )
}
