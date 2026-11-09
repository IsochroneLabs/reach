// Recommended sites (GET /api/recommendations, methodology §5): ranked zones where one new
// facility of the selected category reduces the deficit most for the selected profile. A click
// loads the zone's catchment (POST /api/catchment with candidate_id), drawn on the map. Hidden
// when the run has no recommendations for this selection.
import { CARD_HELP, classPlain } from '../labels'
import { classColour, FACILITY_CLASSES } from '../palette'
import type { CandidateCatchment, Meta, RecommendationProps, Recommendations } from '../types'
import Card from './Card'

export type CatchmentState =
  | { status: 'idle' }
  | { status: 'loading'; candidateId: string }
  | { status: 'done'; candidateId: string; data: CandidateCatchment }
  | { status: 'error'; candidateId: string; message: string }

interface Props {
  meta: Meta
  category: string
  recommendations: Recommendations | null
  catchment: CatchmentState
  onSelect: (rec: RecommendationProps | null) => void
  card: { open: boolean; onToggle: (open: boolean) => void }
}

const fmt = (n: number) => Math.round(n).toLocaleString('en')

export default function RecommendationsPanel({ meta, category, recommendations, catchment, onSelect, card }: Props) {
  const features = recommendations?.available ? recommendations.features : []
  if (!features.length) return null
  const cat = meta.categories.find((c) => c.id === category)
  const selected = catchment.status === 'idle' ? null : catchment.candidateId
  const detail = catchment.status === 'done' ? catchment.data : null

  const budgetMin = detail ? (meta.profiles.find((p) => p.profile_id === detail.profile_id)?.time_budget_min ?? null) : null

  return (
    <Card
      title="Recommended sites"
      help={CARD_HELP.recommendations}
      {...card}
      extra={
        selected && (
          <button type="button" className="link-btn small" onClick={() => onSelect(null)}>
            Clear
          </button>
        )
      }
    >
      <p className="muted small">
        Where one new {cat?.name.toLowerCase() ?? category} facility would help most (100 m zones, best first).
      </p>
      <ol className="rec-list">
        {features.map((f) => {
          const r = f.properties
          return (
            <li key={r.candidate_id} className={r.candidate_id === selected ? 'selected' : undefined}>
              <button
                type="button"
                className="rec-btn"
                aria-pressed={r.candidate_id === selected}
                onClick={() => onSelect(r.candidate_id === selected ? null : r)}
              >
                <span className="rec-rank">{r.rank}</span>
                <span className="rec-body">
                  <strong>{r.district_name ?? 'Outside the districts'}</strong>
                  <span className="small">
                    {fmt(r.residents_gaining_access)} residents gain access
                    {cat && cat.k > 1 && <> · {fmt(r.residents_to_sufficient)} reach sufficient</>}
                  </span>
                  <span className="muted small">
                    deficit −{fmt(r.population_gain)} · {fmt(r.catchment_residents)} residents within reach
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ol>
      {catchment.status === 'loading' && <p className="muted small">Loading catchment…</p>}
      {catchment.status === 'error' && <p className="error">{catchment.message}</p>}
      {detail && (
        <div className="rec-detail">
          <p className="small">
            <strong>{fmt(detail.residents)}</strong> residents in {detail.cells} cells reach zone #
            {detail.target.rank} within {budgetMin ?? '–'} minutes (highlighted on the map). Their classes today:
          </p>
          <ul className="rec-classes small">
            {/* k = 1: "insufficient" is empty (methodology §4), as in the legend */}
            {FACILITY_CLASSES.filter((c) => c !== 'insufficient' || (cat?.k ?? 1) > 1).map((c) => (
              <li key={c}>
                <span className="swatch" style={{ background: classColour(c) }} />
                {classPlain(c, budgetMin)}: {fmt(detail.residents_by_class[category]?.[c] ?? 0)}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="muted small">
        Accessibility only: zoning, parcels, capacity, minimum catchment and statutory planning (e.g.
        Bedarfsplanung for doctors) are not considered; results depend on k and OSM completeness. Where k
        is 2 or more, a second site in a neighbouring zone can still rank high (greedy selection, each zone
        once).
      </p>
    </Card>
  )
}
