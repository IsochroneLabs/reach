// Pin-drop inspector (POST /api/inspect): precomputed classes and counts of the cell, reachable
// facilities with travel times, the route to the nearest one (time first, length secondary) and the 5/10/15 min isochrone (display).
import { CARD_HELP, CELL_STATUS_TEXT, classPlain } from '../labels'
import { classColour, classLabel, TRANSIT } from '../palette'
import type { IsochroneDirection } from '../settings'
import type { Inspect, Meta } from '../types'
import Card from './Card'

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
}

const fmtMin = (m: number | null | undefined) => (m === null || m === undefined ? '–' : `${m.toFixed(1)} min`)

export default function Inspector(props: Props) {
  const { meta, state, districtName, category, onCategory, onClose, card, coloursWithPin, onColoursWithPin, direction, reverseError } = props
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
          <InspectBody data={state.previous} meta={meta} districtName={districtName} category={category} onCategory={onCategory} direction={direction} reverseError={reverseError} />
        </div>
      )}
      {state.status === 'error' && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {state.status === 'done' && (
        <InspectBody data={state.data} meta={meta} districtName={districtName} category={category} onCategory={onCategory} direction={direction} reverseError={reverseError} />
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
}: {
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
                      <li key={f.facility_id}>
                        <span>{f.name ?? <span className="muted">unnamed</span>}</span>
                        <span className="reach-time">{fmtMin(f.time_min)}</span>
                      </li>
                    ))}
                  </ol>
                )}
                {c.nearest_route && (
                  <p className="small route-info" data-testid={`route-${c.category}`}>
                    Route to the nearest:{' '}
                    <strong title="Travel time of the route, including slopes">
                      {fmtMin(c.nearest_route.properties.time_s / 60)}
                    </strong>{' '}
                    <span className="muted">
                      · {Math.round(c.nearest_route.properties.length_m)} m · shown on the map when this category is
                      selected
                    </span>
                  </p>
                )}
              </details>
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

function budget(meta: Meta, profileId: string) {
  return meta.profiles.find((p) => p.profile_id === profileId)?.time_budget_min ?? ''
}
