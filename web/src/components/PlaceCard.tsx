import { useId, useState } from 'react'

import type { CellDetail, Mode, Trip } from '../api/types'
import { useI18n } from '../i18n/i18n'
import { placeName, useRank } from './places'
import type { CellState } from '../remote/cells'
import { useRefs } from '../remote/refs'
import type { Place } from '../state/profile'
import { useStore } from '../state/store'
import { DataNote } from './DataNote'
import { FitBadge } from './FindResults'
import { ModeIcon, TripWindowText } from './Minutes'
import { Reasons } from './Reasons'

export function RankText({ rank }: { rank: number | null }) {
  const { t } = useI18n()
  if (rank == null) return null
  return <>{rank >= 95 ? t('rank.top') : t('rank.better', { pct: rank })}</>
}

export function RentInput({ place }: { place: Place }) {
  const { t } = useI18n()
  const { dispatch } = useStore()
  const id = useId()
  return (
    <div className="rent">
      <label htmlFor={id}>{t('rent.label')}</label>
      <div className="rent-input">
        <span aria-hidden="true">€</span>
        <input
          id={id}
          type="number"
          inputMode="numeric"
          min={0}
          max={5000}
          step={10}
          value={place.rentEur ?? ''}
          aria-describedby={`${id}-hint`}
          onChange={(e) => {
            const v = e.target.value === '' ? null : Number(e.target.value)
            if (v === null || (Number.isFinite(v) && v >= 0 && v <= 5000)) {
              dispatch({ type: 'updatePlace', id: place.id, patch: { rentEur: v } })
            }
          }}
        />
      </div>
      <p id={`${id}-hint`} className="muted small">
        {t('rent.hint')}
      </p>
    </div>
  )
}

interface Row {
  key: string
  type: string
  name: string
  window: string
  byMode: Partial<Record<Mode, Trip>>
  share: number | null
}

function rowsOf(detail: CellDetail, typeLabel: (k: string) => string): Row[] {
  const map = new Map<string, Row>()
  for (const tr of detail.trips) {
    const key = `${tr.destination_type}|${tr.destination_id}`
    let r = map.get(key)
    if (!r) {
      const part = detail.fit_parts?.find((p) => p.destination_type === tr.destination_type)
      r = {
        key,
        type: tr.destination_type,
        name: tr.destination_type === 'campus_site' ? (tr.name ?? typeLabel('campus_site')) : `${typeLabel(tr.destination_type)}: ${tr.name ?? '–'}`,
        window: tr.trip_window,
        byMode: {},
        share: part ? part.share : null,
      }
      map.set(key, r)
    }
    r.byMode[tr.mode] = tr
  }
  const rows = [...map.values()]
  rows.sort((a, b) => (a.type === 'campus_site' ? -1 : b.type === 'campus_site' ? 1 : a.name.localeCompare(b.name)))
  return rows
}

