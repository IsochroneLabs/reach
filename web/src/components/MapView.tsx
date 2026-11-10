// MapLibre map: basemap, class map of cells, districts, inspector overlays (isochrone and route,
// display only), facility pins and the route to the next missing facility (or to a facility picked
// in the list), the recommendations layer (ranked zones; hidden while the run has none) and the
// catchment of a selected zone (the cells that reach it, plus its reverse isochrone). The map
// settings (settings.ts) switch layers, opacity, rings and the pin mode without reloading data.
import {
  AttributionControl,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
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
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { FeatureCollection } from 'geojson'
import { BASEMAP_ATTRIBUTION, DATA_ATTRIBUTION } from '../attribution'
import { infoLines, PARK_NOTE } from '../facilityInfo'
import { timeLabel } from '../labels'
import {
  fillColourExpression,
  SCORE_CLASSES,
  SCORE_FULL_OUTLINE,
  ISOCHRONE_COLOURS as ISO,
  FACILITY_LAYER_COLOURS as FAC,
  MAP_COLOURS,
  POI_COLOURS as POI,
  RECOMMENDATION_COLOURS as REC,
} from '../palette'
import type { MapSettings } from '../settings'
import type {
  CandidateCatchment,
  Cells,
  Districts,
  Facilities,
  FacilityTags,
  Housing,
  Inspect,
  Recommendations,
  RouteAnswer,
} from '../types'

setWorkerUrl(workerUrl)

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

// the grey dot where the user clicked stays this long; the pin moves to the cell centre
const CLICK_DOT_MS = 1500
// layers a click selects (instead of dropping a pin); they get the pointer cursor
const CLICKABLE_LAYERS = ['recommendations', 'poi-pins', 'facility-all']
// facility pins show their time label from this zoom on
const POI_LABEL_MINZOOM = 15

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
  /** Reverse isochrone of the pin's cell (settings direction reverse or both), else null. */
  reverseIsochrone: FeatureCollection | null
  /** Pin position: the routing origin of the inspected cell (`cell.origin`). */
  marker: [number, number] | null
  /** A pin is set (pin mode: isochrone and route, cell colours only if the settings say so). */
  pinMode: boolean
  settings: MapSettings
  routeCategory: string
  /** Facility budget of the inspected profile (minutes), for "beyond 15 min" labels. */
  budgetMin: number | null
  /** All facilities of the selected category with park outlines and access points (or null). */
  facilities: Facilities | null
  /** Facilities of the category that are parks (area outline), for the park note. */
  areaIds: Set<string>
  /** Facility picked in the list or on the map, and the one under the pointer in the list. */
  selectedFacility: string | null
  hoveredFacility: string | null
  /** Route to the picked facility (replaces the route to the next missing facility). */
  facilityRoute: RouteAnswer | null
  onFacility: (facilityId: string) => void
  onFacilityHover: (facilityId: string | null) => void
  recommendations: Recommendations | null
  /** Housing potential cells scored for the selection (null = layer off). */
  housing: Housing | null
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

/** Pins of the selected category: the facilities reachable in the budget, plus the next missing
 * facility (filled pin) when the cell has fewer than needed. */
function poiPins(
  inspect: Inspect | null,
  category: string,
  budgetMin: number | null,
  areaIds: Set<string>,
): FeatureCollection {
  const c = inspect?.categories.find((x) => x.category === category)
  if (!c) return EMPTY
  const pin = (
    f: { facility_id: string; name: string | null; tags: FacilityTags; point: [number, number] },
    min: number,
    beyond: boolean,
    next: boolean,
  ) => ({
    type: 'Feature' as const,
    properties: {
      facility_id: f.facility_id,
      name: f.name,
      category: c.name,
      tags: JSON.stringify(f.tags),
      area: areaIds.has(f.facility_id),
      time_min: min,
      time_label: timeLabel(min, budgetMin, beyond),
      beyond,
      next,
    },
    geometry: { type: 'Point' as const, coordinates: f.point },
  })
  const features = c.reachable.map((f) => pin(f, f.time_min, false, false))
  const n = c.next_facility
  if (n) features.push(pin(n, n.time_min, !n.within_budget, true))
  return { type: 'FeatureCollection', features }
}

/** The route on the map: to the picked facility, else to the next missing facility (dashed and
 * labelled "beyond 15 min" when it is outside the budget). */
function routeLine(
  inspect: Inspect | null,
  category: string,
  picked: RouteAnswer | null,
  budgetMin: number | null,
): FeatureCollection {
  const next = inspect?.categories.find((x) => x.category === category)?.next_facility
  const route = picked ? picked.route : next?.route
  if (!route) return EMPTY
  const beyond = picked ? !picked.within_budget : !next!.within_budget
  const minutes = (picked ? picked.route.properties.time_s : next!.time_s) / 60
  return {
    type: 'FeatureCollection',
    features: [{ ...route, properties: { ...route.properties, beyond, label: timeLabel(minutes, budgetMin, beyond) } }],
  }
}

/** The label of the route as a point halfway along it (a label along a winding line is hidden by
 * MapLibre where the line bends too much). */
function routeLabelPoint(route: FeatureCollection): FeatureCollection {
  const f = route.features[0]
  if (!f || f.geometry.type !== 'LineString') return EMPTY
  const line = f.geometry.coordinates
  const middle = line[Math.floor(line.length / 2)]
  return {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: { label: f.properties?.label }, geometry: { type: 'Point', coordinates: middle } }],
  }
}

