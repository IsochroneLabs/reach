import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'

import { getApi } from '../api/client'
import { ApiError, type FitResponse } from '../api/types'
import { FIT_CACHE_SIZE, FIT_DEBOUNCE_MS } from '../settings'
import { hasWeight, normalise, profileKey, type StudentProfile } from '../state/profile'
import { useStore } from '../state/store'
import { useRefs } from './refs'

export type FitError =
  | { kind: 'server'; message: string }
  | { kind: 'invalid'; message: string }
  | { kind: 'rate'; retryInS: number }

export interface FitState {
  /** the latest successful response (kept while a newer request runs or fails) */
  data: FitResponse | null
  /** profile key of `data` */
  dataKey: string | null
  updating: boolean
  error: FitError | null
  /** all destinations "not important": nothing to score */
  noWeight: boolean
  retry: () => void
}

const Ctx = createContext<FitState | null>(null)

/**
 * The fit request flow of docs/app_screens.md §4.2: normalise → cache → debounce → abort the
 * in-flight request → POST /api/fit → keep the newest answer only. One request at a time for the
 * whole app (Find colours and the rank in Check share it).
 */
export function FitProvider({ children }: { children: ReactNode }) {
  const refs = useRefs()
  const { state } = useStore()
  const [data, setData] = useState<{ res: FitResponse; key: string } | null>(null)
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState<FitError | null>(null)
  const [attempt, setAttempt] = useState(0)
  const cache = useRef(new Map<string, FitResponse>())
  const seq = useRef(0)

  const types = refs.kind === 'ok' ? refs.refs.types : null
  const key = types ? profileKey(state.profile, types) : null
  const noWeight = !hasWeight(state.profile)
  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  useEffect(() => {
    if (!types || !key || noWeight) return
    const hit = cache.current.get(key)
    if (hit) {
      setData({ res: hit, key })
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
        const res = await api.fit(body, ctrl.signal)
        if (my !== seq.current) return
        cache.current.set(key, res)
        while (cache.current.size > FIT_CACHE_SIZE) cache.current.delete(cache.current.keys().next().value!)
        setData({ res, key })
        setError(null)
        setUpdating(false)
      } catch (e) {
        if (ctrl.signal.aborted || my !== seq.current) return
        setUpdating(false)
        if (e instanceof ApiError && e.status === 429) setError({ kind: 'rate', retryInS: e.retryAfterS ?? 5 })
        else if (e instanceof ApiError && e.status === 422) {
          console.warn('POST /api/fit rejected the profile:', e.message)
          setError({ kind: 'invalid', message: e.message })
        } else setError({ kind: 'server', message: e instanceof Error ? e.message : String(e) })
      }
    }, FIT_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
    // state.profile is covered by key; attempt re-runs after Retry
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, types, noWeight, attempt])

  // 429: count down Retry-After, then send once more.
  useEffect(() => {
    if (error?.kind !== 'rate') return
    const h = setTimeout(() => {
      if (error.retryInS <= 1) {
        setError(null)
        retry()
      } else setError({ kind: 'rate', retryInS: error.retryInS - 1 })
    }, 1000)
    return () => clearTimeout(h)
  }, [error, retry])

  const value: FitState = {
    data: data?.res ?? null,
    dataKey: data?.key ?? null,
    updating: updating && !noWeight,
    error: noWeight ? null : error,
    noWeight,
    retry,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useFit(): FitState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useFit outside FitProvider')
  return v
}