function TripsTable({ detail, modes }: { detail: CellDetail; modes: Mode[] }) {
  const { t, label, duration } = useI18n()
  const refs = useRefs()
  const { state } = useStore()
  const [openLegs, setOpenLegs] = useState<string | null>(null)
  const typeLabel = (k: string) => {
    const x = refs.kind === 'ok' ? refs.refs.types.find((d) => d.destination_type === k) : null
    return x ? label(x.label) : k
  }
  const chosen = state.profile.modes
  const rows = rowsOf(detail, typeLabel)
  const campusRows = rows.filter((r) => r.type === 'campus_site')
  const firstCampus = campusRows[0]?.key
  return (
    <div className="trips">
      <h4 className="trips-title">{t('trips.title')}</h4>
      <table>
        <thead>
          <tr>
            <th scope="col">{t('trips.destination')}</th>
            {modes.map((m) => (
              <th key={m} scope="col" className={chosen.includes(m) ? '' : 'off'}>
                <ModeIcon mode={m} title="" />
                <span className="th-mode">{t(`mode.${m}`)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.flatMap((r) => {
            const fastest = chosen
              .map((m) => [m, r.byMode[m]?.minutes] as const)
              .filter((x): x is readonly [Mode, number] => x[1] != null)
              .sort((a, b) => a[1] - b[1])[0]?.[0]
            const showShare = r.share != null && (r.type !== 'campus_site' || r.key === firstCampus)
            const bus = r.byMode.transit
            const legsOpen = openLegs === r.key
            const out = [
              <tr key={r.key} data-testid="trip-row">
                <th scope="row">
                  <span className="trip-name">{r.name}</span>
                  <span className="trip-when">
                    <TripWindowText window={r.window} />
                  </span>
                  {showShare && (
                    <span className="share" title={t('trips.share')}>
                      <span className="share-bar">
                        <i style={{ width: `${Math.round((r.share ?? 0) * 100)}%` }} />
                      </span>
                      <span className="visually-hidden">{t('trips.share')}: </span>
                      {Math.round((r.share ?? 0) * 100)} %
                    </span>
                  )}
                </th>
                {modes.map((m) => {
                  const tr = r.byMode[m]
                  const off = !chosen.includes(m)
                  const best = m === fastest
                  const text = !tr ? '–' : tr.minutes == null ? t('trips.unreachable') : duration(tr.minutes)
                  const cls = `${off ? 'off' : ''}${best ? ' best' : ''}`
                  return (
                    <td key={m} className={cls} title={off ? t('trips.notYourMode') : best ? t('trips.fastest') : undefined}>
                      {m === 'transit' && tr?.legs && !tr.legs.walk_only ? (
                        <button
                          type="button"
                          className="legs-toggle"
                          aria-expanded={legsOpen}
                          aria-label={`${text}, ${t('legs.title')}`}
                          onClick={() => setOpenLegs(legsOpen ? null : r.key)}
                        >
                          {text}
                          {best && <span aria-hidden="true"> ★</span>}
                        </button>
                      ) : (
                        <>
                          {text}
                          {best && <span aria-hidden="true"> ★</span>}
                        </>
                      )}
                      {best && <span className="visually-hidden">, {t('trips.fastest')}</span>}
                      {off && <span className="visually-hidden">, {t('trips.notYourMode')}</span>}
                    </td>
                  )
                })}
              </tr>,
            ]
            if (legsOpen && bus?.legs) {
              const l = bus.legs
              out.push(
                <tr key={`${r.key}-legs`} className="legs-row">
                  <td colSpan={modes.length + 1}>
                    <ul className="plain legs">
                      <li>{t('legs.walkToStop', { stop: l.first_stop ?? '–', min: l.access_min })}</li>
                      <li>{t('legs.wait', { min: l.wait_min })}</li>
                      <li>{t('legs.ride', { line: l.first_route ?? '–', min: l.in_vehicle_min })}</li>
                      {l.transfers > 0 && <li>{t(l.transfers === 1 ? 'legs.transfers.one' : 'legs.transfers.other', { n: l.transfers })}</li>}
                      <li>{t('legs.walkFromStop', { min: l.egress_min })}</li>
                      {l.last_departure && <li><strong>{t('legs.last', { time: l.last_departure })}</strong></li>}
                    </ul>
                  </td>
                </tr>,
              )
            }
            return out
          })}
        </tbody>
      </table>
      <p className="muted small">
        ★ {t('trips.fastest')}
        {campusRows.length > 1 && <> · {t('trips.campusMean')}</>}
      </p>
    </div>
  )
}

/** Check for one place (docs/app_screens.md §1.3). */
export function PlaceCard({ place, cell }: { place: Place; cell: CellState }) {
  const { t, duration } = useI18n()
  const refs = useRefs()
  const { dispatch } = useStore()
  const [renaming, setRenaming] = useState(false)
  const detail = cell.kind === 'ok' ? cell.detail : null
  const rank = useRank(detail?.fit)
  const modes: Mode[] = refs.kind === 'ok' ? refs.refs.meta.modes : ['walk', 'bike', 'transit']
  const name = placeName(place, t)

  return (
    <article className={`card place-card${cell.kind === 'ok' && cell.stale ? ' dim' : ''}`} data-testid="place" aria-busy={cell.kind === 'loading'}>
      <header className="place-head">
        <span className="place-id" aria-hidden="true">{place.id}</span>
        {renaming ? (
          <input
            className="place-rename"
            aria-label={t('check.rename.label', { id: place.id })}
            defaultValue={place.label ?? ''}
            autoFocus
            onBlur={(e) => {
              dispatch({ type: 'updatePlace', id: place.id, patch: { label: e.target.value.trim() || null } })
              setRenaming(false)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === 'Escape') (e.target as HTMLInputElement).blur()
            }}
          />
        ) : (
          <h3 className="place-name">{name}</h3>
        )}
        <button type="button" className="btn-link small" onClick={() => setRenaming(true)}>
          {t('check.rename')}
        </button>
        <button
          type="button"
          className="btn-icon"
          aria-label={t('check.remove', { id: place.id })}
          onClick={() => dispatch({ type: 'removePlace', id: place.id })}
        >
          ×
        </button>
      </header>
      {detail?.district && <p className="muted small place-district">{t('check.district', { district: detail.district })}</p>}

      {cell.kind === 'loading' && <p className="muted">{t('status.loading')}</p>}
      {cell.kind === 'nodata' && <p className="note note-sample">{t('check.noData')}</p>}
      {cell.kind === 'error' && <p className="note banner-inline">{t('error.serverNoResult')}</p>}

      {detail && (
        <>
          <div className="place-score">
            <FitBadge fit={detail.fit ?? null} size="l" />
            <div>
              <p className="place-fit-label">{t('fit.label')}</p>
              <p className="place-rank" data-testid="rank">
                <RankText rank={rank} />
              </p>
              {detail.weekly_min != null && (
                <p className="place-weekly" data-testid="weekly">
                  {t('weekly.label', { time: duration(detail.weekly_min) })}
                </p>
              )}
            </div>
          </div>
          {rank != null && <p className="muted small">{t('rank.note')}</p>}
          {detail.populated === false && <p className="muted small">{t('check.addressCell')}</p>}
          {detail.reasons && detail.reasons.length > 0 && <Reasons reasons={detail.reasons} />}
          <RentInput place={place} />
          <TripsTable detail={detail} modes={modes} />
          <div className="place-actions">
            <button
              type="button"
              className="btn btn-quiet btn-small"
              onClick={() => {
                dispatch({ type: 'nearby', id: place.id })
                dispatch({ type: 'focus', point: place.point })
              }}
            >
              {t('check.nearby')} →
            </button>
          </div>
          <DataNote />
        </>
      )}
    </article>
  )
}
