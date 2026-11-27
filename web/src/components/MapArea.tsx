import { lazy, Suspense, useMemo, useState } from 'react'

import type { LonLat } from '../api/types'
import { nearbyCells } from '../logic/nearby'
import { cellCentre, cellIdAt } from '../geo/laea'
import { useI18n } from '../i18n/i18n'
import { useFit } from '../remote/fit'
import { useListings } from '../remote/listings'
import { useRefs } from '../remote/refs'
import { MAX_PLACES } from '../settings'
import { useStore } from '../state/store'
import { storage } from '../state/storage'
import type { DrawCell, MapMarker } from './MapView'
import { useToast } from './Toast'

const MapView = lazy(() => import('./MapView').then((m) => ({ default: m.MapView })))
const CELLS_KEY = 'reach.v1.cells'

export function FitLegend() {
  const { t } = useI18n()
  return (
    <div className="legend" aria-hidden="true">
      <strong>{t('fit.legend')}</strong>
      <div className="legend-ramp">
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <i key={i} className={`legend-step step-${i}`} />
        ))}
      </div>
      <div className="legend-scale">
        <span>0 · {t('fit.legend.low')}</span>
        <span>{t('fit.legend.high')} · 100</span>
      </div>
      <div className="legend-none">
        <i /> {t('fit.legend.none')}
      </div>
    </div>
  )
}

