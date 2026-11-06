// View and selection live in the URL hash (`#/map?profile=…&category=…`, `#/data`), so a demo
// link opens a given view; no router dependency.
import { useCallback, useEffect, useState } from 'react'

export interface Route {
  view: 'map' | 'data'
  profile: string | null
  category: string | null
}

function parse(hash: string): Route {
  const [path, search = ''] = hash.replace(/^#\/?/, '').split('?')
  const params = new URLSearchParams(search)
  return {
    view: path === 'data' ? 'data' : 'map',
    profile: params.get('profile'),
    category: params.get('category'),
  }
}

export function routeHash(route: Route): string {
  if (route.view === 'data') return '#/data'
  const params = new URLSearchParams()
  if (route.profile) params.set('profile', route.profile)
  if (route.category) params.set('category', route.category)
  const search = params.toString()
  return `#/map${search ? `?${search}` : ''}`
}

export function useRoute(): [Route, (next: Route) => void] {
  const [route, setRoute] = useState(() => parse(window.location.hash))
  useEffect(() => {
    const onHash = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const navigate = useCallback((next: Route) => {
    const hash = routeHash(next)
    // replaceState: selector changes should not fill the back button history
    if (hash !== window.location.hash) window.history.replaceState(null, '', hash)
    setRoute(next)
  }, [])
  return [route, navigate]
}
