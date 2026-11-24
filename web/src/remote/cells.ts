import { useEffect, useState } from 'react'

import { getApi } from '../api/client'
import { ApiError, type CellDetail } from '../api/types'
import { FIT_DEBOUNCE_MS } from '../settings'
import { normalise, type Place, type StudentProfile } from '../state/profile'
import { useRefs } from './refs'

export type CellState =
  | { kind: 'loading' }
  | { kind: 'ok'; detail: CellDetail; stale?: boolean }
  | { kind: 'nodata' }
  | { kind: 'error'; message: string }

type Answer = { key: string; state: CellState }

/**
 * POST /api/cell/{id} for every place (≤ 3, in parallel), the profile in the body, debounced like
 * the fit request; a newer profile aborts the older requests (docs/app_screens.md §4.5).
 */
export function useCellDetails(places: Place[], profile: StudentProfile): Record<string, CellState> {
  const refs = useRefs()
  const [answers, setAnswers] = useState<Record<string, Answer>>({})
  const types = refs.kind === 'ok' ? refs.refs.types : null
  const body = types ? normalise(profile, types) : null
  const bodyKey = body ? JSON.stringify(body) : ''
  const cellsKey = places.map((p) => p.cellId).join('|')

  useEffect(() => {
    if (!body || !cellsKey) return
    const ctrl = new AbortController()
    const ids = [...new Set(cellsKey.split('|'))]
    const timer = setTimeout(async () => {
      const api = await getApi()
      await Promise.all(
        ids.map(async (id) => {
          const key = `${id}|${bodyKey}`
          let state: CellState
          try {
            state = { kind: 'ok', detail: await api.cell(id, body, ctrl.signal) }
          } catch (e) {
            if (ctrl.signal.aborted) return
            state =
              e instanceof ApiError && e.status === 404
                ? { kind: 'nodata' }
                : { kind: 'error', message: e instanceof Error ? e.message : String(e) }
          }
          setAnswers((a) => ({ ...a, [id]: { key, state } }))
        }),
      )
    }, FIT_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
    // body is covered by bodyKey
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bodyKey, cellsKey])

  const out: Record<string, CellState> = {}
  for (const p of places) {
    const a = answers[p.cellId]
    if (a && a.key === `${p.cellId}|${bodyKey}`) out[p.id] = a.state
    // keep the previous answer visible (dimmed) while the new profile loads
    else if (a?.state.kind === 'ok') out[p.id] = { ...a.state, stale: true }
    else out[p.id] = { kind: 'loading' }
  }
  return out
}
