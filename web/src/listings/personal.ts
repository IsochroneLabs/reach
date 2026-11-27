/**
 * The personal lines of the application text (F4.8): kept in localStorage only, never sent to the
 * server, deletable with one call (methodology §8.2).
 */
import type { PersonalLines } from './application.ts'

/** The app passes `storage` (state/storage.ts); tests pass a map. */
export interface KeyValueStore {
  get(key: string): string | null
  set(key: string, value: string): void
  remove(key: string): void
}

export const PERSONAL_KEY = 'reach.application.v1'
const FIELDS: (keyof PersonalLines)[] = ['name', 'age', 'about', 'extra1', 'extra2']
/** Longest line kept; the about line may be a short paragraph. */
const MAX_LEN: Record<keyof PersonalLines, number> = { name: 80, age: 3, about: 600, extra1: 200, extra2: 200 }

export const emptyLines = (): PersonalLines => ({ name: '', age: '', about: '', extra1: '', extra2: '' })

/** Unknown keys and non-strings are dropped, long lines cut. */
export function sanitizeLines(raw: unknown): PersonalLines {
  const out = emptyLines()
  if (raw && typeof raw === 'object') {
    for (const f of FIELDS) {
      const v = (raw as Record<string, unknown>)[f]
      if (typeof v === 'string') out[f] = v.slice(0, MAX_LEN[f])
    }
  }
  return out
}

export function loadLines(store: KeyValueStore): PersonalLines {
  const raw = store.get(PERSONAL_KEY)
  if (!raw) return emptyLines()
  try {
    return sanitizeLines(JSON.parse(raw))
  } catch {
    return emptyLines()
  }
}

export function saveLines(store: KeyValueStore, lines: PersonalLines): void {
  const clean = sanitizeLines(lines)
  if (FIELDS.every((f) => clean[f].trim() === '')) store.remove(PERSONAL_KEY)
  else store.set(PERSONAL_KEY, JSON.stringify(clean))
}

export function clearLines(store: KeyValueStore): void {
  store.remove(PERSONAL_KEY)
}
