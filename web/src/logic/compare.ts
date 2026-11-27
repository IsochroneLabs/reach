/**
 * The "In short" lines of the comparison (docs/app_screens.md §1.4), as structured facts; the
 * component words them with the i18n keys compare.*. Pure.
 */

export interface PlaceFacts {
  id: string
  name: string
  fit: number | null
  rentEur: number | null
  /** destination label → fastest minutes in the student's modes */
  minutes: Record<string, number | null>
}

export type Fact =
  | { kind: 'fitBetter'; a: string; b: string; fa: number; fb: number }
  | { kind: 'fitEqual'; a: string; b: string }
  | { kind: 'cheaper'; a: string; eur: number }
  | { kind: 'destDiff'; a: string; dest: string; min: number }

/** Facts for two places: fit, rent, the 1–2 largest per-destination gaps. */
export function compareTwo(x: PlaceFacts, y: PlaceFacts, equalDelta: number): Fact[] {
  const out: Fact[] = []
  if (x.fit != null && y.fit != null) {
    if (Math.abs(x.fit - y.fit) < equalDelta) out.push({ kind: 'fitEqual', a: x.name, b: y.name })
    else {
      const [hi, lo] = x.fit > y.fit ? [x, y] : [y, x]
      out.push({ kind: 'fitBetter', a: hi.name, b: lo.name, fa: hi.fit!, fb: lo.fit! })
    }
  }
  if (x.rentEur != null && y.rentEur != null && Math.round(Math.abs(x.rentEur - y.rentEur)) >= 1) {
    const cheap = x.rentEur < y.rentEur ? x : y
    out.push({ kind: 'cheaper', a: cheap.name, eur: Math.round(Math.abs(x.rentEur - y.rentEur)) })
  }
  const gaps = Object.keys(x.minutes)
    .filter((d) => x.minutes[d] != null && y.minutes[d] != null)
    .map((d) => ({ d, diff: (x.minutes[d] as number) - (y.minutes[d] as number) }))
    .filter((g) => Math.abs(g.diff) >= 5)
    .sort((p, q) => Math.abs(q.diff) - Math.abs(p.diff))
    .slice(0, 2)
  for (const g of gaps) {
    out.push({ kind: 'destDiff', a: g.diff < 0 ? x.name : y.name, dest: g.d, min: Math.round(Math.abs(g.diff)) })
  }
  return out
}
