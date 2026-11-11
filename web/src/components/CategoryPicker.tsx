// What people need: collapsible groups of category checkboxes with "All". Each group header
// has a checkbox for the whole group and shows how many of its categories are selected. One
// category gives today's class map, several give the accessibility score. Public transport has
// its own supply classes and is chosen alone.
import { useEffect, useId, useRef, useState } from 'react'
import { TRANSIT } from '../palette'
import type { Category, Profile } from '../types'

interface Props {
  categories: Category[]
  profile: Profile
  /** Selected ids in `categories` order, or [TRANSIT]. */
  selected: string[]
  onChange: (ids: string[]) => void
}

// Display labels and order of the config groups; unknown groups follow, capitalised.
const GROUP_LABEL: Record<string, string> = {
  food: 'Food',
  health: 'Health & care',
  education: 'Education',
  green: 'Green space',
  sport: 'Sport',
  services: 'Services',
}
const GROUP_ORDER = Object.keys(GROUP_LABEL)
const groupLabel = (g: string) => GROUP_LABEL[g] ?? g.charAt(0).toUpperCase() + g.slice(1)
const groupRank = (g: string) => (GROUP_ORDER.includes(g) ? GROUP_ORDER.indexOf(g) : GROUP_ORDER.length)

interface TriStateProps {
  label: string
  count: number
  total: number
  onChange: (on: boolean) => void
}

/** Checkbox for several categories: checked with all, indeterminate with some of them. */
function TriStateCheckbox({ label, count, total, onChange }: TriStateProps) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = count > 0 && count < total
  }, [count, total])
  return <input ref={ref} type="checkbox" aria-label={label} checked={total > 0 && count === total} onChange={(e) => onChange(e.target.checked)} />
}

export default function CategoryPicker({ categories, profile, selected, onChange }: Props) {
  const name = useId()
  const transit = selected[0] === TRANSIT
  const chosen = transit ? [] : selected
  const groups = [...new Set(categories.map((c) => c.group ?? 'other'))]
    .sort((a, b) => groupRank(a) - groupRank(b))
    .map((g) => ({ group: g, items: categories.filter((c) => (c.group ?? 'other') === g) }))
  const all = categories.map((c) => c.id)
  // groups with a selected category start open; afterwards only the header buttons change this
  const [open, setOpen] = useState<Set<string>>(
    () => new Set(groups.filter((g) => g.items.some((c) => chosen.includes(c.id))).map((g) => g.group)),
  )
  const flip = (g: string) =>
    setOpen((prev) => {
      const next = new Set(prev)
      if (!next.delete(g)) next.add(g)
      return next
    })
  // keep at least one category; the order follows `categories`, so the URL stays canonical
  const setMany = (ids: string[], on: boolean) => {
    const next = all.filter((c) => (ids.includes(c) ? on : chosen.includes(c)))
    if (next.length > 0) onChange(next)
  }

  return (
    <fieldset className="picker">
      <legend>What they need</legend>
      <div className="picker-head">
        <label className="check picker-all">
          <TriStateCheckbox
            label="All"
            count={chosen.length}
            total={all.length}
            onChange={(on) => onChange(on ? all : [chosen[0] ?? all[0]])}
          />
          All
        </label>
        <span className="muted small" data-testid="picker-count">
          {transit ? 'Public transport' : `${chosen.length} of ${all.length} selected`}
        </span>
      </div>
      <div className="picker-list">
        {groups.map(({ group, items }) => {
          const label = groupLabel(group)
          const ids = items.map((c) => c.id)
          const count = ids.filter((id) => chosen.includes(id)).length
          const isOpen = open.has(group)
          const bodyId = `${name}-${group}`
          return (
            <div key={group} className={`picker-group${count > 0 ? ' active' : ''}`} role="group" aria-label={label}>
              <div className="picker-row">
                <TriStateCheckbox label={`Whole group: ${label}`} count={count} total={ids.length} onChange={(on) => setMany(ids, on)} />
                <button type="button" className="picker-toggle" aria-expanded={isOpen} aria-controls={bodyId} onClick={() => flip(group)}>
                  <span className="picker-title">{label}</span>
                  <span className="picker-badge">
                    {count}/{ids.length}
                  </span>
                  <span className="chevron" aria-hidden="true">
                    {isOpen ? '▾' : '▸'}
                  </span>
                </button>
              </div>
              <div id={bodyId} className="picker-items" hidden={!isOpen}>
                {items.map((c) => (
                  <label key={c.id} className="check">
                    <input
                      type="checkbox"
                      name={`${name}-${c.id}`}
                      checked={chosen.includes(c.id)}
                      onChange={(e) => setMany([c.id], e.target.checked)}
                    />
                    {c.name}
                  </label>
                ))}
              </div>
            </div>
          )
        })}
        {profile.transit && (
          <div className={`picker-group${transit ? ' active' : ''}`} role="group" aria-label="Public transport">
            <label className="check picker-row">
              <input type="checkbox" checked={transit} onChange={(e) => onChange(e.target.checked ? [TRANSIT] : [all[0]])} />
              <span className="picker-title">Public transport</span>
              <span className="muted small">departures, shown alone</span>
            </label>
          </div>
        )}
      </div>
    </fieldset>
  )
}
