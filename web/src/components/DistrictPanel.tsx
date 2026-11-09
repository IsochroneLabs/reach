// District statistics (GET /api/districts/{id}/scores): share of residents per class, residents
// lacking access, deficit sum and rank per category for the selected profile.
import { useEffect, useState } from 'react'
import { errorMessage, getDistrictScores } from '../api'
import { CARD_HELP } from '../labels'
import { classColour, FACILITY_CLASSES } from '../palette'
import type { DistrictScores, Districts, Meta } from '../types'
import Card from './Card'

interface Props {
  meta: Meta
  districts: Districts
  selected: string | null
  profile: string
  category: string
  onSelect: (id: string | null) => void
  onCategory: (id: string) => void
  /** Score view: population-weighted mean score of the selected district (null = not shown). */
  scoreMean?: number | null
  card: { open: boolean; onToggle: (open: boolean) => void }
}

type Loaded = { key: string; data: DistrictScores } | { key: string; error: string }

const pct = (v: number | null) => (v === null ? '–' : `${Math.round(v * 100)} %`)

export default function DistrictPanel({ meta, districts, selected, profile, category, onSelect, onCategory, scoreMean, card }: Props) {
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const key = selected ? `${selected}|${profile}` : null

  useEffect(() => {
    if (!selected || !key) return
    let cancelled = false
    getDistrictScores(selected, profile).then(
      (data) => !cancelled && setLoaded({ key, data }),
      (err: unknown) => !cancelled && setLoaded({ key, error: errorMessage(err) }),
    )
    return () => {
      cancelled = true
    }
  }, [selected, profile, key])

  const options = [...districts.features]
    .map((f) => f.properties)
    .sort((a, b) => a.name.localeCompare(b.name, 'de'))
  const current = loaded && loaded.key === key ? loaded : null

  return (
    <Card
      title="District"
      label="District statistics"
      help={CARD_HELP.district}
      {...card}
      extra={
        <select aria-label="District" value={selected ?? ''} onChange={(e) => onSelect(e.target.value || null)}>
          <option value="">Choose a district…</option>
          {options.map((d) => (
            <option key={d.district_id} value={d.district_id}>
              {d.name}
            </option>
          ))}
        </select>
      }
    >
      {!selected && <p className="muted small">Choose a district above, or click a square on the map to select its district.</p>}
      {selected && !current && <p className="muted small">Loading…</p>}
      {current && 'error' in current && <p className="error">{current.error}</p>}
      {current && 'data' in current && (
        <>
          <p className="muted small">
            {districts.features
              .find((f) => f.properties.district_id === selected)
              ?.properties.residents.toLocaleString('en')}{' '}
            residents · rank 1 = largest deficit of {current.data.scores[0]?.districts_ranked ?? '–'} districts
          </p>
          {scoreMean != null && (
            <p className="small" data-testid="district-score">
              Mean accessibility score of the selected categories: <strong>{Math.round(scoreMean)}</strong> of 100 (weighted by residents)
            </p>
          )}
          <table className="district-table">
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col">Residents by class</th>
                <th scope="col" title="Residents in cells with no facility of the category">
                  Lack
                </th>
                <th scope="col" title="Residents × missing share of the needed facilities, summed (rank 1 = largest)">
                  Deficit
                </th>
              </tr>
            </thead>
            <tbody>
              {current.data.scores.map((s) => {
                const shares = [s.share_lack, s.share_insufficient, s.share_sufficient]
                return (
                  <tr key={s.category} className={s.category === category ? 'selected' : undefined}>
                    <th scope="row">
                      <button type="button" className="link-btn" onClick={() => onCategory(s.category)}>
                        {meta.categories.find((c) => c.id === s.category)?.name ?? s.category}
                      </button>
                    </th>
                    <td>
                      <div
                        className="share-bar"
                        role="img"
                        aria-label={FACILITY_CLASSES.map((c, i) => `${c} ${pct(shares[i])}`).join(', ')}
                        title={FACILITY_CLASSES.map((c, i) => `${c} ${pct(shares[i])}`).join(' · ')}
                      >
                        {FACILITY_CLASSES.map((c, i) => (
                          <span key={c} style={{ width: `${(shares[i] ?? 0) * 100}%`, background: classColour(c) }} />
                        ))}
                      </div>
                    </td>
                    <td className="num">{s.residents_lack?.toLocaleString('en') ?? '–'}</td>
                    <td className="num">
                      {s.deficit_sum === null ? '–' : Math.round(s.deficit_sum).toLocaleString('en')}
                      <span className="muted"> #{s.rank_deficit ?? '–'}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </>
      )}
    </Card>
  )
}
