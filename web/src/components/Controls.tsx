// Profile and category selectors plus the class legend of the current map.
import { categoryName, profileLabel } from '../labels'
import { classColour, classLabel, legendEntries, TRANSIT } from '../palette'
import type { Cells, Meta, Profile } from '../types'

interface Props {
  meta: Meta
  profile: Profile
  category: string
  cells: Cells | null
  loading: boolean
  error: string | null
  onProfile: (id: string) => void
  onCategory: (id: string) => void
}

export default function Controls({ meta, profile, category, cells, loading, error, onProfile, onCategory }: Props) {
  const entries = legendEntries(category, meta.categories, meta.transit_classes)
  const residents = new Map<string, number>()
  let total = 0
  for (const f of cells?.features ?? []) {
    residents.set(f.properties.class, (residents.get(f.properties.class) ?? 0) + f.properties.population)
    total += f.properties.population
  }

  return (
    <section className="card" aria-label="Map settings">
      <div className="field-row">
        <label className="field">
          <span>Profile</span>
          <select value={profile.profile_id} onChange={(e) => onProfile(e.target.value)}>
            {meta.profiles.map((p) => (
              <option key={p.profile_id} value={p.profile_id}>
                {profileLabel(p)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Category</span>
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
          {category === TRANSIT
            ? `Public transport: weekday departures at stops within ${profile.transit_budget_min} min`
            : `${categoryName(meta, category)} within ${profile.time_budget_min} min`}
          {loading && <span className="muted"> · loading…</span>}
        </div>
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
                <span className="swatch" style={{ background: classColour(e.cls, category === TRANSIT) }} />
                <span className="legend-class">{classLabel(e.cls)}</span>
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
            Share of {total.toLocaleString('en')} residents in {cells.features.length.toLocaleString('en')} scored
            100 m cells. Click the map to inspect a location.
          </p>
        )}
      </div>
    </section>
  )
}
