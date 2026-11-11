// Pin-drop inspector (POST /api/inspect): precomputed classes and counts of the cell, reachable
// facilities with travel times (click: show on the map with its route), the next missing facility
// of a category below its requirement, the route to the nearest one (time first, length
// secondary) and the 5/10/15 min isochrone (display).
import { googleMapsUrl, infoLines, PARK_NOTE } from '../facilityInfo'
import { CARD_HELP, CELL_STATUS_TEXT, classPlain, timeLabel } from '../labels'
import { classColour, classLabel, TRANSIT } from '../palette'
import type { IsochroneDirection } from '../settings'
import type { Inspect, Meta, RouteAnswer } from '../types'
import Card from './Card'

/** Route to the facility picked in the list (POST /api/route). */
export type FacilityRouteState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done'; data: RouteAnswer }
  | { status: 'error'; message: string }

/** What the facility entries need: the pick, the hover, and the route of the pick. */
export interface FacilityProps {
  selected: string | null
  route: FacilityRouteState
  /** Pick a facility (a second click on it clears the pick); its category becomes the selected one. */
  onSelect: (facilityId: string | null, category: string) => void
  onHover: (facilityId: string | null) => void
  /** Facilities of the selected category that are parks (area outline): they get the park note. */
  areaIds: Set<string>
}

export type InspectState =
  | { status: 'idle' }
  | { status: 'loading'; showSpinner: boolean; previous: Inspect | null }
  | { status: 'done'; data: Inspect }
  | { status: 'error'; message: string }

interface Props {
  meta: Meta
  state: InspectState
  districtName: (id: string | null) => string | null
  category: string
  onCategory: (id: string) => void
  onClose: () => void
  card: { open: boolean; onToggle: (open: boolean) => void }
  coloursWithPin: boolean
  onColoursWithPin: (on: boolean) => void
  direction: IsochroneDirection
  /** Message when the reverse isochrone could not be loaded. */
  reverseError: string | null
  facility: FacilityProps
}

const fmtMin = (m: number | null | undefined) => (m === null || m === undefined ? '–' : `${m.toFixed(1)} min`)

