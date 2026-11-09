// Score settings (methodology §4b): time threshold, facilities needed and weight per category.
// Everything is computed in the browser (`score.ts`); the values live in the URL hash.
import { useState } from 'react'
import { CARD_HELP } from '../labels'
import { effective, isDefault, type CategoryParams, type ScoreParams } from '../score'
import type { Category } from '../types'
import Card from './Card'

interface Props {
  categories: Category[]
  params: ScoreParams
  /** Facility budget of the profile (minutes): the largest possible threshold. */
  budgetMin: number
  /** Largest number of facilities per category the API delivers times for. */
  maxK: number
  /** All weights are 0: nothing can be scored. */
  noWeight?: boolean
  card: { open: boolean; onToggle: (open: boolean) => void }
  onChange: (next: ScoreParams) => void
}

const MIN_T = 5

/** Number input that lets you clear and retype: the typed text is kept until blur, a valid number
 * is committed at once. */
function NumberField(props: { value: number; min: number; max?: number; step: number; label: string; onValue: (n: number) => void }) {
  const { value, min, max, step, label, onValue } = props
  const [draft, setDraft] = useState<string | null>(null)
  return (
    <input
      type="number"
      min={min}
      max={max}
      step={step}
      value={draft ?? value}
      aria-label={label}
      onChange={(e) => {
        setDraft(e.target.value)
        const n = Number(e.target.value)
        if (e.target.value !== '' && Number.isFinite(n)) onValue(n)
      }}
      onBlur={() => setDraft(null)}
    />
  )
}

export default function ScorePanel({ categories, params, budgetMin, maxK, noWeight, card, onChange }: Props) {
  const globalT = params.t ?? budgetMin
  const setGlobal = (t: number) => onChange({ ...params, t: t >= budgetMin ? null : t })
  // a value equal to its default is not stored, so the hash stays empty until something changes
  const setCat = (cat: Category, field: keyof CategoryParams, value: number | undefined, def: number) => {
    const o: CategoryParams = { ...params.cats[cat.id], [field]: value === undefined || value === def ? undefined : value }
    const cats = { ...params.cats, [cat.id]: o }
    onChange({ ...params, cats })
  }
  const num = (raw: string) => (raw === '' || !Number.isFinite(Number(raw)) ? undefined : Number(raw))

  return (
    <Card title="Score settings" label="Score settings" help={CARD_HELP.score} {...card}>
      <label className="field">
        <span>
          Time within reach: <strong data-testid="score-threshold">{globalT} min</strong>
        </span>
        <input
          type="range"
          min={MIN_T}
          max={budgetMin}
          step={1}
          value={globalT}
          aria-label="Time within reach (minutes)"
          onChange={(e) => setGlobal(Number(e.target.value))}
        />
      </label>
      <p className="muted small">
        At most {budgetMin} minutes: the routing only stores facilities within the budget, so a longer time cannot be shown.
      </p>
      {noWeight && (
        <p className="error" role="alert">
          Set at least one weight above 0, otherwise nothing is scored.
        </p>
      )}
      <table className="score-table">
        <thead>
          <tr>
            <th scope="col">Category</th>
            <th scope="col">Minutes</th>
            <th scope="col">Needed</th>
            <th scope="col">Weight</th>
          </tr>
        </thead>
        <tbody>
          {categories.map((c) => {
            const e = effective(params, c, budgetMin, maxK)
            const own = params.cats[c.id] ?? {}
            return (
              <tr key={c.id}>
                <th scope="row">{c.name}</th>
                <td>
                  <input
                    type="number"
                    min={1}
                    max={budgetMin}
                    step={1}
                    value={own.t ?? ''}
                    placeholder={String(globalT)}
                    aria-label={`${c.name}: minutes`}
                    onChange={(ev) => setCat(c, 't', Math.min(budgetMin, num(ev.target.value) ?? NaN) || undefined, budgetMin)}
                  />
                </td>
                <td>
                  <NumberField
                    value={e.k}
                    min={1}
                    max={maxK}
                    step={1}
                    label={`${c.name}: facilities needed`}
                    onValue={(n) => setCat(c, 'k', Math.min(maxK, Math.max(1, Math.round(n))), Math.min(maxK, c.k))}
                  />
                </td>
                <td>
                  <NumberField value={e.w} min={0} step={0.5} label={`${c.name}: weight`} onValue={(n) => setCat(c, 'w', Math.max(0, n), 1)} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <button type="button" className="link-btn" disabled={isDefault(params)} onClick={() => onChange({ t: null, cats: {} })}>
        Reset score settings
      </button>
    </Card>
  )
}
