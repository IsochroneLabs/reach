// Housing potential (GET /api/housing, methodology §5b): the best unpopulated 100 m cells, scored
// like the residents' cells with the settings of the score card. A click on an entry drops the
// pin there, so the inspector shows the live values ("no residents in the Zensus 2022 grid").
import { CARD_HELP } from '../labels'
import { classColour, SCORE_CLASSES, SCORE_RANGES } from '../palette'
import { cellCentre, topHousing } from '../score'
import type { Category, Housing } from '../types'
import Card from './Card'

export type HousingState =
  | { status: 'loading' }
  | { status: 'error'; message: string; onRetry: () => void }
  | { status: 'done'; housing: Housing }

interface Props {
  state: HousingState
  /** Categories of the score, for the heading. */
  categories: Category[]
  /** Pin at the cell's centre. */
  onPick: (lon: number, lat: number) => void
  card: { open: boolean; onToggle: (open: boolean) => void }
}

const TOP_N = 10

export default function HousingPanel({ state, categories, onPick, card }: Props) {
  const housing = state.status === 'done' ? state.housing : null
  const top = topHousing(housing, TOP_N)
  const names = categories.map((c) => c.name.toLowerCase()).join(', ')
  return (
    <Card title="Housing potential" help={CARD_HELP.housing} {...card}>
      {state.status === 'loading' && <p className="muted small">Loading housing potential…</p>}
      {state.status === 'error' && (
        <p className="error" role="alert">
          {state.message}{' '}
          <button type="button" className="link-btn" onClick={state.onRetry}>
            Retry
          </button>
        </p>
      )}
      {housing && !housing.available && (
        <p className="muted small">This run has no housing potential (published without the housing stage).</p>
      )}
      {housing?.available && !top.length && (
        <p className="muted small">No cells for this profile: the housing potential is computed for the walking profiles only.</p>
      )}
      {top.length > 0 && (
        <>
          <p className="muted small">
            Cells without residents, scored for {names || 'the selected categories'} (dashed outline on the map).
          </p>
          <ul className="housing-legend small" data-testid="housing-legend">
            {SCORE_CLASSES.map((cls, i) => (
              <li key={cls}>
                <span className="swatch" style={{ background: classColour(cls) }} />
                {SCORE_RANGES[i]}
              </li>
            ))}
          </ul>
          <h3 className="small">Top {top.length} cells for new homes</h3>
          <ol className="rec-list" data-testid="housing-top">
            {top.map((f, i) => {
              const p = f.properties
              return (
                <li key={p.cell_id}>
                  <button
                    type="button"
                    className="rec-btn"
                    onClick={() => {
                      const [lon, lat] = cellCentre(f.geometry.coordinates[0])
                      onPick(lon, lat)
                    }}
                  >
                    <span className="rec-rank">{i + 1}</span>
                    <span className="rec-body">
                      <strong>{p.district_name ?? 'Outside the districts'}</strong>
                      <span className="small">
                        <span className="swatch" style={{ background: classColour(p.class) }} /> score {Math.round(p.score)}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ol>
        </>
      )}
      <p className="muted small">
        Accessibility only: ownership, zoning, noise, flood risk and nature protection are not considered; a cell
        without residents in the 2022 census may be built up since. Candidates are grid cells inside the urban
        boundary plus a margin, outside forest, water, industrial areas, cemeteries and parks.
      </p>
    </Card>
  )
}
