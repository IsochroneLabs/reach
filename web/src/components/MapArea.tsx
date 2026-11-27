import { lazy, Suspense, useMemo, useState } from 'react'

import type { LonLat } from '../api/types'
import { nearbyCells } from '../logic/nearby'
import { cellCentre, cellIdAt } from '../geo/laea'
import { useI18n } from '../i18n/i18n'
import { useFit } from '../remote/fit'
import { useRefs } from '../remote/refs'
import { MAX_PLACES } from '../settings'
import { useStore } from '../state/store'
import type { DrawCell, MapMarker } from './MapView'
import { useToast } from './Toast'

const MapView = lazy(() => import('./MapView').then((m) => ({ default: m.MapView })))

export function FitLegend() {
  const { t } = useI18n()
  return (
    <div className="legend" aria-hidden="true">
      <strong>{t('fit.legend')}</strong>
      <div className="legend-ramp" />
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
  const [popupCell, setPopupCell] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)

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
    if (state.mode === 'check') {
      return pois.concat(state.places.map((p) => ({
        key: p.id,
        point: p.point,
        text: p.id,
        kind: 'pin' as const,
        title: `${t('check.place', { id: p.id })}: ${p.label ?? t('check.pin')}`,
      })))
    }
    const labels: MapMarker[] = (fit.data?.areas ?? []).flatMap((a) => {
      const c = cellCentre(a.best_cell_id)
      return c ? [{ key: `label-${a.area_id}`, point: c, text: a.name, kind: 'label' as const, title: a.name }] : []
    })
    return pois.concat(labels, pins, (fit.data?.areas ?? []).slice(0, 3).flatMap((a, i) => {
      const c = cellCentre(a.best_cell_id)
      return c
        ? [{
            key: a.area_id,
            point: c,
            text: String(i + 1),
            kind: 'rank' as const,
            title: `${i + 1}. ${a.name}`,
            onClick: () => setPopupCell(a.best_cell_id),
          }]
        : []
    }))
  }, [state.mode, state.places, state.nearbyOf, fit.data, t, pois])

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
            markers={markers}
            focus={state.focus}
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
      <FitLegend />
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
