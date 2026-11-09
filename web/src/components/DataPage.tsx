// Data & validation page (GET /api/meta): run, data dates, validation summary, known
// limitations, sources and attribution.
import { BASEMAP_ATTRIBUTION, DATA_ATTRIBUTION, OSM_ATTRIBUTION } from '../attribution'
import type { Meta } from '../types'
import { profileLabel } from '../labels'

const DOCS: string = import.meta.env.VITE_DOCS_URL

/** Dates as `5 Nov 2026`, timestamps as `5 Nov 2026, 20:49 UTC`. */
function fmtDate(iso: string | null): string {
  if (!iso) return '–'
  const withTime = iso.length > 10
  const text = new Date(iso).toLocaleString('en-GB', {
    dateStyle: 'medium',
    timeStyle: withTime ? 'short' : undefined,
    timeZone: 'UTC',
  })
  return withTime ? `${text} UTC` : text
}

// Known limitations of the method (docs/methodology.md, docs/notes.md); the measured effect of
// each is in the validation issues above it.
const LIMITATIONS: { text: string; doc: string }[] = [
  { text: 'Only residents in cells whose centre lies inside the city boundary are scored; the few edge cells outside appear as totals in the validation report.', doc: 'notes.md' },
  { text: 'Each 100 m Zensus cell is routed from its centre point, not from the buildings in it.', doc: 'notes.md' },
  { text: 'Facilities come from OpenStreetMap; completeness differs by category and is not yet checked against official lists.', doc: 'methodology.md' },
  { text: 'Valhalla routes by cost, not pure time: a faster profile can occasionally reach fewer facilities (the monotonicity warnings).', doc: 'notes.md' },
  { text: 'The route drawn on the map goes to the nearest access point by straight line; its time can differ slightly from the listed time.', doc: 'data_contract.md' },
  { text: 'Isochrones are for display only; counts always come from the routing matrix.', doc: 'architecture.md' },
  { text: 'Thresholds (k per category) and public transport classes are provisional until calibrated for Tübingen.', doc: 'methodology.md' },
]

export default function DataPage({ meta }: { meta: Meta }) {
  const { run, validation } = meta
  return (
    <main className="page" data-testid="data-page">
      <h1>Data &amp; validation</h1>

      <section className="card">
        <h2>Current run</h2>
        <dl className="kv">
          <dt>Run</dt>
          <dd>
            <code>{run.run_id}</code> ({run.status})
          </dd>
          <dt>Finished</dt>
          <dd>{fmtDate(run.finished_at)}</dd>
          <dt>OpenStreetMap snapshot</dt>
          <dd>{fmtDate(run.osm_snapshot)}</dd>
          <dt>Timetable (GTFS) valid</dt>
          <dd>
            {fmtDate(run.gtfs_valid_from)} – {fmtDate(run.gtfs_valid_to)}
          </dd>
          <dt>Reference weekday</dt>
          <dd>{fmtDate(run.reference_weekday)}</dd>
          <dt>Profiles</dt>
          <dd>{meta.profiles.map((p) => profileLabel(p, meta.profiles)).join(' · ')}</dd>
          <dt>Categories (k)</dt>
          <dd>{meta.categories.map((c) => `${c.name} (${c.k})`).join(' · ')}</dd>
        </dl>
      </section>

      <section className="card">
        <h2>Validation</h2>
        <p className="checks">
          <span className="badge ok">{validation.ok} ok</span>
          <span className="badge warn">{validation.warn} warnings</span>
          <span className={`badge ${validation.fail ? 'fail' : ''}`}>{validation.fail} failed</span>
        </p>
        {validation.issues.length === 0 ? (
          <p className="muted">No warnings in this run.</p>
        ) : (
          <ul className="issues">
            {validation.issues.map((i) => (
              <li key={`${i.stage}/${i.check}`}>
                <span className={`badge ${i.status}`}>{i.status}</span> <code>{i.check}</code>{' '}
                <span className="muted">({i.stage})</span>
                <p className="small">{i.message}</p>
              </li>
            ))}
          </ul>
        )}
        <h3>Known limitations</h3>
        <ul className="limitations">
          {LIMITATIONS.map((l) => (
            <li key={l.text}>
              {l.text}{' '}
              <a href={`${DOCS}/${l.doc}`} target="_blank" rel="noreferrer" className="small">
                {l.doc}
              </a>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Data sources</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Source</th>
                <th scope="col">Retrieved</th>
                <th scope="col">Licence</th>
              </tr>
            </thead>
            <tbody>
              {meta.data_sources.map((s) => (
                <tr key={s.source}>
                  <th scope="row">
                    <a href={s.url} target="_blank" rel="noreferrer">
                      {s.source}
                    </a>
                  </th>
                  <td>{fmtDate(s.retrieved_at)}</td>
                  <td>{s.licence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h3>Attribution</h3>
        <p className="attribution">
          {[OSM_ATTRIBUTION, ...DATA_ATTRIBUTION, `Basemap ${BASEMAP_ATTRIBUTION}`].map((html) => (
            <span key={html} dangerouslySetInnerHTML={{ __html: html }} />
          ))}
        </p>
        <p className="small muted">
          Method and architecture: <a href={`${DOCS}/methodology.md`} target="_blank" rel="noreferrer">methodology</a>{' '}
          · <a href={`${DOCS}/architecture.md`} target="_blank" rel="noreferrer">architecture</a>
        </p>
      </section>
    </main>
  )
}
