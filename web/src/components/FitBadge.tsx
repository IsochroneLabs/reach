/** The fit as a number in mono, tabular (docs/design.md §6 "big number"); never a coloured badge. */
export function FitBadge({ fit, size = 'm' }: { fit: number | null; size?: 's' | 'm' | 'l' }) {
  return <span className={`fit-num fit-${size}`}>{fit ?? '–'}</span>
}
