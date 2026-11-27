import type { ReactNode } from 'react'

import type { CellDetail } from '../api/types'
import { useI18n } from '../i18n/i18n'
import { compareTwo, type Fact, type PlaceFacts } from '../logic/compare'
import { cityRank } from '../logic/rank'
import type { CellState } from '../remote/cells'
import { useFit } from '../remote/fit'
import { useDestName } from '../remote/refs'
import { FIT_EQUAL_DELTA } from '../settings'
import type { Place } from '../state/profile'
import { useStore } from '../state/store'
import { FitBadge } from './FindResults'
import { ModeIcon } from './Minutes'
import { placeName } from './places'
import { useToast } from './Toast'

function factText(f: Fact, t: ReturnType<typeof useI18n>['t'], duration: (m: number) => string): string {
  switch (f.kind) {
    case 'fitBetter':
      return t('compare.fitBetter', { a: f.a, fa: f.fa, fb: f.fb })
    case 'fitEqual':
      return t('compare.fitEqual', { a: f.a, b: f.b })
    case 'cheaper':
      return t('compare.cheaper', { a: f.a, eur: f.eur })
    case 'destDiff':
      return t('compare.destDiff', { a: f.a, dest: f.dest, time: duration(f.min) })
  }
}

/** Two or three places side by side, the differences in plain language, a shareable link (§1.4). */
export function CompareView({ places, cells }: { places: Place[]; cells: Record<string, CellState> }) {
  const { t, duration } = useI18n()
  const fit = useFit()
  const { state, dispatch } = useStore()
  const toast = useToast()

  const detail = (p: Place): CellDetail | null => {
    const c = cells[p.id]
    return c?.kind === 'ok' ? c.detail : null
  }
  const typeLabel = useDestName()
  const short = (p: Place) => `${p.id} · ${placeName(p, t).replace(/, Tübingen$/, '')}`

  const facts: PlaceFacts[] = places.map((p) => {
    const d = detail(p)
    return {
      id: p.id,
      name: short(p),
      fit: d?.fit ?? null,
      rentEur: p.rentEur,
      minutes: Object.fromEntries((d?.fit_parts ?? []).map((x) => [typeLabel(x.destination_type), x.minutes])),
    }
  })
  const ready = places.every((p) => detail(p))
  const ranked = [...facts].sort((a, b) => (b.fit ?? -1) - (a.fit ?? -1))
  const lines = ready
    ? ranked.slice(1).flatMap((other, i) => compareTwo(ranked[0], other, FIT_EQUAL_DELTA).slice(0, i === 0 ? 4 : 2))
    : []

  const best = <T,>(vals: (T | null)[], better: (a: T, b: T) => boolean) => {
    let bi = -1
    vals.forEach((v, i) => {
      if (v != null && (bi < 0 || better(v, vals[bi] as T))) bi = i
    })
    return bi
  }
  const fits = places.map((p) => detail(p)?.fit ?? null)
  const bestFit = best(fits, (a, b) => a > b)
  const types = [...new Set(places.flatMap((p) => (detail(p)?.fit_parts ?? []).map((x) => x.destination_type)))]

  const row = (title: string, cellsOf: (p: Place, i: number) => ReactNode, key: string) => (
    <tr key={key}>
      <th scope="row">{title}</th>
      {places.map((p, i) => (
        <td key={p.id}>{cellsOf(p, i)}</td>
      ))}
    </tr>
  )
  const star = <span className="star" aria-label={t('compare.best')}>★</span>

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      toast(t('compare.copied'))
    } catch {
      toast(t('compare.copyFailed'))
    }
  }

  return (
    <section className="compare card" aria-labelledby="compare-title" data-testid="compare">
      <h3 id="compare-title">{t('compare.title')}</h3>
      <div className="in-short">
        <h4>{t('compare.inShort')}</h4>
        {!ready && <p className="muted">{t('status.loading')}</p>}
        <ul data-testid="in-short">
          {lines.map((f, i) => (
            <li key={i}>{factText(f, t, duration)}</li>
          ))}
        </ul>
      </div>
      <div className="compare-scroll">
        <table className="compare-table">
          <thead>
            <tr>
              <td />
              {places.map((p) => (
                <th key={p.id} scope="col">
                  <span className="place-id" aria-hidden="true">{p.id}</span> {placeName(p, t).replace(/, Tübingen$/, '')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {row(t('compare.row.fit'), (_, i) => (
              <>
                <FitBadge fit={fits[i]} size="s" /> {i === bestFit && star}
              </>
            ), 'fit')}
            {row(t('compare.row.rank'), (_, i) => {
              const r = fit.data && fits[i] != null ? cityRank(fit.data.cells, fits[i]) : null
              return r == null ? '–' : t('compare.rankTop', { pct: Math.max(1, 100 - r) })
            }, 'rank')}
            {row(t('compare.row.rent'), (p) => (p.rentEur == null ? t('rent.none') : t('rent.value', { eur: p.rentEur })), 'rent')}
            {types.map((ty) => {
              const parts = places.map((p) => detail(p)?.fit_parts?.find((x) => x.destination_type === ty) ?? null)
              const bi = best(parts.map((x) => x?.minutes ?? null), (a, b) => a < b)
              return row(typeLabel(ty), (_, i) => {
                const x = parts[i]
                if (!x) return '–'
                return (
                  <span className="minutes">
                    {x.mode && <ModeIcon mode={x.mode} />}
                    <span className="minutes-value">{x.minutes == null ? t('trips.unreachable') : duration(x.minutes)}</span>
                    {i === bi && star}
                  </span>
                )
              }, ty)
            })}
          </tbody>
        </table>
      </div>
      <div className="share-row">
        <button type="button" className="btn btn-small" onClick={copy}>
          {t('compare.share')}
        </button>
        <label className="check">
          <input
            type="checkbox"
            checked={state.shareRents}
            onChange={(e) => dispatch({ type: 'shareRents', on: e.target.checked })}
          />
          {t('compare.shareRents')}
        </label>
      </div>
    </section>
  )
}
