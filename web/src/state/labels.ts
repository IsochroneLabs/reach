/**
 * Destination labels in the student profile (F2.5, methodology §3.1): favourite supermarkets
 * (grocery brands and groups, QF3) and sport/hobby categories, each a destination of its own
 * under the key `<type>:<category>` (QF4). Standalone (types only), so node --test can load it.
 */
import type { DestinationLabel, DestinationType, Label } from '../api/types'

/** `sport:tennis` → ['sport', 'tennis']; a plain type → [type, null]. */
export function splitKey(key: string): [string, string | null] {
  const i = key.indexOf(':')
  return i < 0 ? [key, null] : [key.slice(0, i), key.slice(i + 1)]
}

/** Types whose labels are categories: containers, never a term themselves. */
export function isContainer(t: DestinationType): boolean {
  return !!t.labels?.some((l) => l.kind === 'category')
}

export interface DestinationKey {
  key: string
  type: DestinationType
  category: DestinationLabel | null
  name: Label
}

/** Resolves a profile key (type or category) against the reference list; null if unknown. */
export function resolveKey(key: string, types: DestinationType[]): DestinationKey | null {
  const [typeKey, cat] = splitKey(key)
  const type = types.find((t) => t.destination_type === typeKey)
  if (!type) return null
  if (cat == null) return isContainer(type) ? null : { key, type, category: null, name: type.label }
  const category = type.labels?.find((l) => l.kind === 'category' && l.label === cat) ?? null
  return category ? { key, type, category, name: category.name } : null
}

/** Every key a student can add: plain types and the categories of container types. */
export function choosableKeys(types: DestinationType[]): DestinationKey[] {
  return types.flatMap((type): DestinationKey[] =>
    isContainer(type)
      ? (type.labels ?? [])
          .filter((l) => l.kind === 'category' && l.destinations > 0)
          .map((category) => ({ key: `${type.destination_type}:${category.label}`, type, category, name: category.name }))
      : [{ key: type.destination_type, type, category: null, name: type.label }],
  )
}

/** Brands and groups of the grocery type that the student can pick as favourites. */
export function groceryLabels(types: DestinationType[]): DestinationLabel[] {
  const g = types.find((t) => t.destination_type === 'grocery')
  return (g?.labels ?? []).filter((l) => (l.kind === 'brand' || l.kind === 'group') && l.destinations > 0)
}
