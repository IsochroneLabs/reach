// What people need: grouped checkboxes (food, health, education, green) with "All". One category
// gives today's class map, several give the accessibility score. Public transport has its own
// supply classes and is chosen alone.
import { useId } from 'react'
import { TRANSIT } from '../palette'
import type { Category, Profile } from '../types'

interface Props {
  categories: Category[]
  profile: Profile
  /** Selected ids in `categories` order, or [TRANSIT]. */
  selected: string[]
  onChange: (ids: string[]) => void
}

const GROUP_LABEL: Record<string, string> = { food: 'Food', health: 'Health', education: 'Education', green: 'Green space' }
const groupLabel = (g: string) => GROUP_LABEL[g] ?? g.charAt(0).toUpperCase() + g.slice(1)

export default function CategoryPicker({ categories, profile, selected, onChange }: Props) {
  const name = useId()
  const transit = selected[0] === TRANSIT
  const groups = [...new Set(categories.map((c) => c.group ?? 'other'))].map((g) => ({
    group: g,
    items: categories.filter((c) => (c.group ?? 'other') === g),
  }))
  const all = categories.map((c) => c.id)
  const allChecked = !transit && all.every((id) => selected.includes(id))
  // keep at least one category; the order follows `categories`, so the URL stays canonical
  const toggle = (id: string, on: boolean) => {
    const base = transit ? [] : selected
    const next = all.filter((c) => (c === id ? on : base.includes(c)))
    if (next.length > 0) onChange(next)
  }

  return (
    <fieldset className="picker">
      <legend>What they need</legend>
      <label className="check picker-all">
        <input
          type="checkbox"
          checked={allChecked}
          onChange={(e) => onChange(e.target.checked ? all : [selected.find((s) => s !== TRANSIT) ?? all[0]])}
        />
        All
      </label>
      {groups.map(({ group, items }) => (
        <div key={group} className="picker-group" role="group" aria-label={groupLabel(group)}>
          <div className="picker-title muted small">{groupLabel(group)}</div>
          {items.map((c) => (
            <label key={c.id} className="check">
              <input
                type="checkbox"
                name={`${name}-${c.id}`}
                checked={!transit && selected.includes(c.id)}
                onChange={(e) => toggle(c.id, e.target.checked)}
              />
              {c.name}
            </label>
          ))}
        </div>
      ))}
      {profile.transit && (
        <div className="picker-group" role="group" aria-label="Public transport">
          <label className="check">
            <input type="checkbox" checked={transit} onChange={(e) => onChange(e.target.checked ? [TRANSIT] : [all[0]])} />
            Public transport (departures)
          </label>
        </div>
      )}
    </fieldset>
  )
}
