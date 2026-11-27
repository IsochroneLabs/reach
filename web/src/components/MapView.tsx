import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { GeoJSONSource, Map as MlMap, MapMouseEvent, Marker, Popup } from 'maplibre-gl'
// MapLibre 6 looks for its worker next to its own module; the bundle moves it, so pass the URL.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

import type { LonLat } from '../api/types'
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
  kind: 'rank' | 'pin' | 'label' | 'poi'
  title: string
  onClick?: () => void
}

// Monochrome fit ramp, low → high (docs/design.md §6; same values as --fit-0 … --fit-6 in index.css).
const RAMP = ['#efefef', '#d2d2d2', '#b0b0b0', '#8c8c8c', '#686868', '#444444', '#1c1c1c']
const WASH = '#f1f1ef'
const HATCH_INK = '#666666'

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

/** Plain background (D5 not built yet, notes N18): no third-party tiles, glyphs or sprites. */
const PLAIN_STYLE = {
  version: 8 as const,
  sources: {},
  layers: [{ id: 'bg', type: 'background' as const, paint: { 'background-color': WASH } }],
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
  markers,
  focus,
  label,
  popup,
  onMapClick,
  onReady,
  onFail,
}: {
  bounds: [LonLat, LonLat] | null
  cells: DrawCell[]
  markers: MapMarker[]
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
          style: BASEMAP_STYLE || PLAIN_STYLE,
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
            paint: { 'line-color': '#111111', 'line-width': 2 },
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

  // markers
  useEffect(() => {
    const lib = ml.current
    if (!ready || !map.current || !lib) return
    markerObjs.current.forEach((m) => m.remove())
    markerObjs.current = markers.map((mk) => {
      if (mk.kind === 'poi') {
        // a chosen destination (favourite supermarket, sport or hobby place): dot + short name
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
