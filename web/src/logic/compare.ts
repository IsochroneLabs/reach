/**
 * The "In short" lines of the comparison (docs/app_screens.md §1.4), as structured facts; the
 * component words them with the i18n keys compare.*. Pure.
 */

export interface PlaceFacts {
  id: string
  name: string
  fit: number | null
  weeklyMin: number | null
  rentEur: number | null
  /** destination label → fastest minutes in the student's modes */
  minutes: Record<string, number | null>
}

export type Fact =
  | { kind: 'fitBetter'; a: string; b: string; fa: number; fb: number }
  | { kind: 'fitEqual'; a: string; b: string }
  | { kind: 'rentVsTime'; a: string; eur: number; min: number }
  | { kind: 'rentAndTime'; a: string; eur: number; min: number }
  | { kind: 'timeOnly'; a: string; min: number }
  | { kind: 'destDiff'; a: string; dest: string; min: number }

/** Facts for two places: fit, rent vs. weekly time, the 1–2 largest per-destination gaps. */
export function compareTwo(x: PlaceFacts, y: PlaceFacts, equalDelta: number): Fact[] {
  const out: Fact[] = []
  if (x.fit != null && y.fit != null) {
    if (Math.abs(x.fit - y.fit) < equalDelta) out.push({ kind: 'fitEqual', a: x.name, b: y.name })
    else {
      const [hi, lo] = x.fit > y.fit ? [x, y] : [y, x]
      out.push({ kind: 'fitBetter', a: hi.name, b: lo.name, fa: hi.fit!, fb: lo.fit! })
    }
  }
  if (x.weeklyMin != null && y.weeklyMin != null) {
    const saved = Math.round(Math.abs(x.weeklyMin - y.weeklyMin))
    if (saved >= 5) {
      const [fast, slow] = x.weeklyMin < y.weeklyMin ? [x, y] : [y, x]
      if (fast.rentEur != null && slow.rentEur != null && fast.rentEur !== slow.rentEur) {
        const eur = Math.round(Math.abs(fast.rentEur - slow.rentEur))
        out.push(
          fast.rentEur > slow.rentEur
            ? { kind: 'rentVsTime', a: fast.name, eur, min: saved }
            : { kind: 'rentAndTime', a: fast.name, eur, min: saved },
        )
      } else out.push({ kind: 'timeOnly', a: fast.name, min: saved })
    }
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
