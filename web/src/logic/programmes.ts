// Programme search and building names for the profile panel (N31).

/** lower case, no accents, ß → ss: "Wirtschaftsinformatik" matches "wirtschafts", "Ökonomie" "oko". */
export function fold(text: string): string {
  return text
    .toLowerCase()
    .replace(/ß/g, 'ss')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
}

/** Programmes whose label contains every word of the query, shortest label first. */
export function matchProgrammes(list: { id: string; text: string }[], query: string): string[] {
  const words = fold(query).split(/\s+/).filter(Boolean)
  return list
    .filter((p) => words.every((w) => fold(p.text).includes(w)))
    .sort((a, b) => a.text.length - b.text.length || a.text.localeCompare(b.text))
    .map((p) => p.id)
}

/** Building name without its address: "WiWi Sem Mohl (Mohlstraße 36)" → "WiWi Sem Mohl". */
export function shortName(name: string): string {
  return name.replace(/\s*\([^()]*\)$/, '')
}
