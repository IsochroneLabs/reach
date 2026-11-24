import { createContext, useContext, useEffect, useMemo, useReducer, type Dispatch, type ReactNode } from 'react'

import { cellIdAt } from '../geo/laea'
import { MAX_PLACES } from '../settings'
import { decodeHash, encodeHash } from './hash'
import { defaultProfile, PLACE_IDS, type Place, type PlaceId, type StudentProfile } from './profile'
import { storage } from './storage'

export type AppMode = 'find' | 'check'

export interface AppState {
  profile: StudentProfile
  places: Place[]
  mode: AppMode
  /** Find: outline the better cells around this place */
  nearbyOf: PlaceId | null
  /** Find → Check transition: the map flies here */
  focus: [number, number] | null
  shareRents: boolean
  /** set on load: the link had parts that could not be read */
  badLink: boolean
  /** set on load: the profile came from the link and replaced a stored one */
  replacedProfile: StudentProfile | null
}

export type Action =
  | { type: 'profile'; profile: StudentProfile }
  | { type: 'mode'; mode: AppMode }
  | { type: 'addPlace'; place: Omit<Place, 'id' | 'rentEur'>; replace?: PlaceId }
  | { type: 'updatePlace'; id: PlaceId; patch: Partial<Pick<Place, 'label' | 'rentEur'>> }
  | { type: 'removePlace'; id: PlaceId }
  | { type: 'nearby'; id: PlaceId | null }
  | { type: 'focus'; point: [number, number] | null }
  | { type: 'shareRents'; on: boolean }
  | { type: 'ackLoad' }

const PROFILE_KEY = 'reach.v1.profile'
const PLACES_KEY = 'reach.v1.places'

const modeFromPath = (path: string): AppMode => (/^\/check\/?$/.test(path) ? 'check' : 'find')
const pathOf = (mode: AppMode) => (mode === 'check' ? '/check' : '/')

function readJson<T>(key: string): T | null {
  const raw = storage.get(key)
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function initialState(): AppState {
  const fromHash = decodeHash(window.location.hash, cellIdAt)
  const stored = readJson<StudentProfile>(PROFILE_KEY)
  const storedPlaces = readJson<Place[]>(PLACES_KEY)
  const profile = fromHash.profile ?? stored ?? defaultProfile()
  const replaced =
    fromHash.profile && stored && JSON.stringify(stored) !== JSON.stringify(fromHash.profile) ? stored : null
  return {
    profile,
    places: (fromHash.places ?? (Array.isArray(storedPlaces) ? storedPlaces : [])).slice(0, MAX_PLACES),
    mode: modeFromPath(window.location.pathname),
    nearbyOf: null,
    focus: null,
    shareRents: false,
    badLink: fromHash.bad,
    replacedProfile: replaced,
  }
}

function relabel(places: Place[]): Place[] {
  return places.map((p, i) => ({ ...p, id: PLACE_IDS[i] }))
}

function reducer(s: AppState, a: Action): AppState {
  switch (a.type) {
    case 'profile':
      return { ...s, profile: a.profile }
    case 'mode':
      return { ...s, mode: a.mode, nearbyOf: a.mode === 'check' ? null : s.nearbyOf }
    case 'addPlace': {
      if (a.replace) {
        return {
          ...s,
          places: s.places.map((p) => (p.id === a.replace ? { ...p, ...a.place } : p)),
          mode: 'check',
          focus: a.place.point,
        }
      }
      if (s.places.length >= MAX_PLACES) return s
      const place: Place = { ...a.place, id: PLACE_IDS[s.places.length], rentEur: null }
      return { ...s, places: [...s.places, place], mode: 'check', focus: a.place.point }
    }
    case 'updatePlace':
      return { ...s, places: s.places.map((p) => (p.id === a.id ? { ...p, ...a.patch } : p)) }
    case 'removePlace':
      return { ...s, places: relabel(s.places.filter((p) => p.id !== a.id)), nearbyOf: null }
    case 'nearby':
      return { ...s, nearbyOf: a.id, mode: a.id ? 'find' : s.mode }
    case 'focus':
      return { ...s, focus: a.point }
    case 'shareRents':
      return { ...s, shareRents: a.on }
    case 'ackLoad':
      return { ...s, badLink: false, replacedProfile: null }
  }
}

const Ctx = createContext<{ state: AppState; dispatch: Dispatch<Action> } | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState)

  // Profile and places → localStorage and the URL hash (replaceState: no history entry per change).
  useEffect(() => {
    storage.set(PROFILE_KEY, JSON.stringify(state.profile))
    storage.set(PLACES_KEY, JSON.stringify(state.places))
    const hash = encodeHash(state.profile, state.places, state.shareRents)
    if (hash !== window.location.hash) {
      window.history.replaceState(null, '', `${window.location.pathname}${hash}`)
    }
  }, [state.profile, state.places, state.shareRents])

  // Mode → path (pushState, so Back returns to the other mode).
  useEffect(() => {
    const path = pathOf(state.mode)
    if (window.location.pathname !== path) {
      window.history.pushState(null, '', `${path}${window.location.hash}`)
    }
  }, [state.mode])

  useEffect(() => {
    const onPop = () => dispatch({ type: 'mode', mode: modeFromPath(window.location.pathname) })
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const value = useMemo(() => ({ state, dispatch }), [state])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useStore() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useStore outside StoreProvider')
  return v
}
