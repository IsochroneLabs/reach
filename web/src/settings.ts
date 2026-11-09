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

function load(): MapSettings {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_SETTINGS
    const stored = JSON.parse(raw) as Partial<MapSettings>
    // unknown or mistyped keys from an older version fall back to the defaults
    const merged = { ...DEFAULT_SETTINGS }
    for (const key of Object.keys(DEFAULT_SETTINGS) as (keyof MapSettings)[])
      if (typeof stored[key] === typeof DEFAULT_SETTINGS[key]) Object.assign(merged, { [key]: stored[key] })
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
export function useSettings(): [MapSettings, (change: Partial<MapSettings>) => void, () => void] {
  const [settings, setSettings] = useState(load)
  useEffect(() => save(settings), [settings])
  const update = useCallback((change: Partial<MapSettings>) => setSettings((s) => ({ ...s, ...change })), [])
  const reset = useCallback(() => setSettings(DEFAULT_SETTINGS), [])
  return [settings, update, reset]
}

export const ringShown = (settings: MapSettings, minute: number) => settings.isochroneRings[String(minute)] !== false
export const cardOpen = (settings: MapSettings, id: string) => settings.openCards[id] !== false
