import { useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'

import type { CampusSite, Programme } from '../api/types'
import { useI18n } from '../i18n/i18n'
import { matchProgrammes, shortName } from '../logic/programmes'

const MAX_OPTIONS = 40

/**
 * Search over the Alma programmes (N31): a combobox with a list of matches. The chosen programme
 * shows where its sessions are and what the weights are based on.
 */
export function ProgrammePicker({
  inputId,
  programmes,
  sites,
  value,
  onChange,
  describedBy,
}: {
  inputId: string
  programmes: Programme[]
  sites: CampusSite[]
  value: string | null
  onChange: (programme: string | null) => void
  describedBy?: string
}) {
  const { t, label } = useI18n()
  const id = useId()
  const input = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState<string | null>(null) // null = not typing
  const [active, setActive] = useState(0)
  const chosen = programmes.find((p) => p.programme === value) ?? null
  const items = useMemo(() => programmes.map((p) => ({ id: p.programme, text: label(p.label) })), [programmes, label])
  const matches = useMemo(
    () => (query === null ? [] : matchProgrammes(items, query).slice(0, MAX_OPTIONS)),
    [items, query],
  )
  const open = query !== null && query.trim().length > 0
  const textOf = (pid: string) => items.find((x) => x.id === pid)?.text ?? pid

  const pick = (pid: string) => {
    onChange(pid)
    setQuery(null)
  }
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' && open) setActive((a) => Math.min(a + 1, matches.length - 1))
    else if (e.key === 'ArrowUp' && open) setActive((a) => Math.max(a - 1, 0))
    else if (e.key === 'Enter' && open && matches[active]) pick(matches[active])
    else if (e.key === 'Escape') setQuery(null)
    else return
    e.preventDefault()
  }

  return (
    <div className="programme-picker">
      <div className="programme-input">
        <input
          ref={input}
          id={inputId}
          type="text"
          role="combobox"
          autoComplete="off"
          spellCheck={false}
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-activedescendant={open && matches[active] ? `${id}-${matches[active]}` : undefined}
          aria-describedby={describedBy}
          placeholder={t('profile.programme.search')}
          value={query ?? (chosen ? label(chosen.label) : '')}
          onChange={(e) => {
            setQuery(e.target.value)
            setActive(0)
          }}
          onFocus={(e) => e.target.select()}
          onBlur={() => setQuery(null)}
          onKeyDown={onKey}
        />
        {chosen && query === null && (
          <button
            type="button"
            className="programme-clear"
            aria-label={t('profile.programme.clear')}
            title={t('profile.programme.clear')}
            onClick={() => {
              onChange(null)
              input.current?.focus()
            }}
          >
            <span aria-hidden="true">×</span>
          </button>
        )}
      </div>
      <ul id={`${id}-list`} role="listbox" className="programme-list" hidden={!open} aria-label={t('profile.programme')}>
        {open && matches.length === 0 && <li className="muted small programme-none">{t('profile.programme.noMatch')}</li>}
        {matches.map((pid, i) => (
          <li
            key={pid}
            id={`${id}-${pid}`}
            role="option"
            aria-selected={i === active}
            className={i === active ? 'is-active' : undefined}
            onMouseDown={(e) => e.preventDefault()}
            onMouseEnter={() => setActive(i)}
            onClick={() => pick(pid)}
          >
            {textOf(pid)}
          </li>
        ))}
      </ul>
      {chosen && <ProgrammeBuildings programme={chosen} sites={sites} />}
    </div>
  )
}

/** "Weighted by compulsory courses: Neue Aula 40 %, Kupferbau 30 %, …" */
function ProgrammeBuildings({ programme, sites }: { programme: Programme; sites: CampusSite[] }) {
  const { t } = useI18n()
  const n = programme.sites.length
  const shares = programme.shares?.length === n ? programme.shares : programme.sites.map(() => 1 / n)
  const names = new Map(sites.map((s) => [s.site_id, shortName(s.name)]))
  const parts = programme.sites.map((s, i) => `${names.get(s) ?? s} ${Math.round(shares[i] * 100)} %`)
  return (
    <p className="muted small programme-buildings" data-testid="programme-buildings">
      {t(`profile.programme.basis.${programme.basis ?? 'override'}`)} {parts.join(', ')}
    </p>
  )
}