/** The map of Find and Check: cell fits, rank markers, place pins, popups. */
export function MapArea() {
  const { t, duration } = useI18n()
  const refs = useRefs()
  const fit = useFit()
  const { state, dispatch } = useStore()
  const toast = useToast()
  const listings = useListings()
  const { data: listingsData, select: selectListing, selected: selectedListing, routes } = listings
  const [popupCell, setPopupCell] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [showCells, setShowCells] = useState(() => storage.get(CELLS_KEY) !== '0')

  const toggleCells = () => {
    const next = !showCells
    setShowCells(next)
    storage.set(CELLS_KEY, next ? '1' : '0')
  }

  // opening a WG hides the fit cells so the streets, outlines and routes are readable; closing
  // restores the student's grid preference. Turning the grid back on while the WG is open sticks
  // (state adjusted during render, https://react.dev/learn/you-might-not-need-an-effect).
  const selectedId = listings.selected?.listing_id ?? null
  const [gridSeenFor, setGridSeenFor] = useState<string | null>(selectedId)
  const [gridBefore, setGridBefore] = useState<boolean | null>(null)
  if (gridSeenFor !== selectedId) {
    setGridSeenFor(selectedId)
    if (selectedId && showCells) {
      setGridBefore(true)
      setShowCells(false)
    } else if (!selectedId && gridBefore) {
      setShowCells(gridBefore)
      setGridBefore(null)
    }
  }

  const extra = useExtraCells()
  const cells: DrawCell[] = useMemo(() => {
    if (!fit.data || fit.noWeight) return []
    return Object.entries(fit.data.cells).map(([id, [f]]) => ({ id, fit: f, outline: extra.has(id) }))
  }, [fit.data, fit.noWeight, extra])

  const addPlace = (cellId: string, point: LonLat, label: string | null) => {
    if (state.places.length >= MAX_PLACES) {
      toast(t('check.max'))
      return
    }
    dispatch({ type: 'addPlace', place: { point, cellId, label } })
  }

  // chosen destinations: favourite supermarkets and sport/hobby categories (F2.5)
  const pois: MapMarker[] = useMemo(() => {
    if (refs.kind !== 'ok') return []
    const keys = Object.entries(state.profile.destinations).filter(([, v]) => v.importance > 0).map(([k]) => k)
    const favourites = 'grocery' in state.profile.destinations ? (state.profile.labels?.grocery ?? []) : []
    return refs.refs.labelDestinations
      .filter((d) =>
        d.destination_type === 'grocery'
          ? d.labels.some((l) => favourites.includes(l))
          : d.labels.some((l) => keys.includes(`${d.destination_type}:${l}`)),
      )
      .map((d) => ({
        key: `poi-${d.destination_id}`,
        point: d.point,
        text: d.name ?? '',
        kind: 'poi' as const,
        title: `${t('map.chosenPlaces')}: ${d.name ?? ''}`,
      }))
  }, [refs, state.profile, t])

  // buildings of the programme's campus sites get the stronger outline (F3.4/F4.5)
  const universitySites = useMemo(() => {
    if (refs.kind !== 'ok') return []
    if (state.profile.programme) {
      return refs.refs.programmes.find((p) => p.programme === state.profile.programme)?.sites ?? []
    }
    return refs.refs.sites.filter((s) => (s.default_share ?? 0) > 0).map((s) => s.site_id)
  }, [refs, state.profile.programme])

  // open WG-Gesucht ads in Find (F4.7): one square per listing with a point
  const listingPins: MapMarker[] = useMemo(() => {
    if (!listingsData) return []
    const chosen = selectedListing ? [selectedListing] : listingsData.slice(0, 10)
    return chosen
      .filter((l) => l.point)
      .map((l) => {
        const eur = l.rent_total_eur ?? l.rent_cold_eur
        return {
          key: `listing-${l.listing_id}`,
          point: l.point!,
          text: t('listings.marker'),
          kind: 'listing' as const,
          title: [l.title ?? t('listings.untitled'), eur != null ? t('listings.eur', { eur }) : null]
            .filter(Boolean)
            .join(' · '),
          onClick: () => selectListing(l.listing_id),
        }
      })
  }, [listingsData, selectListing, selectedListing, t])

  const markers: MapMarker[] = useMemo(() => {
    const pins: MapMarker[] = state.places
      .filter((p) => state.mode === 'check' || p.id === state.nearbyOf)
      .map((p) => ({
        key: `pin-${p.id}`,
        point: p.point,
        text: p.id,
        kind: 'pin' as const,
        title: `${t('check.place', { id: p.id })}: ${p.label ?? t('check.pin')}`,
      }))
    const labels: MapMarker[] = (fit.data?.areas ?? []).flatMap((a) => {
      const c = cellCentre(a.best_cell_id)
      return c ? [{ key: `label-${a.area_id}`, point: c, text: a.name, kind: 'label' as const, title: a.name }] : []
    })
    if (state.mode === 'find') return pois.concat(listingPins, labels, pins)
    return pois.concat(state.places.map((p) => ({
      key: p.id,
      point: p.point,
      text: p.id,
      kind: 'pin' as const,
      title: `${t('check.place', { id: p.id })}: ${p.label ?? t('check.pin')}`,
    })))
  }, [state.mode, state.places, state.nearbyOf, fit.data, t, pois, listingPins])

  const popupData = popupCell && fit.data?.cells[popupCell]
  const popup =
    state.mode === 'find' && popupCell && popupData
      ? {
          point: cellCentre(popupCell)!,
          onClose: () => setPopupCell(null),
          content: (
            <div className="cell-popup" data-testid="cell-popup">
              <p className="cell-popup-fit">
                <strong>{t('find.cell.fit', { fit: popupData[0] ?? '–' })}</strong>
                {popupData[1] != null && <span className="muted"> · {t('weekly.short', { time: duration(popupData[1]) })}</span>}
              </p>
              <button
                type="button"
                className="btn btn-small"
                onClick={() => {
                  setPopupCell(null)
                  addPlace(popupCell, cellCentre(popupCell)!, null)
                }}
              >
                {t('find.cell.check')}
              </button>
            </div>
          ),
        }
      : null

  const onMapClick = (point: LonLat, cellId: string | null) => {
    if (state.mode === 'find') {
      setPopupCell(cellId)
      return
    }
    addPlace(cellId ?? cellIdAt(point), point, null)
  }

  const bounds = refs.kind === 'ok' ? refs.refs.meta.bounds : null
  return (
    <div className="map-wrap" data-testid="map">
      {bounds && !failed && (
        <Suspense fallback={null}>
          <MapView
            bounds={bounds}
            cells={cells}
            showCells={showCells}
            markers={markers}
            routes={routes}
            universitySites={universitySites}
            focus={selectedListing?.point ?? state.focus}
            label={t('map.label')}
            popup={popup}
            onMapClick={onMapClick}
            onReady={() => setLoaded(true)}
            onFail={() => setFailed(true)}
          />
        </Suspense>
      )}
      {(!bounds || failed) && <div className="map-placeholder" />}
      {!loaded && !failed && <p className="map-status">{t('map.loading')}</p>}
      {failed && <p className="map-status">{t('map.failed')}</p>}
      {loaded && fit.updating && (
        <p className="map-status" role="status">
          {t('status.updating')}
        </p>
      )}
      {loaded && state.mode === 'check' && state.places.length < MAX_PLACES && (
        <p className="map-hint">{t('map.pinHint')}</p>
      )}
      <div className="map-toggles" role="group" aria-label={t('map.toggles')}>
        <button
          type="button"
          className="map-toggle"
          aria-pressed={showCells}
          title={t('map.toggle.cells.title')}
          onClick={toggleCells}
        >
          {t('map.toggle.cells')}
        </button>
      </div>
      {showCells && <FitLegend />}
      <p className="map-attrib">{t('map.attribution')}</p>
    </div>
  )
}

/** Cells to outline: in Find, the better cells near a place ("better places nearby"). */
function useExtraCells(): Set<string> {
  const { state } = useStore()
  const fit = useFit()
  return useMemo(() => new Set(nearbyCells(state, fit.data?.cells)), [state, fit.data])
}
