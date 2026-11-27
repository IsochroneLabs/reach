import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from 'react'

import { useI18n } from '../i18n/i18n'
import { storage } from '../state/storage'

const KEY = 'reach.v1.panels'
/** narrowest results column, and the map never gets narrower than this */
const RIGHT_MIN = 300
const MAP_MIN = 320
const LEFT_W = 360
const STEP = 40

interface PanelState {
  left: boolean
  right: boolean
  /** null = the default width of the current view */
  width: number | null
}

function load(): PanelState {
  try {
    const v = JSON.parse(storage.get(KEY) ?? '{}') as Partial<PanelState>
    return {
      left: v.left !== false,
      right: v.right !== false,
      width: typeof v.width === 'number' && v.width >= RIGHT_MIN ? v.width : null,
    }
  } catch {
    return { left: true, right: true, width: null }
  }
}

/**
 * Both side columns can be folded away; the results column can be dragged wider, e.g. to see three
 * places side by side in the comparison (N30). Kept in localStorage, never in the link.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useSidePanels(defaultWidth: number, hasLeft: boolean) {
  const [s, setS] = useState(load)
  useEffect(() => storage.set(KEY, JSON.stringify(s)), [s])
  const width = s.width ?? defaultWidth
  const style = {
    '--left-w': hasLeft && s.left ? `${LEFT_W}px` : '0px',
    '--right-w': s.right ? `${width}px` : '0px',
  } as CSSProperties
  return {
    ...s,
    width,
    style,
    toggleLeft: () => setS((x) => ({ ...x, left: !x.left })),
    toggleRight: () => setS((x) => ({ ...x, right: !x.right })),
    setWidth: (w: number | null) => setS((x) => ({ ...x, width: w, right: true })),
  }
}

/** Fold buttons at the inner edges of both columns and the drag handle of the results column. */
export function PanelEdges({
  panels,
  hasLeft,
}: {
  panels: ReturnType<typeof useSidePanels>
  hasLeft: boolean
}) {
  const { t } = useI18n()
  const handle = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)
  const { setWidth, width } = panels

  const clamp = useCallback(
    (w: number) => {
      const layout = handle.current?.parentElement
      const total = layout?.clientWidth ?? window.innerWidth
      const left = hasLeft && panels.left ? LEFT_W : 0
      return Math.round(Math.max(RIGHT_MIN, Math.min(w, total - left - MAP_MIN)))
    },
    [hasLeft, panels.left],
  )

  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    setDragging(true)
  }
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return
    const rect = handle.current?.parentElement?.getBoundingClientRect()
    if (rect) setWidth(clamp(rect.right - e.clientX))
  }
  const onUp = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.releasePointerCapture(e.pointerId)
    setDragging(false)
  }
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowLeft') setWidth(clamp(width + STEP))
    else if (e.key === 'ArrowRight') setWidth(clamp(width - STEP))
    else if (e.key === 'Home') setWidth(null)
    else return
    e.preventDefault()
  }

  return (
    <>
      {hasLeft && (
        <button
          type="button"
          className="panel-fold panel-fold-left"
          aria-expanded={panels.left}
          aria-label={t(panels.left ? 'panels.hideProfile' : 'panels.showProfile')}
          title={t(panels.left ? 'panels.hideProfile' : 'panels.showProfile')}
          onClick={panels.toggleLeft}
        >
          <span aria-hidden="true">{panels.left ? '‹' : '›'}</span>
        </button>
      )}
      <button
        type="button"
        className="panel-fold panel-fold-right"
        aria-expanded={panels.right}
        aria-label={t(panels.right ? 'panels.hideResults' : 'panels.showResults')}
        title={t(panels.right ? 'panels.hideResults' : 'panels.showResults')}
        onClick={panels.toggleRight}
      >
        <span aria-hidden="true">{panels.right ? '›' : '‹'}</span>
      </button>
      {panels.right && (
        <div
          ref={handle}
          className={`panel-resize${dragging ? ' is-dragging' : ''}`}
          role="separator"
          aria-orientation="vertical"
          aria-label={t('panels.resize')}
          aria-valuenow={width}
          aria-valuemin={RIGHT_MIN}
          tabIndex={0}
          title={t('panels.resize')}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
          onDoubleClick={() => setWidth(null)}
          onKeyDown={onKey}
        />
      )}
    </>
  )
}
