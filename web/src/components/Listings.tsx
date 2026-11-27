import { useEffect, useState } from 'react'

import { getApi } from '../api/client'
import type { CellDetail, Listing, Trip } from '../api/types'
import { cellIdAt } from '../geo/laea'
import { useI18n } from '../i18n/i18n'
import { useDestName, useRefs } from '../remote/refs'
import { useListings } from '../remote/listings'
import { normalise } from '../state/profile'
import { useStore } from '../state/store'
import { FitBadge } from './FitBadge'

const KIND_KEY = {
  wg_room: 'listings.kind.wg_room',
  studio: 'listings.kind.studio',
  flat: 'listings.kind.flat',
} as const

function Kind({ kind }: { kind: Listing['kind'] }) {
  const { t } = useI18n()
  return <>{t(KIND_KEY[kind])}</>
}

/** Photo from its original URL (data contract: linked, never copied); grey ground if it fails. */
function Photo({ listing, big }: { listing: Listing; big?: boolean }) {
  const [failed, setFailed] = useState(false)
  const src = listing.image_urls?.[0]
  if (!src || failed) return <span className={`listing-photo${big ? ' big' : ''} empty`} aria-hidden="true" />
  return (
    <img
      className={`listing-photo${big ? ' big' : ''}`}
      src={src}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  )
}

function rent(listing: Listing): number | null {
  return listing.rent_total_eur ?? listing.rent_cold_eur
}

function Card({ listing }: { listing: Listing }) {
  const { t, duration } = useI18n()
  const { select } = useListings()
  const eur = rent(listing)
  return (
    <li className="listing">
      <button type="button" className="listing-card" onClick={() => select(listing.listing_id)}>
        <Photo listing={listing} />
        <span className="listing-body">
          <span className="listing-kind">
            <Kind kind={listing.kind} />
            {listing.district ? <> · {listing.district}</> : null}
          </span>
          <span className="listing-title">{listing.title ?? t('listings.untitled')}</span>
          <span className="listing-meta">
            <span className="num">{eur != null ? t('listings.eur', { eur }) : t('listings.noRent')}</span>
            {listing.size_m2 != null && <> · <span className="num">{t('listings.sizeValue', { size: listing.size_m2 })}</span></>}
            {listing.rooms != null && <> · {t('listings.roomsValue', { n: listing.rooms })}</>}
          </span>
          <span className="listing-foot">
            <FitBadge fit={listing.fit ?? null} size="s" />
            {listing.weekly_min != null && <span className="muted small">{t('weekly.short', { time: duration(listing.weekly_min) })}</span>}
          </span>
        </span>
      </button>
    </li>
  )
}

/** The fastest trip per destination type in the student's modes, for the listing detail. */
function useListingTrips(listing: Listing): { rows: [string, Trip][]; detail: CellDetail | null } {
  const refs = useRefs()
  const { state } = useStore()
  const [detail, setDetail] = useState<CellDetail | null>(null)
  const cellId = listing.cell_id

  useEffect(() => {
    if (!cellId || refs.kind !== 'ok') return
    const ctrl = new AbortController()
    const body = normalise(state.profile, refs.refs.types)
    getApi()
      .then((api) => api.cell(cellId, body, ctrl.signal))
      .then((d) => setDetail(d))
      .catch(() => setDetail(null))
    return () => ctrl.abort()
    // the profile is re-read when it changes; the listing's cell is the key
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cellId, refs.kind, JSON.stringify(state.profile)])

  const best = new Map<string, Trip>()
  for (const tr of detail?.trips ?? []) {
    if (tr.minutes == null || !state.profile.modes.includes(tr.mode)) continue
    const cur = best.get(tr.destination_type)
    if (!cur || (cur.minutes ?? Infinity) > tr.minutes) best.set(tr.destination_type, tr)
  }
  const order = Object.entries(state.profile.destinations)
    .filter(([, v]) => v.importance > 0)
    .sort((a, b) => b[1].importance - a[1].importance)
  const rows = order
    .map(([key]) => [key, best.get(key.split(':')[0])] as const)
    .filter((r): r is readonly [string, Trip] => !!r[1])
    .slice(0, 4)
  return { rows: rows as [string, Trip][], detail }
}

