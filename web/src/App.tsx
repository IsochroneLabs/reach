import { useEffect, useState } from 'react'

import { API_BASE, BUILD_SHA } from './config'
import { type ApiState, fetchHealth } from './health'

function apiText(state: ApiState): string {
  switch (state.kind) {
    case 'none':
      return 'not deployed yet'
    case 'loading':
      return 'checking…'
    case 'ok':
      return `${state.health.status} (build ${state.health.build_sha})`
    case 'error':
      return `unreachable (${state.message})`
  }
}

export default function App() {
  const [api, setApi] = useState<ApiState>(API_BASE ? { kind: 'loading' } : { kind: 'none' })

  useEffect(() => {
    if (!API_BASE) return
    const ctrl = new AbortController()
    fetchHealth(API_BASE, ctrl.signal).then(setApi)
    return () => ctrl.abort()
  }, [])

  return (
    <main>
      <h1>reach</h1>
      <p lang="en">
        Where to live in Tübingen as a student: how long your everyday trips take from each part of
        the city on foot, by bike and by bus.
      </p>
      <p lang="de">
        Wo wohnen in Tübingen? Wie lange deine Alltagswege von jedem Teil der Stadt aus dauern – zu
        Fuß, mit dem Rad und mit dem Bus.
      </p>
      <p className="soon">Coming soon · Demnächst</p>
      <dl>
        <dt>Build</dt>
        <dd data-testid="build-sha">{BUILD_SHA}</dd>
        <dt>API</dt>
        <dd data-testid="api-status" data-state={api.kind}>
          {apiText(api)}
        </dd>
      </dl>
      <footer>
        DS500 course project, University of Tübingen ·{' '}
        <a href="https://github.com/IsochroneLabs/reach">Source on GitHub</a>
      </footer>
    </main>
  )
}
