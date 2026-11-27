import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'

import { getApi } from '../api/client'
import { ApiError, type Listing } from '../api/types'
import { FIT_DEBOUNCE_MS } from '../settings'
import { normalise, profileKey, type StudentProfile } from '../state/profile'
import { useStore } from '../state/store'
import { useRefs } from './refs'

export interface ListingsState {
  /** "WG-Gesucht listings" toggle of Find; off by default. */
  enabled: boolean
  setEnabled: (on: boolean) => void
  /** current listings with the fit of their cell, best first; null while loading */
  data: Listing[] | null
  updating: boolean
  error: string | null
  selected: Listing | null
  select: (id: string | null) => void
  retry: () => void
}

const Ctx = createContext<ListingsState | null>(null)

/**
 * Current WG-Gesucht listings (F4.6/F4.7): the toggle loads them once per profile, debounced like
 * the fit request. A listing's numbers are the values of its 100 m cell until point routing (F4.5)
 * exists; the API marks them approximate.
 */
export function ListingsProvider({ children }: { children: ReactNode }) {
  const refs = useRefs()
  const { state } = useStore()
  const [enabled, setEnabled] = useState(false)
  const [data, setData] = useState<{ items: Listing[]; key: string } | null>(null)
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const cache = useRef(new Map<string, Listing[]>())
  const seq = useRef(0)

  const types = refs.kind === 'ok' ? refs.refs.types : null
  const key = types ? profileKey(state.profile, types) : null

  useEffect(() => {
    if (!enabled || !types || !key) return
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
  }, [enabled, key, types, attempt])

  const select = useCallback((id: string | null) => setSelectedId(id), [])
  const toggle = useCallback((on: boolean) => {
    setEnabled(on)
    if (!on) setSelectedId(null)
  }, [])
  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  // do not show a listing from a previous answer after the profile changed
  const items = data && data.key === key ? data.items : null
  const selected = items?.find((l) => l.listing_id === selectedId) ?? null

  const value: ListingsState = {
    enabled,
    setEnabled: toggle,
    data: items,
    updating: updating && enabled,
    error: enabled ? error : null,
    selected,
    select,
    retry,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useListings(): ListingsState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useListings outside ListingsProvider')
  return v
}
