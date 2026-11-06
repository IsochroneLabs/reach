// Class colours. The API delivers class names and bounds but no colours, so they live here.
// Classes are ordered (worst → best) and the colours get monotonically lighter (CIELAB L*), so
// they stay distinguishable without hue: checked with simulated deuteranopia, protanopia and
// tritanopia (Machado 2009): L* 23/51/79, min. ΔE76 ≥ 39 (facility classes) and L* 23/44/70/81,
// min. ΔE76 ≥ 25 (transit classes); the lightest class stays visible on the light basemap.
import type { ExpressionSpecification } from 'maplibre-gl'
import type { Category, TransitClass } from './types'

export const TRANSIT = 'transit'

/** Facility classes in order (methodology §4: lack 0, insufficient 0 < A < k, sufficient ≥ k). */
export const FACILITY_CLASSES = ['lack', 'insufficient', 'sufficient'] as const

const FACILITY_COLOURS: Record<string, string> = {
  lack: '#6b0f3a',
  insufficient: '#c8552f',
  sufficient: '#8fd1c0',
}

// transit supply classes (methodology §3): four steps, so its own ramp
const TRANSIT_COLOURS: Record<string, string> = {
  lack: '#6b0f3a',
  insufficient: '#b4432a',
  medium: '#e49a52',
  high: '#9ad6c6',
}

export const NO_CLASS_COLOUR = '#bdbdbd'

export const classColour = (cls: string | null | undefined, transit = false) =>
  (cls && (transit ? TRANSIT_COLOURS : FACILITY_COLOURS)[cls]) || NO_CLASS_COLOUR

export const classLabel = (cls: string) => cls.charAt(0).toUpperCase() + cls.slice(1)

export interface LegendEntry {
  cls: string
  rule: string
}

/** Legend rows with the rule of each class, from k (facilities) or the transit bounds. */
export function legendEntries(
  category: string,
  categories: Category[],
  transitClasses: TransitClass[],
): LegendEntry[] {
  if (category === TRANSIT) {
    return transitClasses.map((t) => ({
      cls: t.class,
      rule:
        t.upper === null
          ? `≥ ${t.lower.toLocaleString('en')} departures`
          : t.lower === t.upper
            ? `${t.lower} departures`
            : `${t.lower.toLocaleString('en')}–${t.upper.toLocaleString('en')} departures`,
    }))
  }
  const k = categories.find((c) => c.id === category)?.k ?? 1
  const unit = (n: number) => (n === 1 ? 'facility' : 'facilities')
  return FACILITY_CLASSES.filter((cls) => !(cls === 'insufficient' && k <= 1)).map((cls) => ({
    cls,
    rule:
      cls === 'lack'
        ? `0 facilities`
        : cls === 'insufficient'
          ? k === 2
            ? `1 facility`
            : `1–${k - 1} facilities`
          : `≥ ${k} ${unit(k)}`,
  }))
}

/** MapLibre `fill-color` expression on the `class` property. */
export function fillColourExpression(classes: string[], transit: boolean): ExpressionSpecification {
  const pairs = classes.flatMap((cls) => [cls, classColour(cls, transit)])
  // the tuple type needs at least one label/colour pair, which `classes` always provides
  return ['match', ['get', 'class'], ...pairs, NO_CLASS_COLOUR] as unknown as ExpressionSpecification
}
