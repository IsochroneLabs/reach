import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { GeoJSONSource, Map as MlMap, MapMouseEvent, Marker, Popup } from 'maplibre-gl'
// MapLibre 6 looks for its worker next to its own module; the bundle moves it, so pass the URL.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

import type { LonLat } from '../api/types'
import type { Poi, RouteLine } from '../remote/listings'
import { BASEMAP_STYLE } from '../config'
import { cellRing } from '../geo/laea'

/** One cell to draw: fit (null = no data) and whether it is highlighted. */
export interface DrawCell {
  id: string
  fit: number | null
  outline?: boolean
}

export interface MapMarker {
  key: string
  point: LonLat
  text: string
  kind: 'rank' | 'pin' | 'label' | 'poi' | 'listing'
  title: string
  onClick?: () => void
}

// Monochrome fit ramp, low → high (docs/design.md §6; same values as --fit-0 … --fit-6 in index.css).
const RAMP = ['#efefef', '#d2d2d2', '#b0b0b0', '#8c8c8c', '#686868', '#444444', '#1c1c1c']
const WASH = '#f1f1ef'
const HATCH_INK = '#666666'

/** Self-hosted streets, water, rail and green spaces (D5); cells are drawn on top. */
const DEFAULT_BASEMAP = '/basemap/style.json'

/** 6 px tile with one 45° line: cells without a fit are hatched, not coloured. */
function hatchImage(): ImageData {
  const n = 6
  const c = document.createElement('canvas')
  c.width = c.height = n
  const g = c.getContext('2d')!
  g.strokeStyle = HATCH_INK
  g.lineWidth = 1
  g.beginPath()
  g.moveTo(0, n)
  g.lineTo(n, 0)
  g.stroke()
  return g.getImageData(0, 0, n, n)
}

function toGeoJson(cells: DrawCell[]) {
  return {
    type: 'FeatureCollection' as const,
    features: cells.flatMap((c) => {
      const ring = cellRing(c.id)
      if (!ring) return []
      return [
        {
          type: 'Feature' as const,
          id: undefined,
          properties: { id: c.id, fit: c.fit ?? -1, outline: c.outline ? 1 : 0 },
          geometry: { type: 'Polygon' as const, coordinates: [ring] },
        },
      ]
    }),
  }
}

/**
 * MapLibre map (lazy-loaded). Draws cells as 100 m squares from their ids, markers for ranks and
 * places, and a popup whose content is rendered by React. Knows nothing about Find or Check.
 */
