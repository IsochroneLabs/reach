// MapLibre map: basemap, class map of cells, districts, inspector overlays (isochrone and route,
// display only), the recommendations layer (ranked zones; hidden while the run has none) and the
// catchment of a selected zone (the cells that reach it, plus its reverse isochrone). The map
// settings (settings.ts) switch layers, opacity, rings and the pin mode without reloading data.
import {
  AttributionControl,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  type ExpressionSpecification,
  type GeoJSONSource,
  type LngLatBoundsLike,
  type StyleSpecification,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// maplibre-gl 6 resolves its worker next to its own module, which the bundle does not keep:
// let Vite emit the worker as an asset and point MapLibre at it.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { FeatureCollection } from 'geojson'
import { BASEMAP_ATTRIBUTION, DATA_ATTRIBUTION } from '../attribution'
import { fillColourExpression, MAP_COLOURS, RECOMMENDATION_COLOURS as REC } from '../palette'
import type { MapSettings } from '../settings'
import type { CandidateCatchment, Cells, Districts, Inspect, Recommendations } from '../types'

setWorkerUrl(workerUrl)

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

// the grey dot where the user clicked stays this long; the pin moves to the cell centre
const CLICK_DOT_MS = 1500
// layers a click selects (instead of dropping a pin); they get the pointer cursor
const CLICKABLE_LAYERS = ['recommendations']

// Shown when the basemap style cannot be loaded (offline demo): the data layers still work.
const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#f2f1ed' } }],
}

async function loadBasemap(): Promise<{ style: StyleSpecification; ok: boolean }> {
  try {
    const res = await fetch(import.meta.env.VITE_BASEMAP_STYLE, { signal: AbortSignal.timeout(8000) })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return { style: (await res.json()) as StyleSpecification, ok: true }
  } catch (err) {
    console.warn('Basemap style not available, showing data layers only:', err)
    return { style: FALLBACK_STYLE, ok: false }
  }
}

function bboxOf(fc: FeatureCollection): LngLatBoundsLike {
  let [minX, minY, maxX, maxY] = [180, 90, -180, -90]
  const visit = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === 'number') {
      const [x, y] = c as number[]
      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x)
      maxY = Math.max(maxY, y)
    } else if (Array.isArray(c)) c.forEach(visit)
  }
  for (const f of fc.features) if (f.geometry && 'coordinates' in f.geometry) visit(f.geometry.coordinates)
  return [minX, minY, maxX, maxY]
}

interface Props {
  cells: Cells | null
  classes: string[]
  transit: boolean
  districts: Districts
  selectedDistrict: string | null
  inspect: Inspect | null
  /** Pin position: the routing origin of the inspected cell (`cell.origin`). */
  marker: [number, number] | null
  /** A pin is set (pin mode: isochrone and route, cell colours only if the settings say so). */
  pinMode: boolean
  settings: MapSettings
  routeCategory: string
  recommendations: Recommendations | null
  selectedCandidate: string | null
  catchment: CandidateCatchment | null
  onPick: (lon: number, lat: number) => void
  onRecommendation: (candidateId: string) => void
  /** Overlays on the map (settings button). */
  children?: ReactNode
}

/** True for the recommendation with this candidate id (selected marker). */
const isCandidate = (id: string): ExpressionSpecification => ['==', ['get', 'candidate_id'], id]
const pick = (id: string, yes: string, no: string): ExpressionSpecification => [
  'case',
  isCandidate(id),
  yes,
  no,
]

/** Zone centres as points (rank markers) from the zone polygons' `point` property. */
function recommendationPoints(recs: Recommendations): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: recs.features.map((f) => ({
      type: 'Feature',
      properties: { candidate_id: f.properties.candidate_id, rank: f.properties.rank },
      geometry: { type: 'Point', coordinates: f.properties.point },
    })),
  }
}

