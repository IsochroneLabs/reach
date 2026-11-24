import { useId, useState } from 'react'

import type { DestinationType, Importance, Mode } from '../api/types'
import { useRefs, type Refs } from '../remote/refs'
import { useI18n } from '../i18n/i18n'
import { defaultProfile, normalise, type StudentProfile } from '../state/profile'
import { useStore } from '../state/store'
import { ModeIcon, TripWindowText } from './Minutes'
import { useToast } from './Toast'

const IMPORTANCE: Importance[] = [0, 1, 2, 3]
const FINE_MIN = 5
const FINE_MAX = 60
const TRIPS_MAX = 14

/** Names of the default campus sites, e.g. "Tal and Morgenstelle". */
function useCampusMix(refs: Refs | null): string {
  const { lang } = useI18n()
  if (!refs) return ''
  const names = refs.sites
    .filter((s) => (s.default_share ?? 0) > 0)
    .map((s) => s.name.replace(/\s*\(.*\)$/, ''))
  const and = lang === 'de' ? ' und ' : ' and '
  return names.length > 1 ? `${names.slice(0, -1).join(', ')}${and}${names[names.length - 1]}` : (names[0] ?? '')
}

/** The highlighted programme hint (panel top on desktop, above the sheet tabs on phones). */
export function ProgrammeHint({ compact, onOpen }: { compact?: boolean; onOpen?: () => void }) {
  const { t } = useI18n()
  const { state } = useStore()
  if (state.profile.programme) return null
  if (compact) {
    return (
      <button type="button" className="hint hint-compact" onClick={onOpen} data-testid="programme-hint">
        <span aria-hidden="true">!</span> {t('profile.programme.hint')}
      </button>
    )
  }
  return null
}

function ProgrammeField({ refs }: { refs: Refs }) {
  const { t, label } = useI18n()
  const { state, dispatch } = useStore()
  const id = useId()
  const mix = useCampusMix(refs)
  const empty = !state.profile.programme
  const programmes = [...refs.programmes].sort((a, b) => label(a.label).localeCompare(label(b.label)))
  return (
    <div className={`field programme${empty ? ' programme-empty' : ''}`}>
      <label htmlFor={id} className="field-label">
        {t('profile.programme')}
      </label>
      {empty && (
        <p className="hint-text" id={`${id}-hint`} data-testid="programme-hint-panel">
          {t('profile.programme.hint')}
        </p>
      )}
      <select
        id={id}
        value={state.profile.programme ?? ''}
        aria-describedby={empty ? `${id}-hint` : undefined}
        onChange={(e) =>
          dispatch({ type: 'profile', profile: { ...state.profile, programme: e.target.value || null } })
        }
      >
        <option value="">{t('profile.programme.none')}</option>
        {programmes.map((p) => (
          <option key={p.programme} value={p.programme}>
            {label(p.label)}
          </option>
        ))}
      </select>
      {empty && mix && <p className="muted small">{t('profile.campusMix', { sites: mix })}</p>}
    </div>
  )
}

function ModeToggles({ modes }: { modes: Mode[] }) {
  const { t } = useI18n()
  const { state, dispatch } = useStore()
  const chosen = state.profile.modes
  return (
    <fieldset className="field">
      <legend className="field-label">{t('profile.modes')}</legend>
      <div className="chips">
        {modes.map((m) => {
          const on = chosen.includes(m)
          const last = on && chosen.length === 1
          return (
            <button
              key={m}
              type="button"
              className="chip"
              aria-pressed={on}
              aria-disabled={last}
              title={last ? t('profile.modes.min') : undefined}
              onClick={() => {
                if (last) return
                const next = on ? chosen.filter((x) => x !== m) : [...chosen, m]
                dispatch({ type: 'profile', profile: { ...state.profile, modes: next } })
              }}
            >
              <ModeIcon mode={m} title="" />
              {t(`mode.${m}`)}
            </button>
          )
        })}
      </div>
      {chosen.length === 1 && <p className="muted small">{t('profile.modes.min')}</p>}
    </fieldset>
  )
}

function ImportancePicker({ name, value, onChange }: { name: string; value: Importance; onChange: (v: Importance) => void }) {
  const { t } = useI18n()
  const id = useId()
  return (
    <div className="importance" role="radiogroup" aria-label={t('importance.label', { name })}>
      {IMPORTANCE.map((v) => (
        <label key={v} className="importance-step" title={t(`importance.${v}`)}>
          <input
            type="radio"
            name={id}
            value={v}
            checked={value === v}
            onChange={() => onChange(v)}
            className="visually-hidden"
          />
          <span className={`importance-dot${v > 0 && v <= value ? ' on' : ''}${v === 0 ? ' zero' : ''}`} aria-hidden="true" />
          <span className="visually-hidden">{t(`importance.${v}`)}</span>
        </label>
      ))}
      <span className="importance-text">{t(`importance.${value}`)}</span>
    </div>
  )
}