/** Popup content as DOM nodes (OSM names are untrusted text, never HTML). */
function popupContent(props: Record<string, unknown>): HTMLElement {
  const root = document.createElement('div')
  const name = document.createElement('strong')
  name.textContent = typeof props.name === 'string' && props.name ? props.name : 'Unnamed'
  const detail = document.createElement('div')
  detail.className = 'muted small'
  const parts = [String(props.category)]
  if (props.time_label) parts.push(String(props.time_label))
  if (props.next) parts.push('next missing')
  detail.textContent = parts.join(' · ')
  root.append(name, detail)
  // MapLibre hands nested properties over as JSON text
  let tags: FacilityTags | null
  try {
    const raw = props.tags
    tags = (typeof raw === 'string' ? JSON.parse(raw) : raw) as FacilityTags
  } catch {
    tags = {}
  }
  for (const line of infoLines(tags ?? {})) {
    const row = document.createElement('div')
    row.className = 'small'
    row.textContent = `${line.label}: ${line.value}`
    root.append(row)
  }
  if (props.area === true || props.area === 'true') {
    const note = document.createElement('div')
    note.className = 'muted small'
    note.textContent = PARK_NOTE
    root.append(note)
  }
  return root
}

export default function MapView(props: Props) {
  const { cells, classes, transit, districts, selectedDistrict, inspect, marker, routeCategory, recommendations } = props
  const { selectedCandidate, catchment, pinMode, settings, reverseIsochrone, housing } = props
  const { budgetMin, selectedFacility, hoveredFacility, facilityRoute, facilities, areaIds } = props
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const markerRef = useRef<Marker | null>(null)
  const popupRef = useRef<Popup | null>(null)
  const [ready, setReady] = useState(false)
  const clickTimer = useRef<number | undefined>(undefined)
  const [basemapOk, setBasemapOk] = useState(true)
  const onPick = useRef(props.onPick)
  const onRecommendation = useRef(props.onRecommendation)
  const onFacility = useRef(props.onFacility)
  const onFacilityHover = useRef(props.onFacilityHover)
  useEffect(() => {
    onPick.current = props.onPick
    onRecommendation.current = props.onRecommendation
    onFacility.current = props.onFacility
    onFacilityHover.current = props.onFacilityHover
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
      // a click on a facility pin or a recommendation marker selects it; anywhere else drops the
      // inspector pin
      map.on('click', (e) => {
        const pinHit = map?.getLayer('poi-pins')
          ? map.queryRenderedFeatures(e.point, { layers: ['poi-pins', 'facility-all'] })[0]
          : undefined
        if (pinHit) {
          onFacility.current(String(pinHit.properties.facility_id))
          return
        }
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
      // hover on a pin: popup with name, category and time; the list highlights the same entry
      const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10, className: 'poi-popup' })
      popupRef.current = popup
      for (const layer of ['poi-pins', 'facility-all']) {
        map.on('mouseenter', layer, (e) => {
          const f = e.features?.[0]
          if (!f || !map || f.geometry.type !== 'Point') return
          popup.setLngLat(f.geometry.coordinates as [number, number]).setDOMContent(popupContent(f.properties)).addTo(map)
          onFacilityHover.current(String(f.properties.facility_id))
        })
        map.on('mouseleave', layer, () => {
          popup.remove()
          onFacilityHover.current(null)
        })
      }
      map.on('load', () => {
        if (!map) return
        // data below the basemap labels, so street and place names stay readable
        const labels = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
        const sources = ['cells', 'districts', 'isochrone', 'route', 'recommendations', 'recommendation-zones', 'housing']
        sources.push('cell-selected', 'click-point', 'isochrone-reverse', 'poi-pins', 'route-label')
        sources.push('facility-areas', 'facility-access', 'facility-all')
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
        // score view: cells where everything selected is within reach (score 100)
        map.addLayer(
          {
            id: 'cells-full',
            type: 'line',
            source: 'cells',
            filter: ['==', ['get', 'full'], true],
            paint: { 'line-color': SCORE_FULL_OUTLINE, 'line-width': 1.4 },
          },
          labels,
        )
        // housing potential: cells without residents, same score colours, dashed outline
        map.addLayer(
          {
            id: 'housing-fill',
            type: 'fill',
            source: 'housing',
            layout: { visibility: 'none' },
            paint: { 'fill-opacity': 0.8, 'fill-color': fillColourExpression([...SCORE_CLASSES], false) },
          },
          labels,
        )
        map.addLayer(
          {
            id: 'housing-line',
            type: 'line',
            source: 'housing',
            layout: { visibility: 'none' },
            paint: { 'line-color': '#222222', 'line-width': 0.9, 'line-dasharray': [2, 2] },
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
        // park outlines (display note: measured to the access points on their boundary)
        map.addLayer(
          {
            id: 'facility-areas-fill',
            type: 'fill',
            source: 'facility-areas',
            layout: { visibility: 'none' },
            paint: { 'fill-color': FAC.area, 'fill-opacity': 0.14 },
          },
          labels,
        )
        map.addLayer(
          {
            id: 'facility-areas-line',
            type: 'line',
            source: 'facility-areas',
            layout: { visibility: 'none' },
            paint: { 'line-color': FAC.area, 'line-width': 1.4 },
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
          paint: { 'fill-color': ISO.forward, 'fill-opacity': 0.07 },
        })
        map.addLayer({
          id: 'isochrone-line',
          type: 'line',
          source: 'isochrone',
          paint: {
            'line-color': ISO.forward,
            'line-width': ['match', ['get', 'contour_min'], 5, 2.6, 10, 1.8, 1.2],
            'line-dasharray': [3, 1.5],
          },
        })
        // reverse isochrone: dotted, so it differs from the dashed forward one without colour
        map.addLayer({
          id: 'isochrone-reverse-fill',
          type: 'fill',
          source: 'isochrone-reverse',
          paint: { 'fill-color': ISO.reverse, 'fill-opacity': 0.06 },
        })
        map.addLayer({
          id: 'isochrone-reverse-line',
          type: 'line',
          source: 'isochrone-reverse',
          layout: { 'line-cap': 'round' },
          paint: {
            'line-color': ISO.reverse,
            'line-width': ['match', ['get', 'contour_min'], 5, 2.6, 10, 1.8, 1.2],
            'line-dasharray': [0.1, 2],
          },
        })
        // route to the next missing facility (or the picked one): solid within the budget,
        // dashed beyond it (the label says so as well)
        const beyond: ExpressionSpecification = ['==', ['get', 'beyond'], true]
        map.addLayer({
          id: 'route-casing',
          type: 'line',
          source: 'route',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': POI.routeCasing, 'line-width': 6 },
        })
        map.addLayer({
          id: 'route-line',
          type: 'line',
          source: 'route',
          filter: ['!', beyond],
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': POI.route, 'line-width': 3 },
        })
        map.addLayer({
          id: 'route-line-beyond',
          type: 'line',
          source: 'route',
          filter: beyond,
          layout: { 'line-join': 'round' },
          paint: { 'line-color': POI.route, 'line-width': 3, 'line-dasharray': [2, 1.5] },
        })
        // labels need the basemap's glyphs (not available in the offline fallback style)
        if (map.getStyle().glyphs)
          map.addLayer({
            id: 'route-label',
            type: 'symbol',
            source: 'route-label',
            layout: {
              'text-field': ['get', 'label'],
              'text-size': 12,
              'text-font': ['Noto Sans Bold'],
              'text-anchor': 'top',
              'text-offset': [0, 0.8],
              'text-allow-overlap': true,
              'text-ignore-placement': true,
            },
            paint: { 'text-color': POI.route, 'text-halo-color': POI.routeCasing, 'text-halo-width': 2 },
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
        // every facility of the category (switched on in the settings), below the pins
        map.addLayer({
          id: 'facility-all',
          type: 'circle',
          source: 'facility-all',
          layout: { visibility: 'none' },
          paint: {
            'circle-radius': 4,
            'circle-color': FAC.other,
            'circle-stroke-color': POI.routeCasing,
            'circle-stroke-width': 1,
          },
        })
        // access points of parks: where a path meets the boundary and the routing point lies
        map.addLayer({
          id: 'facility-access',
          type: 'circle',
          source: 'facility-access',
          layout: { visibility: 'none' },
          paint: {
            'circle-radius': 3,
            'circle-color': FAC.access,
            'circle-stroke-color': FAC.accessRing,
            'circle-stroke-width': 1,
          },
        })
        // facility pins: small, white with a dark ring; highlighted and next-missing pins filled
        map.addLayer({
          id: 'poi-pins',
          type: 'circle',
          source: 'poi-pins',
          paint: {
            'circle-radius': ['case', ['get', 'next'], 7, 5],
            'circle-color': ['case', ['get', 'next'], POI.next, POI.pin],
            'circle-stroke-color': ['case', ['get', 'next'], POI.nextRing, POI.ring],
            'circle-stroke-width': 1.5,
          },
        })
        if (map.getStyle().glyphs)
          map.addLayer({
            id: 'poi-labels',
            type: 'symbol',
            source: 'poi-pins',
            minzoom: POI_LABEL_MINZOOM,
            layout: {
              'text-field': ['get', 'time_label'],
              'text-size': 11,
              'text-font': ['Noto Sans Regular'],
              'text-offset': [0, 1.1],
              'text-anchor': 'top',
              'text-optional': true,
            },
            paint: { 'text-color': POI.ring, 'text-halo-color': POI.routeCasing, 'text-halo-width': 1.5 },
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

  // housing potential: shown in pin mode too, since its colours are the point of the layer
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    source('housing')?.setData(housing ?? EMPTY)
    const on = housing ? 'visible' : 'none'
    for (const id of ['housing-fill', 'housing-line']) map.setLayoutProperty(id, 'visibility', on)
    map.setPaintProperty('housing-fill', 'fill-opacity', settings.cellOpacity)
  }, [ready, housing, settings.cellOpacity])

  // Display settings: visibility, opacity and filters only, the data stays loaded.
  const coloured = !pinMode || settings.coloursWithPin
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const visible = (on: boolean) => (on ? 'visible' : 'none')
    const minResidents: ExpressionSpecification = ['>=', ['get', 'population'], settings.minResidents]
    map.setLayoutProperty('cells-fill', 'visibility', visible(settings.showCells))
    map.setLayoutProperty('cells-full', 'visibility', visible(settings.showCells && coloured))
    map.setPaintProperty('cells-fill', 'fill-opacity', coloured ? settings.cellOpacity : 0)
    map.setFilter('cells-fill', minResidents)
    map.setFilter('cells-full', ['all', ['==', ['get', 'full'], true], minResidents])
    map.setLayoutProperty('cells-outline', 'visibility', visible(settings.showCells && !coloured))
    map.setFilter('cells-outline', minResidents)
    for (const id of ['districts-line', 'districts-selected'])
      map.setLayoutProperty(id, 'visibility', visible(settings.showDistricts))
    for (const id of ['route-casing', 'route-line', 'route-line-beyond', 'route-label', 'poi-pins', 'poi-labels'])
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible(settings.showPois))
    const outlines = settings.showAllFacilities || (pinMode && settings.showPois)
    for (const id of ['facility-areas-fill', 'facility-areas-line', 'facility-access'])
      map.setLayoutProperty(id, 'visibility', visible(outlines))
    map.setLayoutProperty('facility-all', 'visibility', visible(settings.showAllFacilities))
    const hidden = Object.entries(settings.isochroneRings)
      .filter(([, shown]) => !shown)
      .map(([m]) => Number(m))
    const rings: ExpressionSpecification = ['!', ['in', ['get', 'contour_min'], ['literal', hidden]]]
    for (const id of ['isochrone-fill', 'isochrone-line', 'isochrone-reverse-fill', 'isochrone-reverse-line'])
      map.setFilter(id, rings)
    for (const id of ['isochrone-fill', 'isochrone-line'])
      map.setLayoutProperty(id, 'visibility', visible(settings.isochroneDirection !== 'reverse'))
  }, [ready, settings, coloured, pinMode])

  useEffect(() => {
    if (ready) source('isochrone-reverse')?.setData(reverseIsochrone ?? EMPTY)
  }, [ready, reverseIsochrone])

  useEffect(() => {
    if (ready)
      mapRef.current?.setFilter('districts-selected', ['==', ['get', 'district_id'], selectedDistrict ?? ''])
  }, [ready, selectedDistrict])

  // Zoom to a new inspect answer: the isochrone plus the route to the next missing facility of the
  // selected category, which can lie far outside it. A category change zooms again only when it
  // brings such a route; otherwise the view stays where the user left it.
  const fitted = useRef<{ inspect: Inspect; category: string } | null>(null)
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map || !inspect) return
    const last = fitted.current
    const nextRoute = inspect.categories.find((c) => c.category === routeCategory)?.next_facility?.route
    if (last && last.inspect === inspect && (last.category === routeCategory || !nextRoute)) return
    fitted.current = { inspect, category: routeCategory }
    const shapes = [...inspect.isochrone.features, ...(nextRoute ? [nextRoute] : [])]
    if (shapes.length)
      map.fitBounds(bboxOf({ type: 'FeatureCollection', features: shapes }), { padding: 40, maxZoom: 15, duration: 600 })
  }, [ready, inspect, routeCategory])

  useEffect(() => {
    if (!ready) return
    source('isochrone')?.setData(inspect?.isochrone ?? EMPTY)
  }, [ready, inspect])

  const byKind = useMemo(() => {
    const kinds = (kind: string) =>
      ({
        type: 'FeatureCollection',
        features: (facilities?.features ?? []).filter((f) => f.properties.kind === kind),
      }) as FeatureCollection
    const points = kinds('facility')
    // the park note of the hover popup needs to know which points are parks
    for (const f of points.features) f.properties = { ...f.properties, area: areaIds.has(String(f.properties?.facility_id)) }
    return { facility: points, area: kinds('area'), access: kinds('access') }
  }, [facilities, areaIds])
  useEffect(() => {
    if (!ready) return
    source('facility-all')?.setData(byKind.facility)
    source('facility-areas')?.setData(byKind.area)
    source('facility-access')?.setData(byKind.access)
  }, [ready, byKind])

  const pins = useMemo(
    () => poiPins(inspect, routeCategory, budgetMin, areaIds),
    [inspect, routeCategory, budgetMin, areaIds],
  )
  const route = useMemo(
    () => routeLine(inspect, routeCategory, facilityRoute, budgetMin),
    [inspect, routeCategory, facilityRoute, budgetMin],
  )
  useEffect(() => {
    if (!ready) return
    // a pin that goes away under the pointer fires no mouseleave: close its popup
    popupRef.current?.remove()
    source('poi-pins')?.setData(pins)
    source('route')?.setData(route)
    source('route-label')?.setData(routeLabelPoint(route))
  }, [ready, pins, route])

  // highlighted pins: the one under the pointer (list or map) and the picked one
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const ids = [hoveredFacility, selectedFacility].filter((id): id is string => id !== null)
    const lit: ExpressionSpecification = ['in', ['get', 'facility_id'], ['literal', ids]]
    map.setPaintProperty('poi-pins', 'circle-color', ['case', lit, POI.highlight, ['get', 'next'], POI.next, POI.pin])
    map.setPaintProperty('poi-pins', 'circle-radius', ['case', lit, 8, ['get', 'next'], 7, 5])
  }, [ready, hoveredFacility, selectedFacility])

  // a facility picked in the list: fly to it
  useEffect(() => {
    const map = mapRef.current
    const target = selectedFacility ? pins.features.find((f) => f.properties?.facility_id === selectedFacility) : undefined
    if (!ready || !map || !target || target.geometry.type !== 'Point') return
    map.flyTo({ center: target.geometry.coordinates as [number, number], zoom: Math.max(map.getZoom(), POI_LABEL_MINZOOM), duration: 600 })
    // only a new pick flies; the pins are re-derived whenever the answer changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, selectedFacility])

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
        // facility pins on the map, the kind of route and the highlighted pins, read by the smoke test
        data-highlighted={[...new Set([hoveredFacility, selectedFacility].filter(Boolean))].join(' ')}
        data-poi-pins={settings.showPois ? pins.features.length : 0}
        data-facility-layers={`${byKind.facility.features.length}/${byKind.area.features.length}/${byKind.access.features.length}`}
        data-route={settings.showPois && route.features.length ? (route.features[0].properties?.beyond ? 'beyond' : 'within') : 'none'}
        role="region"
        aria-label="Map: click to inspect a location"
      />
      {!basemapOk && <div className="map-notice">Basemap unavailable — data layers only.</div>}
      {props.children}
    </div>
  )
}
