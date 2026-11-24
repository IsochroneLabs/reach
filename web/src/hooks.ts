import { useEffect, useState } from 'react'

/** Breakpoints of docs/app_screens.md §1: S < 768 px, M 768–1199 px, L ≥ 1200 px. */
export type Breakpoint = 'S' | 'M' | 'L'

function current(): Breakpoint {
  if (window.matchMedia('(min-width: 1200px)').matches) return 'L'
  if (window.matchMedia('(min-width: 768px)').matches) return 'M'
  return 'S'
}

export function useBreakpoint(): Breakpoint {
  const [bp, setBp] = useState<Breakpoint>(current)
  useEffect(() => {
    const qs = ['(min-width: 1200px)', '(min-width: 768px)'].map((q) => window.matchMedia(q))
    const on = () => setBp(current())
    qs.forEach((q) => q.addEventListener('change', on))
    return () => qs.forEach((q) => q.removeEventListener('change', on))
  }, [])
  return bp
}

/** The value, settled for `ms` (restarts on every change). */
export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const h = setTimeout(() => setV(value), ms)
    return () => clearTimeout(h)
  }, [value, ms])
  return v
}