function DestinationRow({ type, profile }: { type: DestinationType; profile: StudentProfile }) {
  const { t, label, num } = useI18n()
  const { dispatch } = useStore()
  const [open, setOpen] = useState(false)
  const v = profile.destinations[type.destination_type]
  const name = label(type.label)
  const fine = v.fine_time_min ?? type.fine_time_min
  const trips = v.trips_per_week ?? type.trips_per_week
  const detailsId = useId()
  const set = (patch: Partial<typeof v>) =>
    dispatch({
      type: 'profile',
      profile: { ...profile, destinations: { ...profile.destinations, [type.destination_type]: { ...v, ...patch } } },
    })
  const remove = () => {
    const rest = { ...profile.destinations }
    delete rest[type.destination_type]
    dispatch({ type: 'profile', profile: { ...profile, destinations: rest } })
  }
  return (
    <li className="dest" data-testid={`dest-${type.destination_type}`}>
      <div className="dest-main">
        <button
          type="button"
          className="dest-name"
          aria-expanded={open}
          aria-controls={detailsId}
          aria-label={t('profile.destinations.details', { name })}
          onClick={() => setOpen((o) => !o)}
        >
          <span className={`chev${open ? ' open' : ''}`} aria-hidden="true">›</span>
          {name}
        </button>
        <ImportancePicker name={name} value={v.importance} onChange={(importance) => set({ importance })} />
      </div>
      <div id={detailsId} className="dest-details" hidden={!open}>
        <label className="slider">
          <span>
            {t('profile.fineTime')} <strong>{t('profile.fineTime.value', { min: fine })}</strong>
          </span>
          <input
            type="range"
            min={FINE_MIN}
            max={FINE_MAX}
            step={5}
            value={fine}
            onChange={(e) => set({ fine_time_min: Number(e.target.value) })}
          />
        </label>
        <label className="inline-num">
          <span>{t('profile.tripsPerWeek')}</span>
          <input
            type="number"
            min={0}
            max={TRIPS_MAX}
            step={trips < 1 ? 0.1 : 1}
            inputMode="decimal"
            value={num(trips, 1).replace(',', '.')}
            onChange={(e) => {
              const x = Number(e.target.value)
              if (Number.isFinite(x) && x >= 0 && x <= TRIPS_MAX) set({ trips_per_week: x })
            }}
          />
        </label>
        <p className="muted small">
          {t('profile.when')}: <TripWindowText window={type.trip_window} />
        </p>
        <button type="button" className="btn-link small" onClick={remove}>
          {t('profile.destinations.remove', { name })}
        </button>
      </div>
    </li>
  )
}

function AddDestination({ refs }: { refs: Refs }) {
  const { t, label } = useI18n()
  const { state, dispatch } = useStore()
  const id = useId()
  const missing = refs.types.filter((x) => !(x.destination_type in state.profile.destinations))
  if (!missing.length) return <p className="muted small">{t('profile.destinations.addNone')}</p>
  return (
    <div className="add-dest">
      <label htmlFor={id} className="visually-hidden">
        {t('profile.destinations.add')}
      </label>
      <select
        id={id}
        value=""
        onChange={(e) => {
          const k = e.target.value
          if (!k) return
          dispatch({
            type: 'profile',
            profile: { ...state.profile, destinations: { ...state.profile.destinations, [k]: { importance: 2 } } },
          })
        }}
      >
        <option value="">+ {t('profile.destinations.add')}</option>
        {missing.map((x) => (
          <option key={x.destination_type} value={x.destination_type}>
            {label(x.label)}
          </option>
        ))}
      </select>
    </div>
  )
}

function ExampleProfiles({ refs }: { refs: Refs }) {
  const { t, label } = useI18n()
  const { state, dispatch } = useStore()
  const toast = useToast()
  const current = JSON.stringify(normalise(state.profile, refs.types))
  const apply = (profile: StudentProfile, text: string) => {
    const previous = state.profile
    dispatch({ type: 'profile', profile })
    toast(text, { label: t('profile.undo'), run: () => dispatch({ type: 'profile', profile: previous }) })
  }
  return (
    <details className="examples">
      <summary>{t('profile.examples')}</summary>
      <ul className="plain">
        {refs.personas.map((p) => {
          const profile = { ...p.profile, programme: p.profile.programme ?? null } as StudentProfile
          const active = JSON.stringify(normalise(profile, refs.types)) === current
          return (
            <li key={p.persona}>
              <button
                type="button"
                className="example"
                aria-pressed={active}
                onClick={() => apply(profile, t('profile.examples.applied', { name: label(p.label) }))}
              >
                {label(p.label)}
              </button>
            </li>
          )
        })}
      </ul>
      <button
        type="button"
        className="btn-link small"
        onClick={() => apply(defaultProfile(refs.meta.modes.filter((m) => m !== 'bike_transit')), t('profile.reset.done'))}
      >
        {t('profile.reset')}
      </button>
    </details>
  )
}

/** The student profile, edited live next to the map (docs/app_screens.md §2.2). */
export function ProfilePanel({ onClose }: { onClose?: () => void }) {
  const { t, label } = useI18n()
  const refsState = useRefs()
  const { state } = useStore()
  const refs = refsState.kind === 'ok' ? refsState.refs : null
  const chosen = refs
    ? refs.types
        .filter((x) => x.destination_type in state.profile.destinations)
        .sort((a, b) =>
          a.destination_type === 'campus_site'
            ? -1
            : b.destination_type === 'campus_site'
              ? 1
              : label(a.label).localeCompare(label(b.label)),
        )
    : []

  return (
    <section className="panel" aria-labelledby="profile-title" data-testid="profile-panel">
      <div className="panel-head">
        <h2 id="profile-title">{t('profile.title')}</h2>
        {onClose && (
          <button type="button" className="btn-icon" aria-label={t('profile.close')} onClick={onClose}>
            ×
          </button>
        )}
      </div>
      {!refs && <p className="muted">{t('status.loading')}</p>}
      {refs && (
        <>
          <ProgrammeField refs={refs} />
          <ModeToggles modes={refs.meta.modes} />
          <div className="field">
            <h3 className="field-label">{t('profile.destinations')}</h3>
            <ul className="plain dests">
              {chosen.map((x) => (
                <DestinationRow key={x.destination_type} type={x} profile={state.profile} />
              ))}
            </ul>
            <AddDestination refs={refs} />
          </div>
          <ExampleProfiles refs={refs} />
        </>
      )}
    </section>
  )
}
