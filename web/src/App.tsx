import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { errorMessage, getCells, getDistricts, getMeta, getRecommendations, postInspect } from './api'
import Controls from './components/Controls'
import DataPage from './components/DataPage'
import DistrictPanel from './components/DistrictPanel'
import Inspector, { type InspectState } from './components/Inspector'
import MapView from './components/MapView'
import { FACILITY_CLASSES, TRANSIT } from './palette'
import { routeHash, useRoute } from './route'
import type { Cells, Districts, Meta, Recommendations } from './types'

// Scored cells answer in < 100 ms: show the spinner only for slower (live) answers.
const SPINNER_DELAY_MS = 300

type Boot = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; meta: Meta; districts: Districts }

export default function App() {
  const [boot, setBoot] = useState<Boot>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([getMeta(), getDistricts()]).then(
      ([meta, districts]) => !cancelled && setBoot({ status: 'ready', meta, districts }),
      (err: unknown) => !cancelled && setBoot({ status: 'error', message: errorMessage(err) }),
    )
    return () => {
      cancelled = true
    }
  }, [attempt])

  if (boot.status === 'loading') return <div className="splash">Loading reach…</div>
  if (boot.status === 'error')
    return (
      <div className="splash">
        <p className="error">{boot.message}</p>
        <button
          type="button"
          onClick={() => {
            setBoot({ status: 'loading' })
            setAttempt((a) => a + 1)
          }}
        >
          Retry
        </button>
      </div>
    )
  return <Main meta={boot.meta} districts={boot.districts} />
}

