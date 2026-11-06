// Pin-drop inspector (POST /api/inspect): precomputed classes and counts of the cell, reachable
// facilities with times, the route to the nearest one and the 5/10/15 min isochrone (display).
import { classColour, classLabel, TRANSIT } from '../palette'
import type { Inspect, Meta } from '../types'

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
}

const fmtMin = (m: number | null | undefined) => (m === null || m === undefined ? '–' : `${m.toFixed(1)} min`)

export default function Inspector({ meta, state, districtName, category, onCategory, onClose }: Props) {
  if (state.status === 'idle') return null
  return (
    <section id="inspector" className="card inspector" aria-label="Inspector" aria-busy={state.status === 'loading'}>
      <header className="card-head">
        <h2>Location</h2>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close inspector">
          ×
        </button>
      </header>
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
          <InspectBody data={state.previous} meta={meta} districtName={districtName} category={category} onCategory={onCategory} />
        </div>
      )}
      {state.status === 'error' && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {state.status === 'done' && (
        <InspectBody data={state.data} meta={meta} districtName={districtName} category={category} onCategory={onCategory} />
      )}
    </section>
  )
}

function InspectBody({
  data,
  meta,
  districtName,
  category,
  onCategory,
}: {
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

  return (
    <div data-testid="inspect-result">
      <p className="cell-meta">
        {data.cell.scored ? (
          <>
            {data.cell.population?.toLocaleString('en')} residents in this 100 m cell
            {district && <> · {district}</>}
          </>
        ) : (
          <>No residents in this 100 m cell (not scored)</>
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
      {weakest && (
        <p className="weakest">
          Weakest category: <strong>{meta.categories.find((c) => c.id === weakest)?.name ?? weakest}</strong>
          {pre.get(weakest) && <> ({pre.get(weakest)!.class})</>}
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
                  <span className="swatch" style={{ background: classColour(p?.class) }} title={p ? classLabel(p.class) : 'not scored'} />
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
                        <span className="muted">{fmtMin(f.time_min)}</span>
                      </li>
                    ))}
                  </ol>
                )}
                {c.nearest_route && (
                  <p className="muted small">
                    Route to the nearest ({Math.round(c.nearest_route.properties.length_m)} m) shown on the map when
                    this category is selected.
                  </p>
                )}
              </details>
            </li>
          )
        })}
        {transit && (
          <li className={category === TRANSIT ? 'selected' : undefined}>
            <div className="transit-row">
              <span className="swatch" style={{ background: classColour(transit.class, true) }} title={classLabel(transit.class)} />
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
      <p className="muted small">
        Count / needed for “sufficient” · time to the nearest. Dashed lines: area reachable in{' '}
        {data.isochrone.features.map((f) => f.properties.contour_min).join(', ')} min (display only;
        counts use the routing matrix).
        {data.cached && ' · cached'}
      </p>
    </div>
  )
}

function budget(meta: Meta, profileId: string) {
  return meta.profiles.find((p) => p.profile_id === profileId)?.time_budget_min ?? ''
}
