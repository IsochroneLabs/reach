import { useRef, useState, type ReactNode } from 'react'

import { useI18n } from '../i18n/i18n'

export type Snap = 'peek' | 'half' | 'full'
const ORDER: Snap[] = ['peek', 'half', 'full']
const HEIGHT: Record<Snap, number> = { peek: 0.32, half: 0.6, full: 0.9 }

export type SheetTab = 'results' | 'profile'

/**
 * Mobile bottom sheet (docs/app_screens.md §1.2): three snap points, drag on the handle, or use
 * the handle as a button (Expand / Collapse); Escape collapses to peek. Two tabs: results and
 * profile; `hint` sits above both tabs (the programme hint).
 */
export function BottomSheet({
  tab,
  onTab,
  snap,
  onSnap,
  hint,
  profileDot,
  results,
  profile,
}: {
  tab: SheetTab
  onTab: (t: SheetTab) => void
  snap: Snap
  onSnap: (s: Snap) => void
  hint?: ReactNode
  profileDot?: boolean
  results: ReactNode
  profile: ReactNode
}) {
  const { t } = useI18n()
  const [drag, setDrag] = useState<number | null>(null)
  const start = useRef<{ y: number; h: number } | null>(null)

  const vh = () => window.innerHeight
  const heightPx = drag ?? HEIGHT[snap] * vh()
  const next = snap === 'full' ? 'peek' : ORDER[ORDER.indexOf(snap) + 1]

  return (
    <section
      className="sheet"
      aria-label={t('sheet.label')}
      style={{ height: `${Math.round(heightPx)}px` }}
      data-snap={snap}
      onKeyDown={(e) => {
        if (e.key === 'Escape' && snap !== 'peek') onSnap('peek')
      }}
    >
      <button
        type="button"
        className="sheet-handle"
        aria-label={snap === 'full' ? t('sheet.collapse') : t('sheet.expand')}
        aria-expanded={snap !== 'peek'}
        onClick={() => {
          if (drag == null) onSnap(next)
        }}
        onPointerDown={(e) => {
          start.current = { y: e.clientY, h: heightPx }
          e.currentTarget.setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          if (!start.current) return
          const dy = start.current.y - e.clientY
          if (Math.abs(dy) > 6) setDrag(Math.min(0.95 * vh(), Math.max(0.15 * vh(), start.current.h + dy)))
        }}
        onPointerUp={() => {
          if (drag != null) {
            const share = drag / vh()
            const nearest = ORDER.reduce((a, b) => (Math.abs(HEIGHT[b] - share) < Math.abs(HEIGHT[a] - share) ? b : a))
            onSnap(nearest)
            // let the click that follows pointerup see the drag and ignore it
            setTimeout(() => setDrag(null), 0)
          }
          start.current = null
        }}
      >
        <span className="sheet-grip" aria-hidden="true" />
      </button>
      <div className="sheet-tabs" role="tablist">
        {(['results', 'profile'] as SheetTab[]).map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            id={`sheet-tab-${k}`}
            aria-selected={tab === k}
            aria-controls={`sheet-panel-${k}`}
            className="sheet-tab"
            onClick={() => {
              onTab(k)
              if (snap === 'peek') onSnap('half')
            }}
          >
            {t(k === 'results' ? 'find.tab.results' : 'find.tab.profile')}
            {k === 'profile' && profileDot && <span className="dot" aria-hidden="true" />}
          </button>
        ))}
      </div>
      {hint}
      <div className="sheet-body">
        <div id="sheet-panel-results" role="tabpanel" aria-labelledby="sheet-tab-results" hidden={tab !== 'results'}>
          {results}
        </div>
        <div id="sheet-panel-profile" role="tabpanel" aria-labelledby="sheet-tab-profile" hidden={tab !== 'profile'}>
          {profile}
        </div>
      </div>
    </section>
  )
}