export default function Inspector(props: Props) {
  const { meta, state, districtName, category, onCategory, onClose, card, coloursWithPin, onColoursWithPin, direction, reverseError, facility } = props
  if (state.status === 'idle') return null
  return (
    <Card
      id="inspector"
      className="inspector"
      title="Location"
      label="Inspector"
      busy={state.status === 'loading'}
      help={CARD_HELP.inspector}
      {...card}
      extra={
        <span className="card-tools">
          <label className="check small" title="Show the cell colours while a pin is set">
            <input type="checkbox" checked={coloursWithPin} onChange={(e) => onColoursWithPin(e.target.checked)} />
            Show cell colours
          </label>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close inspector">
            ×
          </button>
        </span>
      }
    >
      {state.status === 'loading' && state.showSpinner && (
        <p className="loading" role="status">
          <span className="spinner" aria-hidden="true" /> Calculating reachable facilities…
        </p>
      )}
      {state.status === 'loading' && !state.showSpinner && !state.previous && (
        <p className="loading" aria-hidden="true">&nbsp;</p>
      )}
      {state.status === 'loading' && state.previous && (
        <div className="stale">
          <InspectBody data={state.previous} meta={meta} districtName={districtName} category={category} onCategory={onCategory} direction={direction} reverseError={reverseError} facility={facility} />
        </div>
      )}
      {state.status === 'error' && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {state.status === 'done' && (
        <InspectBody data={state.data} meta={meta} districtName={districtName} category={category} onCategory={onCategory} direction={direction} reverseError={reverseError} facility={facility} />
      )}
    </Card>
  )
}

function InspectBody({
  data,
  meta,
  districtName,
  category,
  onCategory,
  direction,
  reverseError,
  facility,
}: {
  facility: FacilityProps
  direction: IsochroneDirection
  reverseError: string | null
  data: Inspect
  meta: Meta
  districtName: (id: string | null) => string | null
  category: string
  onCategory: (id: string) => void
}) {
  const pre = new Map(data.precomputed?.categories.map((c) => [c.category, c]))
  const transit = data.precomputed?.transit ?? null
  const live = data.source === 'live'
  const weakest = data.weakest_category
  const district = districtName(data.cell.district_id)
  const budgetMin = meta.profiles.find((p) => p.profile_id === data.profile_id)?.time_budget_min ?? null
  const rings = data.isochrone.features.map((f) => f.properties.contour_min).join('/')

  return (
    <div data-testid="inspect-result">
      <p className="cell-meta">
        {data.cell.status === 'scored' ? (
          <>
            {data.cell.population?.toLocaleString('en')} residents in this 100 m cell
            {district && <> · {district}</>}
          </>
        ) : (
          <span data-testid="cell-status">{CELL_STATUS_TEXT[data.cell.status]}</span>
        )}
        {live ? (
          <span className="badge live" title="Computed now with a live Valhalla matrix; not part of the published scores">
            live result
          </span>
        ) : (
          <span className="badge" title="Values of the published run">
            precomputed
          </span>
        )}
      </p>
      <p className="muted small origin-note">Measured from the centre of this 100 m cell (the pin).</p>
      {weakest && (
        <p className="weakest">
          Weakest category: <strong>{meta.categories.find((c) => c.id === weakest)?.name ?? weakest}</strong>
          {pre.get(weakest) && <> ({classPlain(pre.get(weakest)!.class, budgetMin).toLowerCase()})</>}
        </p>
      )}
      {data.cell.scored && !weakest && data.precomputed && <p className="weakest">All categories sufficient.</p>}

      <ul className="cat-list">
        {data.categories.map((c) => {
          const p = pre.get(c.category)
          const k = meta.categories.find((m) => m.id === c.category)?.k
          const nearest = p?.nearest_min ?? c.reachable[0]?.time_min ?? null
          return (
            <li key={c.category} className={c.category === category ? 'selected' : undefined}>
              <details>
                <summary>
                  <span className="swatch" style={{ background: classColour(p?.class) }} title={p ? `${classPlain(p.class, budgetMin)} (${classLabel(p.class)})` : 'not scored'} />
                  <button type="button" className="link-btn" onClick={() => onCategory(c.category)} title="Show on the map">
                    {c.name}
                  </button>
                  <span className="cat-count">
                    {c.count}
                    {k !== undefined && <span className="muted"> / {k}</span>}
                  </span>
                  <span className="muted cat-time">{fmtMin(nearest)}</span>
                </summary>
                {c.reachable.length === 0 ? (
                  <p className="muted small">None reachable within {budget(meta, data.profile_id)} min.</p>
                ) : (
                  <ol className="reach-list">
                    {c.reachable.map((f) => (
                      <li key={f.facility_id} className={facility.selected === f.facility_id ? 'picked' : undefined}>
                        <FacilityButton id={f.facility_id} name={f.name} category={c.category} facility={facility} />
                        <span className="reach-time">{fmtMin(f.time_min)}</span>
                      </li>
                    ))}
                  </ol>
                )}
                {c.next_facility && (
                  <p className="small next-info" data-testid={`next-${c.category}`}>
                    {c.count === 0 ? 'Nearest' : 'Next missing'}:{' '}
                    <FacilityButton id={c.next_facility.facility_id} name={c.next_facility.name} category={c.category} facility={facility} />{' '}
                    <strong>{timeLabel(c.next_facility.time_min, budgetMin, !c.next_facility.within_budget)}</strong>
                  </p>
                )}
                {!c.next_facility && c.next_note && (
                  <p className="muted small next-info" data-testid={`next-${c.category}`}>
                    {c.next_note}
                  </p>
                )}
                {c.nearest_route && (
                  <p className="small route-info" data-testid={`route-${c.category}`}>
                    Route to the nearest:{' '}
                    <strong title="Travel time of the route, including slopes">
                      {fmtMin(c.nearest_route.properties.time_s / 60)}
                    </strong>{' '}
                    <span className="muted">
                      · {Math.round(c.nearest_route.properties.length_m)} m
                    </span>
                  </p>
                )}
              </details>
              {/* outside the details, so a pick on the map shows its route with the list collapsed */}
              {c.category === category && <FacilityRouteInfo state={facility.route} budgetMin={budgetMin} areaIds={facility.areaIds} />}
            </li>
          )
        })}
        {transit && (
          <li className={category === TRANSIT ? 'selected' : undefined}>
            <div className="transit-row">
              <span className="swatch" style={{ background: classColour(transit.class, true) }} title={`${classPlain(transit.class, null, true)} (${classLabel(transit.class)})`} />
              <button type="button" className="link-btn" onClick={() => onCategory(TRANSIT)} title="Show on the map">
                Public transport
              </button>
              <span className="cat-count">{transit.departures.toLocaleString('en')}</span>
              <span className="muted cat-time">{fmtMin(transit.nearest_stop_min)}</span>
            </div>
            <p className="muted small transit-note">
              Weekday departures at {transit.stops_count} stops reachable on foot.
            </p>
          </li>
        )}
      </ul>
      <p className="muted small" data-testid="isochrone-legend">
        Count / needed for “sufficient” · time to the nearest.{' '}
        {direction !== 'reverse' && <>Forward (dashed): where you get in {rings} min. </>}
        {direction !== 'forward' &&
          (reverseError ? (
            <span role="alert">Reverse isochrone unavailable: {reverseError} </span>
          ) : (
            <>Reverse (dotted): from where people reach this point in {rings} min. </>
          ))}
        Display only; counts use the routing matrix.
        {data.cached && ' · cached'}
      </p>
    </div>
  )
}

/** A facility name that picks the facility (map pin, route) and highlights its pin on hover. */
function FacilityButton({
  id,
  name,
  category,
  facility,
}: {
  id: string
  name: string | null
  category: string
  facility: FacilityProps
}) {
  const picked = facility.selected === id
  return (
    <button
      type="button"
      className="link-btn facility-btn"
      aria-pressed={picked}
      title={picked ? 'Click again to clear the route' : 'Show on the map with the route'}
      onClick={() => facility.onSelect(picked ? null : id, category)}
      onMouseEnter={() => facility.onHover(id)}
      onMouseLeave={() => facility.onHover(null)}
      onFocus={() => facility.onHover(id)}
      onBlur={() => facility.onHover(null)}
    >
      {name ?? <span className="muted">unnamed</span>}
    </button>
  )
}

function FacilityRouteInfo({
  state,
  budgetMin,
  areaIds,
}: {
  state: FacilityRouteState
  budgetMin: number | null
  areaIds: Set<string>
}) {
  if (state.status === 'idle') return null
  if (state.status === 'loading')
    return (
      <p className="muted small" role="status" data-testid="facility-route">
        Calculating the route…
      </p>
    )
  if (state.status === 'error')
    return (
      <p className="error small" role="alert" data-testid="facility-route">
        {state.message}
      </p>
    )
  const { route, facility, within_budget } = state.data
  const lines = infoLines(facility.tags)
  return (
    <div className="small route-info" data-testid="facility-route">
      <p>
        Route to <strong>{facility.name ?? 'this facility'}</strong>:{' '}
        <strong>{timeLabel(route.properties.time_s / 60, budgetMin, !within_budget)}</strong>{' '}
        <span className="muted">· {Math.round(route.properties.length_m)} m</span>
      </p>
      <dl className="facility-info" data-testid="facility-info">
        {lines.map((l) => (
          <div key={l.label}>
            <dt>{l.label}</dt>
            <dd>
              {l.href ? (
                <a href={l.href} target="_blank" rel="noreferrer">
                  {l.value}
                </a>
              ) : (
                l.value
              )}
            </dd>
          </div>
        ))}
      </dl>
      {areaIds.has(facility.facility_id) && <p className="muted">{PARK_NOTE}</p>}
      <p className="facility-links">
        <a href={facility.osm_url} target="_blank" rel="noreferrer">
          View on OpenStreetMap
        </a>{' '}
        ·{' '}
        <a href={googleMapsUrl(facility.name, facility.point)} target="_blank" rel="noreferrer">
          Open in Google Maps
        </a>
      </p>
    </div>
  )
}

function budget(meta: Meta, profileId: string) {
  return meta.profiles.find((p) => p.profile_id === profileId)?.time_budget_min ?? ''
}
