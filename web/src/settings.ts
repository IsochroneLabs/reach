// Map display settings (settings panel, pin mode, collapsed cards). Display only: nothing here
// changes what is measured. Persisted per browser in localStorage; every access may throw
// (private mode, blocked storage), so the app also works with the defaults alone.
import { useCallback, useEffect, useState } from 'react'

export type IsochroneDirection = 'forward' | 'reverse' | 'both'

export interface MapSettings {
  showCells: boolean
  /** Fill opacity of the cells, 0–1 (opacity instead of saturation keeps the checked palette). */
  cellOpacity: number
  showDistricts: boolean
  /** Isochrone rings by contour minute; a ring is shown unless set to false. */
  isochroneRings: Record<string, boolean>
  isochroneDirection: IsochroneDirection
  showPois: boolean
  showRecommendations: boolean
  /** With a pin: keep the cell colours (default off: isochrone and route only). */
  coloursWithPin: boolean
  /** Cells with fewer residents are hidden on the map and left out of the legend shares. */
  minResidents: number
  /** Sidebar cards by id; a card is open unless set to false. */
  openCards: Record<string, boolean>
}

export const DEFAULT_SETTINGS: MapSettings = {
  showCells: true,
  cellOpacity: 0.8,
  showDistricts: true,
  isochroneRings: {},
  isochroneDirection: 'forward',
  showPois: true,
  showRecommendations: true,
  coloursWithPin: false,
  minResidents: 0,
  openCards: {},
}

const STORAGE_KEY = 'reach.mapSettings.v1'

/** Upper end of the residents slider (a UI choice, not a threshold). */
export const MAX_MIN_RESIDENTS = 100

const clamp = (v: number, lo: number, hi: number) => (Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : lo)

function load(): MapSettings {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_SETTINGS
    const stored = JSON.parse(raw) as Record<string, unknown>
    // unknown, mistyped or out-of-range values from an older version fall back to the defaults
    const merged = { ...DEFAULT_SETTINGS }
    for (const key of Object.keys(DEFAULT_SETTINGS) as (keyof MapSettings)[]) {
      const value = stored[key]
      const fallback = DEFAULT_SETTINGS[key]
      const plainObject = (v: unknown) => typeof v === 'object' && v !== null && !Array.isArray(v)
      if (plainObject(fallback) ? plainObject(value) : typeof value === typeof fallback)
        Object.assign(merged, { [key]: value })
    }
    if (!['forward', 'reverse', 'both'].includes(merged.isochroneDirection))
      merged.isochroneDirection = DEFAULT_SETTINGS.isochroneDirection
    merged.cellOpacity = clamp(merged.cellOpacity, 0, 1)
    merged.minResidents = clamp(Math.round(merged.minResidents), 0, MAX_MIN_RESIDENTS)
    return merged
  } catch {
    return DEFAULT_SETTINGS
  }
}

function save(settings: MapSettings) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // storage blocked or full: the settings last for this page view only
  }
}

/** Settings state shared by the app; `update` merges a partial change and persists it. */
export function useSettings() {
  const [settings, setSettings] = useState(load)
  useEffect(() => save(settings), [settings])
  const update = useCallback((change: Partial<MapSettings>) => setSettings((s) => ({ ...s, ...change })), [])
  const setCard = useCallback(
    (id: string, open: boolean) => setSettings((s) => ({ ...s, openCards: { ...s.openCards, [id]: open } })),
    [],
  )
  const reset = useCallback(() => setSettings(DEFAULT_SETTINGS), [])
  return { settings, update, setCard, reset }
}

export const ringShown = (settings: MapSettings, minute: number) => settings.isochroneRings[String(minute)] !== false
export const cardOpen = (settings: MapSettings, id: string) => settings.openCards[id] !== false
