// Intro, profile and category selectors plus the class legend of the current map.
import { CARD_HELP, categoryName, classPlain, profileLabel } from '../labels'
import { classColour, classLabel, legendEntries, TRANSIT } from '../palette'
import type { Cells, Meta, Profile } from '../types'
import Card from './Card'

interface Props {
  meta: Meta
  profile: Profile
  category: string
  /** Cells shown on the map (after the residents slider). */
  cells: Cells | null
  /** Number of scored cells before the residents slider. */
  allCells: number
  minResidents: number
  /** Pin mode without colours: the map shows the grid only. */
  coloursHidden: boolean
  card: { open: boolean; onToggle: (open: boolean) => void }
  loading: boolean
  error: string | null
  onProfile: (id: string) => void
  onCategory: (id: string) => void
}

export default function Controls(props: Props) {
  const { meta, profile, category, cells, allCells, minResidents, coloursHidden, card, loading, error, onProfile, onCategory } =
    props
  const transit = category === TRANSIT
  const budget = transit ? profile.transit_budget_min : profile.time_budget_min
  const entries = legendEntries(category, meta.categories, meta.transit_classes)
  const residents = new Map<string, number>()
  let total = 0
  for (const f of cells?.features ?? []) {
    residents.set(f.properties.class, (residents.get(f.properties.class) ?? 0) + f.properties.population)
    total += f.properties.population
  }
  const shown = cells?.features.length ?? 0

  return (
    <Card title="Map" label="Map selection" help={CARD_HELP.map} {...card}>
      <p className="intro">
        {transit
          ? `Each square is 100 m. Colour = how many weekday departures residents reach at stops within ${budget} minutes on foot.`
          : `Each square is 100 m. Colour = how many facilities residents reach in ${budget} minutes.`}
      </p>
      <div className="field-row">
        <label className="field">
          <span>How people travel</span>
          <select value={profile.profile_id} onChange={(e) => onProfile(e.target.value)}>
            {meta.profiles.map((p) => (
              <option key={p.profile_id} value={p.profile_id}>
                {profileLabel(p, meta.profiles)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>What they need</span>
          <select value={category} onChange={(e) => onCategory(e.target.value)}>
            {meta.categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
            {profile.transit && <option value={TRANSIT}>Public transport (departures)</option>}
          </select>
        </label>
      </div>

      <div className="legend">
        <div className="legend-title" aria-live="polite">
          {/* the transit budget (walking time to stops) differs from the facility budget */}
          {transit
            ? `Public transport: weekday departures at stops within ${profile.transit_budget_min} min`
            : `${categoryName(meta, category)} within ${profile.time_budget_min} min`}
          {loading && <span className="muted"> · loading…</span>}
        </div>
        {coloursHidden && <p className="muted small">Colours are hidden while a pin is set (switch in the Location card).</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <ul>
          {entries.map((e) => {
            const r = residents.get(e.cls) ?? 0
            return (
              <li key={e.cls}>
                <span className="swatch" style={{ background: classColour(e.cls, transit) }} />
                <span className="legend-class">
                  {classPlain(e.cls, budget, transit)}
                  <span className="muted legend-tech"> {classLabel(e.cls)}</span>
                </span>
                <span className="muted legend-rule">{e.rule}</span>
                {cells && total > 0 && (
                  <span className="legend-share" title={`${r.toLocaleString('en')} residents`}>
                    {Math.round((100 * r) / total)} %
                  </span>
                )}
              </li>
            )
          })}
        </ul>
        {cells && (
          <p className="muted small" data-testid="cells-summary">
            Share of {total.toLocaleString('en')} residents in {shown.toLocaleString('en')} scored 100 m cells
            {minResidents > 0 && (
              <>
                {' '}
                · <span data-testid="cells-shown">{shown.toLocaleString('en')} of {allCells.toLocaleString('en')} cells shown</span>{' '}
                (at least {minResidents} residents)
              </>
            )}
            . Click any square on the map to see what its residents reach.
          </p>
        )}
      </div>
    </Card>
  )
}
