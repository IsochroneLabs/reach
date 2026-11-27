import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import { getApi } from '../api/client'
import type { CampusSite, DestinationType, LabelDestination, Meta, Persona, Programme } from '../api/types'
import { resolveKey } from '../state/labels'
import { useI18n } from '../i18n/i18n'

/** Reference data of the published run, loaded once per session (docs/app_screens.md §4.1). */
export interface Refs {
  meta: Meta
  types: DestinationType[]
  sites: CampusSite[]
  programmes: Programme[]
  personas: Persona[]
  /** PROPOSED (F2.4): labelled destinations for the map */
  labelDestinations: LabelDestination[]
}

export type RefsState =
  | { kind: 'loading' }
  | { kind: 'ok'; refs: Refs }
  | { kind: 'error'; message: string; retry: () => void }

const Ctx = createContext<RefsState>({ kind: 'loading' })

export function RefsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<RefsState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const retry = useCallback(() => {
    setState({ kind: 'loading' })
    setAttempt((n) => n + 1)
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    getApi()
      .then((api) =>
        Promise.all([
          api.meta(ctrl.signal),
          api.destinationTypes(ctrl.signal),
          api.campusSites(ctrl.signal),
          api.programmes(ctrl.signal),
          api.personas(ctrl.signal),
          api.labelDestinations(ctrl.signal),
        ]),
      )
      .then(([meta, types, sites, programmes, personas, labelDestinations]) =>
        setState({ kind: 'ok', refs: { meta, types, sites, programmes, personas, labelDestinations } }),
      )
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return
        setState({ kind: 'error', message: e instanceof Error ? e.message : String(e), retry })
      })
    return () => ctrl.abort()
  }, [attempt, retry])

  return <Ctx.Provider value={state}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useRefs(): RefsState {
  return useContext(Ctx)
}

/** Display name of a profile key: a destination type or a sport/hobby category ("Tennis"). */
// eslint-disable-next-line react-refresh/only-export-components
export function useDestName(): (key: string) => string {
  const refs = useContext(Ctx)
  const { label } = useI18n()
  return (key: string) => {
    const r = refs.kind === 'ok' ? resolveKey(key, refs.refs.types) : null
    return r ? label(r.name) : key
  }
}
