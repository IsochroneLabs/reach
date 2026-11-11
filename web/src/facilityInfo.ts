// What the app shows about a facility besides its name and time: informative OSM tags as stored
// (no parsing of opening hours) and links. Display only; counts never use these tags.
import type { FacilityTags } from './types'

export interface InfoLine {
  label: string
  value: string
  /** Set for values that are links (only http/https URLs). */
  href?: string
}

const WHEELCHAIR: Record<string, string> = {
  yes: '♿ wheelchair accessible',
  limited: '♿ partly wheelchair accessible',
  no: '♿ not wheelchair accessible',
  designated: '♿ designed for wheelchair users',
}

/** Only web links: a tag value must never become a `javascript:` URL. */
export function safeUrl(value: string | undefined): string | undefined {
  if (!value) return undefined
  const url = /^https?:\/\//i.test(value) ? value : `https://${value}`
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : undefined
  } catch {
    return undefined
  }
}

/** Plain-text lines for the popup and the picked facility; empty if OSM has none of the tags. */
export function infoLines(tags: FacilityTags): InfoLine[] {
  const lines: InfoLine[] = []
  const add = (label: string, value: string | undefined, href?: string) => value && lines.push({ label, value, href })
  add('Opening hours', tags.opening_hours)
  if (tags.wheelchair) add('Access', WHEELCHAIR[tags.wheelchair] ?? `♿ wheelchair: ${tags.wheelchair}`)
  const street = [tags['addr:street'], tags['addr:housenumber']].filter(Boolean).join(' ')
  const town = tags['addr:postcode']
  add('Address', [street, town].filter(Boolean).join(', '))
  add('Speciality', tags['healthcare:speciality']?.replaceAll(';', ', '))
  add('Brand', tags.brand ?? tags.operator)
  const site = tags.website ?? tags['contact:website']
  add('Website', site, safeUrl(site))
  const phone = tags.phone ?? tags['contact:phone']
  add('Phone', phone)
  return lines
}

/** A search link only (no API, no rating): the name and the coordinates of the routing point. */
export function googleMapsUrl(name: string | null, point: [number, number]): string {
  const query = `${name ?? ''} ${point[1].toFixed(6)},${point[0].toFixed(6)}`.trim()
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`
}

export const PARK_NOTE =
  'Measured to the nearest park entrance (where a path meets the boundary). A park counts once.'