function Trips({ listing }: { listing: Listing }) {
  const { t, duration } = useI18n()
  const name = useDestName()
  const { rows, detail } = useListingTrips(listing)
  if (!listing.cell_id) return <p className="muted small">{t('listings.noTrips')}</p>
  if (!detail) return <p className="muted small">{t('listings.tripsLoading')}</p>
  if (!rows.length) return <p className="muted small">{t('listings.noTrips')}</p>
  return (
    <table className="listing-trips">
      <tbody>
        {rows.map(([key, tr]) => (
          <tr key={key}>
            <th scope="row">{name(key)}</th>
            <td className="num">{tr.minutes != null ? duration(tr.minutes) : '–'}</td>
            <td className="muted small">{tr.mode ? t(`mode.${tr.mode}.by`) : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Detail({ listing }: { listing: Listing }) {
  const { t, duration, date } = useI18n()
  const { select } = useListings()
  const { dispatch } = useStore()
  const eur = rent(listing)
  const check = () => {
    if (!listing.point) return
    dispatch({
      type: 'addPlace',
      place: {
        point: listing.point,
        cellId: listing.cell_id ?? cellIdAt(listing.point),
        label: listing.title ?? listing.district ?? t(KIND_KEY[listing.kind]),
      },
    })
  }
  return (
    <article className="listing-detail" data-testid="listing-detail">
      <button type="button" className="btn-link small" onClick={() => select(null)}>
        ← {t('listings.back')}
      </button>
      <h3 className="listing-detail-title">{listing.title ?? t('listings.untitled')}</h3>
      <p className="listing-kind">
        <Kind kind={listing.kind} />
        {listing.district ? <> · {listing.district}</> : null}
        {listing.geocode_precision && listing.geocode_precision !== 'house' ? <> · {t('listings.approx')}</> : null}
      </p>
      <Photo listing={listing} big />
      <div className="listing-figure">
        <FitBadge fit={listing.fit ?? null} />
        {listing.weekly_min != null && <span className="muted small">{t('weekly.short', { time: duration(listing.weekly_min) })}</span>}
      </div>
      <dl className="listing-params">
        <dt>{t('listings.rent')}</dt>
        <dd className="num">{eur != null ? t('listings.eur', { eur }) : '–'}</dd>
        <dt>{t('listings.size')}</dt>
        <dd className="num">{listing.size_m2 != null ? `${listing.size_m2} m²` : '–'}</dd>
        <dt>{t('listings.rooms')}</dt>
        <dd className="num">{listing.rooms ?? '–'}</dd>
        <dt>{t('listings.available')}</dt>
        <dd>{listing.available_from ? date(listing.available_from) : t('listings.availableNow')}</dd>
        {listing.deposit_eur != null && (
          <>
            <dt>{t('listings.deposit')}</dt>
            <dd className="num">{t('listings.eur', { eur: listing.deposit_eur })}</dd>
          </>
        )}
      </dl>
      <Trips listing={listing} />
      {listing.features?.length ? <p className="small">{listing.features.join(' · ')}</p> : null}
      {listing.description_excerpt ? <p className="small">{listing.description_excerpt}</p> : null}
      <div className="listing-actions">
        <button type="button" className="btn btn-small" onClick={check} disabled={!listing.point}>
          {t('listings.check')}
        </button>
        <a href={listing.source_url} target="_blank" rel="noopener noreferrer">
          {t('listings.open')}
        </a>
      </div>
      <p className="muted small">{t('listings.source', { date: date(listing.last_seen.slice(0, 10)) })}</p>
    </article>
  )
}

/** Find → listings: current ads, best fit first, or one detail. */
export function Listings() {
  const { t } = useI18n()
  const { data, updating, error, selected, retry } = useListings()
  if (selected) return <Detail listing={selected} />
  if (error) {
    return (
      <p className="note" role="alert">
        {t('listings.error')}{' '}
        <button type="button" className="btn-link small" onClick={retry}>
          {t('error.retry')}
        </button>
      </p>
    )
  }
  if (!data) {
    return (
      <ol className="plain" aria-busy="true">
        {[1, 2, 3].map((i) => (
          <li key={i} className="card skeleton" aria-hidden="true" />
        ))}
        <li className="visually-hidden">{t('listings.loading')}</li>
      </ol>
    )
  }
  if (!data.length) return <p className="note">{t('listings.none')}</p>
  return (
    <ul className={`plain listings${updating ? ' dim' : ''}`}>
      {data.map((l) => (
        <Card key={l.listing_id} listing={l} />
      ))}
    </ul>
  )
}