export default function MapView(props: Props) {
  const { cells, classes, transit, districts, selectedDistrict, inspect, marker, routeCategory, recommendations } = props
  const { selectedCandidate, catchment, pinMode, settings } = props
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const markerRef = useRef<Marker | null>(null)
  const [ready, setReady] = useState(false)
  const clickTimer = useRef<number | undefined>(undefined)
  const [basemapOk, setBasemapOk] = useState(true)
  const onPick = useRef(props.onPick)
  const onRecommendation = useRef(props.onRecommendation)
  useEffect(() => {
    onPick.current = props.onPick
    onRecommendation.current = props.onRecommendation
  })

  // Create the map once; districts are loaded before the map is mounted (initial bounds).
  useEffect(() => {
    let cancelled = false
    let map: MapLibreMap | undefined
    void loadBasemap().then(({ style, ok }) => {
      if (cancelled || !container.current) return
      setBasemapOk(ok)
      map = new MapLibreMap({
        container: container.current,
        style,
        bounds: bboxOf(districts),
        fitBoundsOptions: { padding: 20 },
        attributionControl: false,
        maxZoom: 18,
      })
      mapRef.current = map
      // dev server only (screenshots, debugging); removed from the production bundle
      if (import.meta.env.DEV) (window as unknown as { __reachMap: MapLibreMap }).__reachMap = map
      map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
      map.addControl(new ScaleControl({ unit: 'metric' }), 'top-left')
      map.addControl(
        new AttributionControl({
          compact: false,
          customAttribution: [BASEMAP_ATTRIBUTION, ...DATA_ATTRIBUTION],
        }),
        'bottom-right',
      )
      // Tile hiccups of the basemap must not end up as console errors or break the app.
      map.on('error', (e) => console.warn('map:', e.error?.message ?? e))
      // a click on a recommendation marker selects it; anywhere else drops the inspector pin
      map.on('click', (e) => {
        const hit = map?.getLayer('recommendations')
          ? map.queryRenderedFeatures(e.point, { layers: ['recommendations'] })[0]
          : undefined
        if (hit) {
          onRecommendation.current(String(hit.properties.candidate_id))
          return
        }
        onPick.current(e.lngLat.lng, e.lngLat.lat)
        const dot = map?.getSource('click-point') as GeoJSONSource | undefined
        dot?.setData({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [e.lngLat.lng, e.lngLat.lat] } })
        window.clearTimeout(clickTimer.current)
        clickTimer.current = window.setTimeout(() => dot?.setData(EMPTY), CLICK_DOT_MS)
      })
      for (const layer of CLICKABLE_LAYERS) {
        map.on('mouseenter', layer, () => {
          if (map) map.getCanvas().style.cursor = 'pointer'
        })
        // back to the crosshair of styles.css
        map.on('mouseleave', layer, () => {
          if (map) map.getCanvas().style.cursor = ''
        })
      }
      map.on('load', () => {
        if (!map) return
        // data below the basemap labels, so street and place names stay readable
        const labels = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
        const sources = ['cells', 'districts', 'isochrone', 'route', 'recommendations', 'recommendation-zones']
        sources.push('cell-selected', 'click-point')
        for (const id of [...sources, 'catchment', 'catchment-isochrone'])
          map.addSource(id, { type: 'geojson', data: EMPTY })
        map.addLayer(
          {
            id: 'cells-fill',
            type: 'fill',
            source: 'cells',
            // the faint outline keeps the lightest classes apart from the light basemap
            paint: { 'fill-opacity': 0.8, 'fill-outline-color': MAP_COLOURS.cellOutline },
          },
          labels,
        )
        // pin mode without colours: the fill is transparent, a thin grid stays
        map.addLayer(
          {
            id: 'cells-outline',
            type: 'line',
            source: 'cells',
            layout: { visibility: 'none' },
            paint: { 'line-color': MAP_COLOURS.cellOutline, 'line-width': 0.6 },
          },
          labels,
        )
        map.addLayer(
          {
            id: 'districts-line',
            type: 'line',
            source: 'districts',
            paint: { 'line-color': '#3d3d3d', 'line-width': 0.8, 'line-opacity': 0.55 },
          },
          labels,
        )
        map.addLayer(
          {
            id: 'districts-selected',
            type: 'line',
            source: 'districts',
            filter: ['==', ['get', 'district_id'], ''],
            paint: { 'line-color': '#111', 'line-width': 2.5 },
          },
          labels,
        )
        // the scored cell of the pin: routing starts at its centre
        map.addLayer({
          id: 'cell-selected',
          type: 'line',
          source: 'cell-selected',
          paint: { 'line-color': MAP_COLOURS.selectedCell, 'line-width': 2.5 },
        })
        map.addLayer({
          id: 'isochrone-fill',
          type: 'fill',
          source: 'isochrone',
          paint: { 'fill-color': '#1f3b70', 'fill-opacity': 0.07 },
        })
        map.addLayer({
          id: 'isochrone-line',
          type: 'line',
          source: 'isochrone',
          paint: {
            'line-color': '#1f3b70',
            'line-width': ['match', ['get', 'contour_min'], 5, 2.6, 10, 1.8, 1.2],
            'line-dasharray': [3, 1.5],
          },
        })
        map.addLayer({
          id: 'route-casing',
          type: 'line',
          source: 'route',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': '#ffffff', 'line-width': 6 },
        })
        map.addLayer({
          id: 'route-line',
          type: 'line',
          source: 'route',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': '#111111', 'line-width': 3 },
        })
        map.addLayer({
          id: 'catchment-line',
          type: 'line',
          source: 'catchment',
          paint: { 'line-color': REC.catchment, 'line-width': 1.6, 'line-opacity': 0.9 },
        })
        map.addLayer({
          id: 'catchment-isochrone',
          type: 'line',
          source: 'catchment-isochrone',
          paint: {
            'line-color': REC.catchment,
            'line-width': ['match', ['get', 'contour_min'], 15, 2.4, 1.2],
            'line-dasharray': [2, 1.5],
          },
        })
        // the 100 m zone itself, visible when zoomed in
        map.addLayer({
          id: 'recommendation-zones',
          type: 'line',
          source: 'recommendation-zones',
          minzoom: 13,
          paint: { 'line-color': REC.ring, 'line-width': 2 },
        })
        map.addLayer({
          id: 'recommendations',
          type: 'circle',
          source: 'recommendations',
          layout: { visibility: 'none' },
          paint: {
            'circle-radius': 10,
            'circle-color': pick('', REC.selected, REC.marker),
            'circle-stroke-color': REC.ring,
            'circle-stroke-width': 2.5,
          },
        })
        // rank numbers need the basemap's glyphs (not available in the offline fallback style)
        if (map.getStyle().glyphs)
          map.addLayer({
            id: 'recommendations-rank',
            type: 'symbol',
            source: 'recommendations',
            layout: {
              visibility: 'none',
              'text-field': ['to-string', ['get', 'rank']],
              'text-size': 12,
              'text-font': ['Noto Sans Bold'],
              'text-allow-overlap': true,
              'text-ignore-placement': true,
            },
            paint: { 'text-color': pick('', REC.selectedText, REC.ring) },
          })
        map.addLayer({
          id: 'click-point',
          type: 'circle',
          source: 'click-point',
          paint: {
            'circle-radius': 4,
            'circle-color': MAP_COLOURS.clickPoint,
            'circle-stroke-color': MAP_COLOURS.clickPointStroke,
            'circle-stroke-width': 1,
          },
        })
        setReady(true)
      })
    })
    return () => {
      cancelled = true
      map?.remove()
      mapRef.current = null
    }
    // districts only seed the initial bounds; later updates go through the effects below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const source = (id: string) => mapRef.current?.getSource(id) as GeoJSONSource | undefined

  useEffect(() => {
    if (!ready) return
    source('cells')?.setData(cells ?? EMPTY)
    mapRef.current?.setPaintProperty('cells-fill', 'fill-color', fillColourExpression(classes, transit))
  }, [ready, cells, classes, transit])

  useEffect(() => {
    if (ready) source('districts')?.setData(districts)
  }, [ready, districts])

  // Display settings: visibility, opacity and filters only, the data stays loaded.
  const coloured = !pinMode || settings.coloursWithPin
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const visible = (on: boolean) => (on ? 'visible' : 'none')
    const minResidents: ExpressionSpecification = ['>=', ['get', 'population'], settings.minResidents]
    map.setLayoutProperty('cells-fill', 'visibility', visible(settings.showCells))
    map.setPaintProperty('cells-fill', 'fill-opacity', coloured ? settings.cellOpacity : 0)
    map.setFilter('cells-fill', minResidents)
    map.setLayoutProperty('cells-outline', 'visibility', visible(settings.showCells && !coloured))
    map.setFilter('cells-outline', minResidents)
    for (const id of ['districts-line', 'districts-selected'])
      map.setLayoutProperty(id, 'visibility', visible(settings.showDistricts))
    for (const id of ['route-casing', 'route-line']) map.setLayoutProperty(id, 'visibility', visible(settings.showPois))
    const hidden = Object.entries(settings.isochroneRings)
      .filter(([, shown]) => !shown)
      .map(([m]) => Number(m))
    const rings: ExpressionSpecification = ['!', ['in', ['get', 'contour_min'], ['literal', hidden]]]
    for (const id of ['isochrone-fill', 'isochrone-line']) map.setFilter(id, rings)
  }, [ready, settings, coloured])

  useEffect(() => {
    if (ready)
      mapRef.current?.setFilter('districts-selected', ['==', ['get', 'district_id'], selectedDistrict ?? ''])
  }, [ready, selectedDistrict])

  // Zoom to a new inspect answer once (not again when only the category changes).
  const fitted = useRef<Inspect | null>(null)
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !inspect || fitted.current === inspect) return
    fitted.current = inspect
    if (inspect.isochrone.features.length)
      map.fitBounds(bboxOf(inspect.isochrone), { padding: 40, maxZoom: 15, duration: 600 })
  }, [ready, inspect])

  useEffect(() => {
    if (!ready) return
    source('isochrone')?.setData(inspect?.isochrone ?? EMPTY)
    const route = inspect?.categories.find((c) => c.category === routeCategory)?.nearest_route
    source('route')?.setData(route ? { type: 'FeatureCollection', features: [route] } : EMPTY)
  }, [ready, inspect, routeCategory])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const show = Boolean(settings.showRecommendations && recommendations?.available && recommendations.features.length)
    source('recommendations')?.setData(show && recommendations ? recommendationPoints(recommendations) : EMPTY)
    source('recommendation-zones')?.setData(show && recommendations ? recommendations : EMPTY)
    // the catchment of a selected zone belongs to the recommendations: hidden with them
    for (const id of ['recommendations', 'recommendations-rank', 'catchment-line', 'catchment-isochrone'])
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', show ? 'visible' : 'none')
    // a hidden layer fires no mouseleave: drop the pointer cursor it may have set
    if (!show) map.getCanvas().style.cursor = ''
  }, [ready, recommendations, settings.showRecommendations])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const id = selectedCandidate ?? ''
    map.setPaintProperty('recommendations', 'circle-color', pick(id, REC.selected, REC.marker))
    if (map.getLayer('recommendations-rank'))
      map.setPaintProperty('recommendations-rank', 'text-color', pick(id, REC.selectedText, REC.ring))
  }, [ready, selectedCandidate])

  // Catchment of the selected zone: its cells (from the map's cells) and the reverse isochrone.
  useEffect(() => {
    if (!ready) return
    const ids = new Set(catchment?.cell_ids ?? [])
    const features = cells && ids.size ? cells.features.filter((f) => ids.has(f.properties.cell_id)) : []
    source('catchment')?.setData({ type: 'FeatureCollection', features })
    source('catchment-isochrone')?.setData(catchment?.isochrone ?? EMPTY)
  }, [ready, catchment, cells])

  const fittedCatchment = useRef<CandidateCatchment | null>(null)
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !catchment || fittedCatchment.current === catchment) return
    fittedCatchment.current = catchment
    if (catchment.isochrone.features.length)
      map.fitBounds(bboxOf(catchment.isochrone), { padding: 40, maxZoom: 15, duration: 600 })
  }, [ready, catchment])

  // Outline of the inspected cell (scored cells only: the map has no polygons of the others).
  const cellId = inspect?.cell.cell_id ?? null
  useEffect(() => {
    if (!ready) return
    const feature = pinMode && cellId ? cells?.features.find((f) => f.properties.cell_id === cellId) : undefined
    source('cell-selected')?.setData(feature ? { type: 'FeatureCollection', features: [feature] } : EMPTY)
  }, [ready, cells, cellId, pinMode])

  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    if (!marker) {
      markerRef.current?.remove()
      markerRef.current = null
      return
    }
    if (!markerRef.current) markerRef.current = new Marker({ color: MAP_COLOURS.pin })
    markerRef.current.setLngLat(marker).addTo(map)
  }, [ready, marker])

  useEffect(() => () => window.clearTimeout(clickTimer.current), [])

  return (
    <div className="map-wrap">
      <div
        ref={container}
        className="map"
        data-testid="map"
        data-ready={ready && cells ? 'true' : 'false'}
        // effective cell fill (0 = no colours), read by the smoke test
        data-cell-fill={settings.showCells && coloured ? settings.cellOpacity : 0}
        role="region"
        aria-label="Map: click to inspect a location"
      />
      {!basemapOk && <div className="map-notice">Basemap unavailable — data layers only.</div>}
      {props.children}
    </div>
  )
}
