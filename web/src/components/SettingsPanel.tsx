// Map settings (display only): gear button at the top right of the map, below the zoom buttons;
// the popover groups cells, isochrones, layers and pin mode. Esc or a click outside closes it.
import { useEffect, useId, useRef, useState } from 'react'
import { MAX_MIN_RESIDENTS, ringShown, type IsochroneDirection, type MapSettings } from '../settings'

interface Props {
  settings: MapSettings
  onChange: (change: Partial<MapSettings>) => void
  onReset: () => void
  /** Contour minutes of the current isochrone (empty before the first pin). */
  rings: number[]
  /** Reverse isochrones need the live endpoint of W2; until then only "forward". */
  directionAvailable: boolean
}

const DIRECTIONS: { value: IsochroneDirection; label: string }[] = [
  { value: 'forward', label: 'Forward' },
  { value: 'reverse', label: 'Reverse' },
  { value: 'both', label: 'Both' },
]

export default function SettingsPanel({ settings, onChange, onReset, rings, directionAvailable }: Props) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const panelId = useId()
  const panel = useRef<HTMLDivElement>(null)

  // move focus into the panel on open, so keyboard users land on its first control
  useEffect(() => {
    if (open) panel.current?.querySelector<HTMLElement>('input, button')?.focus()
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      button.current?.focus()
    }
    const onDown = (e: PointerEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onDown)
    }
  }, [open])

  const check = (
    key: 'showCells' | 'showDistricts' | 'showPois' | 'showAllFacilities' | 'showRecommendations' | 'coloursWithPin',
    label: string,
  ) => (
    <label className="check">
      <input type="checkbox" checked={settings[key]} onChange={(e) => onChange({ [key]: e.target.checked })} />
      {label}
    </label>
  )

  return (
    <div className="settings" ref={root}>
      <button
        ref={button}
        type="button"
        className="settings-btn"
        aria-label="Map settings"
        title="Map settings"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            fill="currentColor"
            d="M19.4 13a7.5 7.5 0 0 0 0-2l2.1-1.6-2-3.5-2.5 1a7.6 7.6 0 0 0-1.7-1L15 3.3h-4l-.4 2.6a7.6 7.6 0 0 0-1.7 1l-2.5-1-2 3.5L6.6 11a7.5 7.5 0 0 0 0 2l-2.2 1.6 2 3.5 2.5-1a7.6 7.6 0 0 0 1.7 1l.4 2.6h4l.4-2.6a7.6 7.6 0 0 0 1.7-1l2.5 1 2-3.5zM13 15.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7z"
            transform="translate(-1 0)"
          />
        </svg>
      </button>
      {open && (
        <div id={panelId} ref={panel} className="settings-panel" role="dialog" aria-label="Map settings">
          <fieldset>
            <legend>Cells</legend>
            {check('showCells', 'Show cells')}
            <label className="range">
              <span>
                Opacity <span className="muted">{Math.round(settings.cellOpacity * 100)} %</span>
              </span>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={Math.round(settings.cellOpacity * 100)}
                onChange={(e) => onChange({ cellOpacity: Number(e.target.value) / 100 })}
              />
            </label>
            <label className="range">
              <span>
                Minimum residents per cell <span className="muted">{settings.minResidents}</span>
              </span>
              <input
                type="range"
                min={0}
                max={MAX_MIN_RESIDENTS}
                step={1}
                value={settings.minResidents}
                aria-describedby={`${panelId}-residents`}
                onChange={(e) => onChange({ minResidents: Number(e.target.value) })}
              />
            </label>
            <p id={`${panelId}-residents`} className="muted small">
              Zensus 2022 perturbs small counts for disclosure control, so residents of sparsely populated
              cells are approximate.
            </p>
          </fieldset>
          <fieldset>
            <legend>Isochrones</legend>
            {rings.length ? (
              <div className="check-row">
                {rings.map((m) => (
                  <label key={m} className="check">
                    <input
                      type="checkbox"
                      checked={ringShown(settings, m)}
                      onChange={(e) => onChange({ isochroneRings: { ...settings.isochroneRings, [String(m)]: e.target.checked } })}
                    />
                    {m} min
                  </label>
                ))}
              </div>
            ) : (
              <p className="muted small">Click the map to choose rings.</p>
            )}
            <div className="check-row" role="radiogroup" aria-label="Isochrone direction">
              {DIRECTIONS.map((d) => (
                <label key={d.value} className="check">
                  <input
                    type="radio"
                    name={`${panelId}-direction`}
                    value={d.value}
                    disabled={!directionAvailable && d.value !== 'forward'}
                    checked={(directionAvailable ? settings.isochroneDirection : 'forward') === d.value}
                    onChange={() => onChange({ isochroneDirection: d.value })}
                  />
                  {d.label}
                </label>
              ))}
            </div>
            {directionAvailable ? (
              <p className="muted small">Forward: where you get. Reverse: from where people reach the pin.</p>
            ) : (
              <p className="muted small">Reverse isochrones are not available yet.</p>
            )}
          </fieldset>
          <fieldset>
            <legend>Layers</legend>
            {check('showDistricts', 'District boundaries')}
            {check('showPois', 'Facility pins and routes')}
            {check('showAllFacilities', 'All facilities of the category')}
            {check('showRecommendations', 'Recommended sites')}
          </fieldset>
          <fieldset>
            <legend>With a pin</legend>
            {check('coloursWithPin', 'Show cell colours')}
          </fieldset>
          <button type="button" className="link-btn small" onClick={onReset}>
            Reset to defaults
          </button>
        </div>
      )}
    </div>
  )
}
