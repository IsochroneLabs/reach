import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'

import { getApi } from '../api/client'
import { ApiError, type Listing, type LonLat, type Mode } from '../api/types'
import { FIT_DEBOUNCE_MS } from '../settings'
import { normalise, profileKey, type StudentProfile } from '../state/profile'
import { useStore } from '../state/store'
import { useRefs } from './refs'

/** One live route line drawn on the map (F4.5): walk or bike only. */
export interface RouteLine {
  key: string
  coordinates: LonLat[]
  mode: Mode
}

export interface ListingsState {
  /** current listings with the fit of their cell, best first; null while loading */
  data: Listing[] | null
  updating: boolean
  error: string | null
  selected: Listing | null
  select: (id: string | null) => void
  retry: () => void
  /** routes of the selected listing's fastest trips, drawn by the map */
  routes: RouteLine[]
  setRoutes: (lines: RouteLine[]) => void
}

const Ctx = createContext<ListingsState | null>(null)

/**
 * Current WG-Gesucht listings (F4.6/F4.7), loaded once per profile and debounced like the fit
 * request. They are the primary Find result: no toggle. A listing's numbers in the list are the
 * values of its 100 m cell; the detail routes the point (F4.5).
 */
export function ListingsProvider({ children }: { children: ReactNode }) {
  const refs = useRefs()
  const { state } = useStore()
  const [data, setData] = useState<{ items: Listing[]; key: string } | null>(null)
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [routes, setRoutesState] = useState<RouteLine[]>([])
  const [attempt, setAttempt] = useState(0)
  const cache = useRef(new Map<string, Listing[]>())
  const seq = useRef(0)

  const types = refs.kind === 'ok' ? refs.refs.types : null
  const key = types ? profileKey(state.profile, types) : null

  useEffect(() => {
    if (!types || !key) return
    const hit = cache.current.get(key)
    if (hit) {
      setData({ items: hit, key })
      setUpdating(false)
      setError(null)
      return
    }
    const body: StudentProfile = normalise(state.profile, types)
    const ctrl = new AbortController()
    const my = ++seq.current
    setUpdating(true)
    const timer = setTimeout(async () => {
      try {
        const api = await getApi()
        const items = await api.listings(body, ctrl.signal)
        if (my !== seq.current) return
        cache.current.set(key, items)
        setData({ items, key })
        setError(null)
        setUpdating(false)
      } catch (e) {
        if (ctrl.signal.aborted || my !== seq.current) return
        setUpdating(false)
        const message = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e)
        setError(message)
      }
    }, FIT_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
    // state.profile is covered by key; attempt re-runs after an error
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, types, attempt])

  const select = useCallback((id: string | null) => {
    setSelectedId(id)
    setRoutesState([])
  }, [])
  const setRoutes = useCallback((lines: RouteLine[]) => setRoutesState(lines), [])
  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  // do not show a listing from a previous answer after the profile changed
  const items = data && data.key === key ? data.items : null
  const selected = items?.find((l) => l.listing_id === selectedId) ?? null

  const value: ListingsState = {
    data: items,
    updating,
    error,
    selected,
    select,
    retry,
    routes,
    setRoutes,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useListings(): ListingsState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useListings outside ListingsProvider')
  return v
}