function Main({ meta, districts }: { meta: Meta; districts: Districts }) {
  const [route, navigate] = useRoute()
  const profile = meta.profiles.find((p) => p.profile_id === route.profile) ?? meta.profiles[0]
  const validCategory = (id: string | null) =>
    id !== null && (meta.categories.some((c) => c.id === id) || (id === TRANSIT && profile.transit))
  const category = validCategory(route.category) ? route.category! : meta.categories[0].id

  const viewKey = `${category}|${profile.profile_id}`
  // Results carry the selection they belong to; the previous cells stay visible while loading.
  const [cellsResult, setCellsResult] = useState<{ key: string; cells: Cells | null }>({ key: '', cells: null })
  const [cellsError, setCellsError] = useState<{ key: string; message: string } | null>(null)
  const [recommendations, setRecommendations] = useState<{ key: string; data: Recommendations } | null>(null)
  const [pin, setPin] = useState<[number, number] | null>(null)
  const [inspect, setInspect] = useState<InspectState>({ status: 'idle' })
  const [district, setDistrict] = useState<string | null>(null)
  const inspectAbort = useRef<AbortController | null>(null)

  // Normalise the hash once (defaults or an unknown profile/category in a shared link).
  useEffect(() => {
    if (route.view === 'map' && (route.profile !== profile.profile_id || route.category !== category))
      navigate({ view: 'map', profile: profile.profile_id, category })
  }, [route, profile.profile_id, category, navigate])

  useEffect(() => {
    let cancelled = false
    getCells(category, profile.profile_id).then(
      (data) => !cancelled && setCellsResult({ key: viewKey, cells: data }),
      (err: unknown) => !cancelled && setCellsError({ key: viewKey, message: errorMessage(err) }),
    )
    return () => {
      cancelled = true
    }
  }, [category, profile.profile_id, viewKey])

  // Recommendations (P7): the layer stays hidden while the endpoint reports `available: false`.
  useEffect(() => {
    if (category === TRANSIT) return
    let cancelled = false
    getRecommendations(category, profile.profile_id).then(
      (data) => !cancelled && setRecommendations({ key: viewKey, data }),
      (err: unknown) => console.warn('recommendations:', errorMessage(err)),
    )
    return () => {
      cancelled = true
    }
  }, [category, profile.profile_id, viewKey])

  const runInspect = useCallback((lon: number, lat: number, profileId: string) => {
    inspectAbort.current?.abort()
    const controller = new AbortController()
    inspectAbort.current = controller
    // keep the previous answer (dimmed) until the new one arrives: no flicker for fast answers
    setInspect((prev) => ({
      status: 'loading',
      showSpinner: false,
      previous: prev.status === 'done' ? prev.data : prev.status === 'loading' ? prev.previous : null,
    }))
    const timer = window.setTimeout(() => {
      if (!controller.signal.aborted)
        setInspect((prev) => (prev.status === 'loading' ? { ...prev, showSpinner: true } : prev))
    }, SPINNER_DELAY_MS)
    postInspect(lon, lat, profileId, controller.signal)
      .then(
        (data) => {
          if (controller.signal.aborted) return
          setInspect({ status: 'done', data })
          if (data.cell.district_id) setDistrict(data.cell.district_id)
        },
        (err: unknown) => {
          if (controller.signal.aborted) return
          setInspect({ status: 'error', message: errorMessage(err) })
        },
      )
      .finally(() => window.clearTimeout(timer))
  }, [])

  const select = (next: { profile?: string; category?: string }) => {
    const profileId = next.profile ?? profile.profile_id
    navigate({ view: 'map', profile: profileId, category: next.category ?? category })
    // the inspect answer covers all categories; only a new profile needs a new one
    if (pin && profileId !== profile.profile_id) runInspect(pin[0], pin[1], profileId)
  }

  const pick = (lon: number, lat: number) => {
    setPin([lon, lat])
    runInspect(lon, lat, profile.profile_id)
  }

  const cells = cellsResult.cells
  const cellsCurrent = cellsResult.key === viewKey
  const cellsFailed = cellsError?.key === viewKey && !cellsCurrent
  const closeInspector = () => {
    inspectAbort.current?.abort()
    setPin(null)
    setInspect({ status: 'idle' })
  }

  // phones: the inspector sits below the map
  const scrollToInspector = (e: MouseEvent) => {
    e.preventDefault()
    document.getElementById('inspector')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const districtName = (id: string | null) =>
    id ? (districts.features.find((f) => f.properties.district_id === id)?.properties.name ?? null) : null
  // colours follow the cells on the map (the previous selection stays visible while loading)
  const transitCells = cells?.category === TRANSIT
  const classes = useMemo(
    () => (transitCells ? meta.transit_classes.map((t) => t.class) : [...FACILITY_CLASSES]),
    [transitCells, meta.transit_classes],
  )
  const shownInspect =
    inspect.status === 'done' ? inspect.data : inspect.status === 'loading' ? inspect.previous : null

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>reach</strong>
          <span className="muted">15-minute Tübingen</span>
        </div>
        <nav aria-label="Views">
          <a href={routeHash({ view: 'map', profile: profile.profile_id, category })} aria-current={route.view === 'map' ? 'page' : undefined}>
            Map
          </a>
          <a href={routeHash({ view: 'data', profile: profile.profile_id, category })} aria-current={route.view === 'data' ? 'page' : undefined}>
            Data &amp; validation
          </a>
        </nav>
        <span className="run muted small" title={`Run ${meta.run.run_id}`}>
          Data {meta.run.osm_snapshot?.slice(0, 10) ?? meta.run.run_id} · {meta.run.status}
        </span>
      </header>

      {route.view === 'data' && <DataPage meta={meta} />}
      {/* the map stays mounted on the data page, so its position survives a view switch */}
      <main className="layout" hidden={route.view === 'data'}>
          <aside className="sidebar">
            <Controls
              meta={meta}
              profile={profile}
              category={category}
              cells={cellsCurrent ? cells : null}
              loading={!cellsCurrent && !cellsFailed}
              error={cellsFailed ? cellsError.message : null}
              onProfile={(id) => select({ profile: id })}
              onCategory={(id) => select({ category: id })}
            />
            <Inspector
              meta={meta}
              state={inspect}
              districtName={districtName}
              category={category}
              onCategory={(id) => select({ category: id })}
              onClose={closeInspector}
            />
            <DistrictPanel
              meta={meta}
              districts={districts}
              selected={district}
              profile={profile.profile_id}
              category={category}
              onSelect={setDistrict}
              onCategory={(id) => select({ category: id })}
            />
          </aside>
          <MapView
            cells={cells}
            classes={classes}
            transit={transitCells}
            districts={districts}
            selectedDistrict={district}
            inspect={shownInspect}
            pin={pin}
            routeCategory={category}
            recommendations={recommendations?.key === viewKey ? recommendations.data : null}
            onPick={pick}
          />
          {pin && (
            <a className="details-hint" href="#inspector" onClick={scrollToInspector}>
              Details below ↓
            </a>
          )}
        </main>
    </div>
  )
}