export function MapView({
  bounds,
  cells,
  showCells,
  markers,
  routes,
  pois,
  universitySites,
  focus,
  label,
  popup,
  onMapClick,
  onReady,
  onFail,
}: {
  bounds: [LonLat, LonLat] | null
  cells: DrawCell[]
  /** false = hide the 100 m grid and its legend (the map toggle) */
  showCells: boolean
  markers: MapMarker[]
  /** live walk/bike routes of the selected listing (F4.5) */
  routes: RouteLine[]
  /** destinations of the selected listing's trips, labelled (N29) */
  pois: Poi[]
  /** campus sites of the profile's programme; their buildings get the stronger outline */
  universitySites: string[]
  focus: LonLat | null
  label: string
  popup: { point: LonLat; content: ReactNode; onClose: () => void } | null
  onMapClick: (point: LonLat, cellId: string | null) => void
  onReady?: () => void
  onFail?: () => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<MlMap | null>(null)
  const ml = useRef<typeof import('maplibre-gl') | null>(null)
  const markerObjs = useRef<Marker[]>([])
  const poiObjs = useRef<Marker[]>([])
  const popupObj = useRef<Popup | null>(null)
  const [popupEl] = useState(() => document.createElement('div'))
  const [ready, setReady] = useState(false)
  const clickRef = useRef(onMapClick)
  const closeRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    clickRef.current = onMapClick
    closeRef.current = popup?.onClose ?? null
  })

  // create once
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const lib = await import('maplibre-gl')
        await import('maplibre-gl/dist/maplibre-gl.css')
        if (cancelled || !box.current) return
        ml.current = lib
        lib.setWorkerUrl(workerUrl)
        const m = new lib.Map({
          container: box.current,
          style: BASEMAP_STYLE || DEFAULT_BASEMAP,
          bounds: bounds ?? undefined,
          // phones: keep the cells above the bottom sheet (peek ≈ 32 % of the height)
          fitBoundsOptions: {
            padding: window.innerWidth < 768 ? { top: 56, left: 12, right: 12, bottom: Math.round(window.innerHeight * 0.34) } : 24,
          },
          attributionControl: false,
          dragRotate: false,
          pitchWithRotate: false,
          maxZoom: 17,
          minZoom: 11,
        })
        m.touchZoomRotate.disableRotation()
        m.addControl(new lib.NavigationControl({ showCompass: false }), 'top-right')
        m.getCanvas().setAttribute('aria-label', label)
        m.on('load', () => {
          // university buildings of the OSM extract, below the cells; the outlines go above
          m.addSource('university', { type: 'geojson', data: '/basemap/university.geojson' })
          m.addLayer({
            id: 'university-fill',
            type: 'fill',
            source: 'university',
            paint: { 'fill-color': '#111111', 'fill-opacity': 0.05 },
          })
          m.addLayer({
            id: 'university-fill-active',
            type: 'fill',
            source: 'university',
            filter: ['in', ['get', 'site'], ['literal', []]],
            paint: { 'fill-color': '#111111', 'fill-opacity': 0.12 },
          })
          m.addSource('cells', { type: 'geojson', data: toGeoJson([]) })
          m.addImage('hatch', hatchImage())
          m.addLayer({
            id: 'cells-fill',
            type: 'fill',
            source: 'cells',
            paint: {
              // seven steps, not a gradient: the legend shows the same squares
              'fill-color': ['step', ['get', 'fit'], WASH, 0, RAMP[0], 15, RAMP[1], 29, RAMP[2], 43, RAMP[3], 58, RAMP[4], 72, RAMP[5], 86, RAMP[6]],
              'fill-opacity': ['case', ['<', ['get', 'fit'], 0], 0, 0.85],
            },
          })
          m.addLayer({
            id: 'cells-nodata',
            type: 'fill',
            source: 'cells',
            filter: ['<', ['get', 'fit'], 0],
            paint: { 'fill-pattern': 'hatch' },
          })
          m.addLayer({
            id: 'cells-line',
            type: 'line',
            source: 'cells',
            // hairline in --rule: keeps the lowest step visible on the wash (1.01 : 1 without it)
            paint: { 'line-color': '#d4d4d2', 'line-width': 0.5 },
          })
          m.addLayer({
            id: 'cells-outline',
            type: 'line',
            source: 'cells',
            filter: ['==', ['get', 'outline'], 1],
            paint: { 'line-color': '#111111', 'line-width': 2.4 },
          })
          // university outlines above the cells: grey for all, ink for the programme's sites
          m.addLayer({
            id: 'university-line',
            type: 'line',
            source: 'university',
            paint: { 'line-color': '#8f8f8b', 'line-width': 1 },
          })
          m.addLayer({
            id: 'university-line-active',
            type: 'line',
            source: 'university',
            filter: ['in', ['get', 'site'], ['literal', []]],
            paint: { 'line-color': '#111111', 'line-width': 2.4 },
          })
          // live routes of the selected listing (F4.5), above the cells and outlines
          m.addSource('routes', {
            type: 'geojson',
            data: { type: 'FeatureCollection', features: [] },
          })
          m.addLayer({
            id: 'routes-casing',
            type: 'line',
            source: 'routes',
            layout: { 'line-cap': 'round', 'line-join': 'round' },
            paint: { 'line-color': '#ffffff', 'line-width': 5, 'line-opacity': 0.9 },
          })
          m.addLayer({
            id: 'routes-line',
            type: 'line',
            source: 'routes',
            layout: { 'line-cap': 'round', 'line-join': 'round' },
            paint: { 'line-color': '#111111', 'line-width': 2.4 },
          })
          setReady(true)
          onReady?.()
        })
        m.on('click', (e: MapMouseEvent) => {
          const f = m.queryRenderedFeatures(e.point, { layers: ['cells-fill'] })[0]
          clickRef.current([e.lngLat.lng, e.lngLat.lat], (f?.properties?.id as string) ?? null)
        })
        m.on('mousemove', 'cells-fill', () => (m.getCanvas().style.cursor = 'pointer'))
        m.on('mouseleave', 'cells-fill', () => (m.getCanvas().style.cursor = ''))
        map.current = m
      } catch (e) {
        console.error('map failed to load', e)
        onFail?.()
      }
    })()
    return () => {
      cancelled = true
      map.current?.remove()
      map.current = null
    }
    // created once; bounds and label are read at creation
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // cells
  useEffect(() => {
    if (!ready || !map.current) return
    ;(map.current.getSource('cells') as GeoJSONSource).setData(toGeoJson(cells))
  }, [ready, cells])

  // grid visibility (map toggle): the layers exist once the style has loaded
  useEffect(() => {
    if (!ready || !map.current) return
    const visibility = showCells ? 'visible' : 'none'
    for (const id of ['cells-fill', 'cells-nodata', 'cells-line', 'cells-outline']) {
      map.current.setLayoutProperty(id, 'visibility', visibility)
    }
  }, [ready, showCells])

  // routes of the selected listing
  useEffect(() => {
    if (!ready || !map.current) return
    const source = map.current.getSource('routes') as GeoJSONSource | undefined
    source?.setData({
      type: 'FeatureCollection',
      features: routes.map((r) => ({
        type: 'Feature' as const,
        properties: { mode: r.mode },
        geometry: { type: 'LineString' as const, coordinates: r.coordinates },
      })),
    })
  }, [ready, routes])

  // labelled destinations of the selected listing (N29): where each trip goes, how long, and
  // whether the place is open at that time (OSM opening hours)
  useEffect(() => {
    const lib = ml.current
    if (!ready || !map.current || !lib) return
    poiObjs.current.forEach((m) => m.remove())
    poiObjs.current = pois.map((poi) => {
      const el = document.createElement('div')
      el.className = `poi-marker${poi.campus ? ' is-campus' : ''}${poi.open === false ? ' is-closed' : ''}`
      const dot = document.createElement('span')
      dot.className = 'poi-dot'
      const text = document.createElement('span')
      text.className = 'poi-label'
      const name = document.createElement('strong')
      name.textContent = poi.name
      const detail = document.createElement('span')
      detail.textContent = poi.detail
      text.append(name, detail)
      el.append(dot, text)
      el.setAttribute('role', 'img')
      el.setAttribute('aria-label', `${poi.name}, ${poi.detail}`)
      return new lib.Marker({ element: el, anchor: 'left', offset: [-6, 0] }).setLngLat(poi.point).addTo(map.current!)
    })
  }, [ready, pois])

  // highlight the buildings of the programme's campus sites
  useEffect(() => {
    if (!ready || !map.current) return
    const filter = ['in', ['get', 'site'], ['literal', universitySites]] as never
    map.current.setFilter('university-line-active', filter)
    map.current.setFilter('university-fill-active', filter)
  }, [ready, universitySites])

  // markers
  useEffect(() => {
    const lib = ml.current
    if (!ready || !map.current || !lib) return
    markerObjs.current.forEach((m) => m.remove())
    markerObjs.current = markers.map((mk) => {
      if (mk.kind === 'listing') {
        // a current WG-Gesucht ad: square marker, click opens the detail in Find
        const el = document.createElement('button')
        el.type = 'button'
        el.className = 'listing-marker'
        el.title = mk.title
        el.setAttribute('aria-label', mk.title)
        el.textContent = mk.text
        el.addEventListener('click', (ev) => {
          ev.stopPropagation()
          mk.onClick?.()
        })
        return new lib.Marker({ element: el, anchor: 'center' }).setLngLat(mk.point).addTo(map.current!)
      }
      if (mk.kind === 'poi') {
        const el = document.createElement('span')
        el.className = 'poi'
        el.title = mk.title
        el.setAttribute('aria-hidden', 'true')
        el.innerHTML = '<span class="poi-dot"></span><span class="poi-text"></span>'
        ;(el.lastChild as HTMLElement).textContent = mk.text
        return new lib.Marker({ element: el, anchor: 'left', offset: [-4, 0] }).setLngLat(mk.point).addTo(map.current!)
      }
      if (mk.kind === 'label') {
        // orientation only (no basemap yet); hidden from screen readers, the cards name the areas
        const el = document.createElement('span')
        el.className = 'area-label'
        el.setAttribute('aria-hidden', 'true')
        el.textContent = mk.text
        return new lib.Marker({ element: el, anchor: 'top', offset: [0, 14] }).setLngLat(mk.point).addTo(map.current!)
      }
      const el = document.createElement('button')
      el.type = 'button'
      // MapLibre positions the element with its own transform, so the shape is an inner element
      el.className = mk.kind === 'pin' ? 'pin-wrap' : 'rank-marker'
      el.title = mk.title
      el.setAttribute('aria-label', mk.title)
      const text = mk.text.replace(/[<>&]/g, '')
      el.innerHTML = mk.kind === 'pin' ? `<span class="pin"><span>${text}</span></span>` : `<span>${text}</span>`
      if (mk.onClick) {
        el.addEventListener('click', (ev) => {
          ev.stopPropagation()
          mk.onClick?.()
        })
      }
      return new lib.Marker({ element: el, anchor: mk.kind === 'pin' ? 'bottom' : 'center' })
        .setLngLat(mk.point)
        .addTo(map.current!)
    })
  }, [ready, markers])

  // popup (React content through a portal)
  useEffect(() => {
    const lib = ml.current
    if (!ready || !map.current || !lib) return
    popupObj.current?.remove()
    popupObj.current = null
    if (!popup) return
    const p = new lib.Popup({ closeButton: true, maxWidth: '260px', offset: 8 })
      .setLngLat(popup.point)
      .setDOMContent(popupEl)
      .addTo(map.current)
    p.on('close', () => {
      if (popupObj.current === p) closeRef.current?.()
    })
    popupObj.current = p
  }, [ready, popup?.point, popupEl]) // eslint-disable-line react-hooks/exhaustive-deps

  // fly to a focus point (Find → Check, Check → nearby)
  useEffect(() => {
    if (!ready || !map.current || !focus) return
    map.current.flyTo({ center: focus, zoom: Math.max(map.current.getZoom(), 14.5), essential: true })
  }, [ready, focus])

  return (
    <>
      <div ref={box} className="map" />
      {popup && createPortal(popup.content, popupEl)}
    </>
  )
}
