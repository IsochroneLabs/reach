import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import {
  errorMessage,
  getCells,
  getDistricts,
  getFacilities,
  getMeta,
  getRecommendations,
  postCandidateCatchment,
  postInspect,
  postIsochrone,
  postRoute,
} from './api'
import Controls from './components/Controls'
import DataPage from './components/DataPage'
import DistrictPanel from './components/DistrictPanel'
import Inspector, { type FacilityRouteState, type InspectState } from './components/Inspector'
import MapView from './components/MapView'
import RecommendationsPanel, { type CatchmentState } from './components/RecommendationsPanel'
import SettingsPanel from './components/SettingsPanel'
import { FACILITY_CLASSES, TRANSIT } from './palette'
import { routeHash, useRoute } from './route'
import { cardOpen, useSettings } from './settings'
import type { Cells, Districts, Facilities, IsochroneAnswer, Meta, RecommendationProps, Recommendations } from './types'

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
  const { settings, update: updateSettings, setCard, reset: resetSettings } = useSettings()
  const profile = meta.profiles.find((p) => p.profile_id === route.profile) ?? meta.profiles[0]
  const validCategory = (id: string | null) =>
    id !== null && (meta.categories.some((c) => c.id === id) || (id === TRANSIT && profile.transit))
  const category = validCategory(route.category) ? route.category! : meta.categories[0].id

  const viewKey = `${category}|${profile.profile_id}`
  // Results carry the selection they belong to; the previous cells stay visible while loading.
  const [cellsResult, setCellsResult] = useState<{ key: string; cells: Cells | null }>({ key: '', cells: null })
  const [cellsError, setCellsError] = useState<{ key: string; message: string } | null>(null)
  const [recommendations, setRecommendations] = useState<{ key: string; data: Recommendations } | null>(null)
  const [facilityLayer, setFacilityLayer] = useState<{ category: string; data: Facilities } | null>(null)
  const [pin, setPin] = useState<[number, number] | null>(null)
  const [inspect, setInspect] = useState<InspectState>({ status: 'idle' })
  const [district, setDistrict] = useState<string | null>(null)
  // facility picked in the list or on the map (route to exactly this one) and the hovered one
  const [selectedFacility, setSelectedFacility] = useState<string | null>(null)
  const [hoveredFacility, setHoveredFacility] = useState<string | null>(null)
  const inspectAbort = useRef<AbortController | null>(null)
  // catchment of a recommended zone; it belongs to the selection it was loaded for
  const [catchment, setCatchment] = useState<{ key: string; state: CatchmentState }>({
    key: '',
    state: { status: 'idle' },
  })
  const catchmentAbort = useRef<AbortController | null>(null)

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

  // Recommendations: layer and panel stay hidden while the run has none for the selection.
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

  // Facilities of the category (points, park outlines, access points): only once they are drawn,
  // i.e. with a pin or with the "all facilities" layer on.
  const wantFacilities = category !== TRANSIT && (pin !== null || settings.showAllFacilities)
  useEffect(() => {
    if (!wantFacilities) return
    let cancelled = false
    getFacilities(category).then(
      (data) => !cancelled && setFacilityLayer({ category, data }),
      (err: unknown) => console.warn('facilities:', errorMessage(err)),
    )
    return () => {
      cancelled = true
    }
  }, [wantFacilities, category])
  const facilities = wantFacilities && facilityLayer?.category === category ? facilityLayer.data : null
  const areaIds = useMemo(
    () => new Set(facilities?.features.filter((f) => f.properties.kind === 'area').map((f) => f.properties.facility_id)),
    [facilities],
  )

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
    // the pins and routes belong to the category and profile they were picked in
    setSelectedFacility(null)
    setHoveredFacility(null)
    const profileId = next.profile ?? profile.profile_id
    navigate({ view: 'map', profile: profileId, category: next.category ?? category })
    // the inspect answer covers all categories; only a new profile needs a new one
    if (pin && profileId !== profile.profile_id) runInspect(pin[0], pin[1], profileId)
  }

  const pick = (lon: number, lat: number) => {
    setSelectedFacility(null)
    setHoveredFacility(null)
    setPin([lon, lat])
    // a new pin always shows its answer, even if the card was collapsed before
    setCard('inspector', true)
    runInspect(lon, lat, profile.profile_id)
  }

  const selectRecommendation = (rec: RecommendationProps | null) => {
    catchmentAbort.current?.abort()
    if (!rec) {
      setCatchment({ key: viewKey, state: { status: 'idle' } })
      return
    }
    const controller = new AbortController()
    catchmentAbort.current = controller
    const candidateId = rec.candidate_id
    setCatchment({ key: viewKey, state: { status: 'loading', candidateId } })
    postCandidateCatchment(candidateId, rec.category, rec.profile_id, controller.signal).then(
      (data) => !controller.signal.aborted && setCatchment({ key: viewKey, state: { status: 'done', candidateId, data } }),
      (err: unknown) =>
        !controller.signal.aborted &&
        setCatchment({ key: viewKey, state: { status: 'error', candidateId, message: errorMessage(err) } }),
    )
  }
  const catchmentState: CatchmentState = catchment.key === viewKey ? catchment.state : { status: 'idle' }
  const currentRecommendations = recommendations?.key === viewKey ? recommendations.data : null

  const cells = cellsResult.cells
  // residents slider: the legend counts the cells shown on the map (the map filters itself)
  const shownCells = useMemo(
    () => (cells && settings.minResidents > 0 ? { ...cells, features: cells.features.filter((f) => f.properties.population >= settings.minResidents) } : cells),
    [cells, settings.minResidents],
  )
  const cellsCurrent = cellsResult.key === viewKey
  const cellsFailed = cellsError?.key === viewKey && !cellsCurrent
  // a facility from the list or a pin: its category becomes the selected one, so its pin is shown
  const pickFacility = (facilityId: string | null, facilityCategory: string) => {
    if (facilityCategory !== category) select({ category: facilityCategory })
    setSelectedFacility(facilityId)
  }
  const closeInspector = () => {
    setSelectedFacility(null)
    setHoveredFacility(null)
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
  // the pin sits where routing starts (cell centre); the click point shows briefly on the map
  // while a new answer loads, the pin stays at the click point
  const marker = inspect.status === 'done' ? inspect.data.cell.origin : inspect.status === 'idle' ? null : pin
  const rings = useMemo(
    () => [...new Set(shownInspect?.isochrone.features.map((f) => f.properties.contour_min) ?? [])].sort((a, b) => a - b),
    [shownInspect],
  )
  // Reverse isochrone of the inspected cell, requested only when the settings ask for it.
  const wantReverse = settings.isochroneDirection !== 'forward'
  // from the shown answer, so the reverse isochrone stays with the forward one while a new pin loads
  const inspectedOrigin = shownInspect?.cell.origin ?? null
  const reverseKey = inspectedOrigin && wantReverse ? `${inspectedOrigin.join(',')}|${profile.profile_id}` : null
  const [reverse, setReverse] = useState<{ key: string; data: IsochroneAnswer | null; error?: string } | null>(null)
  useEffect(() => {
    if (!reverseKey || !inspectedOrigin) return
    const controller = new AbortController()
    postIsochrone(inspectedOrigin[0], inspectedOrigin[1], profile.profile_id, 'reverse', controller.signal).then(
      (data) => setReverse({ key: reverseKey, data }),
      (err: unknown) => !controller.signal.aborted && setReverse({ key: reverseKey, data: null, error: errorMessage(err) }),
    )
    return () => controller.abort()
    // the key covers origin and profile
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reverseKey])
  const reverseOfPin = pin && reverse && reverse.key === reverseKey ? reverse : null
  const reverseIsochrone = reverseOfPin?.data?.isochrone ?? null

  // Route to the picked facility, from the origin of the shown answer; one request per pick
  // (cached by the API), aborted when the pick changes.
  const facilityKey = inspectedOrigin && selectedFacility ? `${inspectedOrigin.join(',')}|${profile.profile_id}|${selectedFacility}` : null
  const [picked, setPicked] = useState<{ key: string; state: FacilityRouteState } | null>(null)
  useEffect(() => {
    if (!facilityKey || !inspectedOrigin || !selectedFacility) return
    const controller = new AbortController()
    postRoute(inspectedOrigin[0], inspectedOrigin[1], profile.profile_id, selectedFacility, controller.signal).then(
      (data) => !controller.signal.aborted && setPicked({ key: facilityKey, state: { status: 'done', data } }),
      (err: unknown) =>
        !controller.signal.aborted && setPicked({ key: facilityKey, state: { status: 'error', message: errorMessage(err) } }),
    )
    return () => controller.abort()
    // the key covers origin, profile and facility
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facilityKey])
  const facilityRoute: FacilityRouteState = !facilityKey ? { status: 'idle' } : picked?.key === facilityKey ? picked.state : { status: 'loading' }
  const budgetMin = meta.profiles.find((p) => p.profile_id === shownInspect?.profile_id)?.time_budget_min ?? null

  const card = (id: string) => ({
    open: cardOpen(settings, id),
    onToggle: (open: boolean) => setCard(id, open),
  })

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
              cells={cellsCurrent ? shownCells : null}
              allCells={cellsCurrent ? (cells?.features.length ?? 0) : 0}
              minResidents={settings.minResidents}
              coloursHidden={pin !== null && !settings.coloursWithPin}
              card={card('map')}
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
              card={card('inspector')}
              coloursWithPin={settings.coloursWithPin}
              direction={settings.isochroneDirection}
              reverseError={reverseOfPin?.error ?? null}
              facility={{ selected: selectedFacility, route: facilityRoute, onSelect: pickFacility, onHover: setHoveredFacility, areaIds }}
              onColoursWithPin={(on) => updateSettings({ coloursWithPin: on })}
            />
            <RecommendationsPanel
              meta={meta}
              category={category}
              recommendations={currentRecommendations}
              catchment={catchmentState}
              onSelect={selectRecommendation}
              card={card('recommendations')}
            />
            <DistrictPanel
              meta={meta}
              districts={districts}
              selected={district}
              profile={profile.profile_id}
              category={category}
              onSelect={setDistrict}
              onCategory={(id) => select({ category: id })}
              card={card('district')}
            />
          </aside>
          <MapView
            cells={cells}
            classes={classes}
            transit={transitCells}
            districts={districts}
            selectedDistrict={district}
            inspect={shownInspect}
            reverseIsochrone={reverseIsochrone}
            marker={marker}
            pinMode={pin !== null}
            settings={settings}
            routeCategory={category}
            budgetMin={budgetMin}
            facilities={facilities}
            selectedFacility={selectedFacility}
            hoveredFacility={hoveredFacility}
            facilityRoute={facilityRoute.status === 'done' ? facilityRoute.data : null}
            onFacility={(id) => pickFacility(id === selectedFacility ? null : id, category)}
            onFacilityHover={setHoveredFacility}
            recommendations={currentRecommendations}
            selectedCandidate={catchmentState.status === 'idle' ? null : catchmentState.candidateId}
            catchment={catchmentState.status === 'done' ? catchmentState.data : null}
            onPick={pick}
            onRecommendation={(id) => {
              const rec = currentRecommendations?.features.find((f) => f.properties.candidate_id === id)
              const selected = catchmentState.status === 'idle' ? null : catchmentState.candidateId
              // a second click on the selected marker clears it, as in the list
              if (rec) selectRecommendation(id === selected ? null : rec.properties)
            }}
          >
            <SettingsPanel
              settings={settings}
              onChange={updateSettings}
              onReset={resetSettings}
              rings={rings}
              directionAvailable
            />
          </MapView>
          {pin && (
            <a className="details-hint" href="#inspector" onClick={scrollToInspector}>
              Details below ↓
            </a>
          )}
        </main>
    </div>
  )
}
