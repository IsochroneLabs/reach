/**
 * Application text for a listing (methodology §8.2, architecture O26, step F4.8).
 *
 * Templates in German and English, three tones. Filled only from what the student chose or typed
 * and what the listing says: a missing value stays a visible gap in [brackets], nothing is
 * invented, only the hobbies passed in are named. Runs in the browser; nothing is sent anywhere.
 */
import { APPLICATION_MAX_CHARS, APPLICATION_MAX_HOBBIES } from '../settings.ts'

export type Lang = 'de' | 'en'
export type Tone = 'casual' | 'friendly' | 'formal'
export type Degree = 'bachelor' | 'master'

/** Up to five lines the student types; kept in localStorage only (see personal.ts). */
export interface PersonalLines {
  name: string
  age: string
  about: string
  extra1: string
  extra2: string
}

export interface ApplicationInput {
  lang: Lang
  tone: Tone
  student: {
    /** display name of the programme in `lang`, null if none chosen */
    programme: string | null
    degree: Degree | null
    semester: number | null
    /** display names of the chosen sport and hobby categories to mention */
    hobbies: string[]
  }
  personal: PersonalLines
  listing: {
    kind: 'wg_room' | 'studio' | 'flat' | null
    title: string | null
    household_size: number | null
    /** ISO date "2026-12-01" */
    available_from: string | null
  }
}

export interface ApplicationDraft {
  text: string
  /** the bracketed gaps left in the text, in order */
  gaps: string[]
  tooLong: boolean
}

const GAP = {
  de: { name: 'Name', age: 'Alter', programme: 'Studiengang', semester: 'Semester', degree: 'Bachelor/Master', date: 'Einzugsdatum', about: 'ein, zwei Sätze über dich' },
  en: { name: 'name', age: 'age', programme: 'programme', semester: 'semester', degree: 'Bachelor/Master', date: 'move-in date', about: 'a sentence or two about you' },
} as const

const clean = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim()

function list(items: string[], lang: Lang): string {
  const and = lang === 'de' ? 'und' : 'and'
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} ${and} ${items[items.length - 1]}`
}

function longDate(iso: string, lang: Lang): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return null
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])))
  return new Intl.DateTimeFormat(lang === 'de' ? 'de-DE' : 'en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(d)
}

/** Builds the draft; pure, so the same input always gives the same text. */
export function draftApplication(input: ApplicationInput): ApplicationDraft {
  const { lang, tone, student, personal, listing } = input
  const gaps: string[] = []
  const gap = (key: keyof (typeof GAP)['de']) => {
    const g = `[${GAP[lang][key]}]`
    gaps.push(g)
    return g
  }
  const name = clean(personal.name) || gap('name')
  const age = clean(personal.age) || gap('age')
  const programme = clean(student.programme) || gap('programme')
  const semester = student.semester != null && student.semester > 0 ? String(student.semester) : gap('semester')
  const degree = student.degree ? (student.degree === 'bachelor' ? 'Bachelor' : 'Master') : gap('degree')
  const date = (listing.available_from && longDate(listing.available_from, lang)) || gap('date')
  const about = clean(personal.about) || gap('about')
  const extras = [personal.extra1, personal.extra2].map(clean).filter(Boolean)
  const hobbies = student.hobbies.map(clean).filter(Boolean).slice(0, APPLICATION_MAX_HOBBIES)
  const title = clean(listing.title)
  const t = (lang === 'de' ? de : en)[tone]
  const parts = [
    t.greeting(listing.kind),
    t.intro({ name, age, programme, semester, degree }),
    t.listing({ kind: listing.kind, title, household: listing.household_size, date }),
    about,
    ...extras,
    hobbies.length ? t.hobbies(list(hobbies, lang)) : null,
    t.close(listing.kind),
    `${t.signoff}\n${name}`,
  ].filter((p): p is string => p != null)
  const text = parts.join('\n\n')
  return { text, gaps, tooLong: text.length > APPLICATION_MAX_CHARS }
}

interface Intro {
  name: string
  age: string
  programme: string
  semester: string
  degree: string
}
interface ListingPart {
  kind: ApplicationInput['listing']['kind']
  title: string
  household: number | null
  date: string
}
interface Template {
  greeting: (kind: ApplicationInput['listing']['kind']) => string
  intro: (v: Intro) => string
  listing: (v: ListingPart) => string
  hobbies: (list: string) => string
  close: (kind: ApplicationInput['listing']['kind']) => string
  signoff: string
}

/** "Zimmer" is neuter, "Wohnung" feminine: article and possessive follow the noun. */
const deThing = (kind: ListingPart['kind'], formal: boolean) =>
  kind === 'wg_room'
    ? { noun: 'Zimmer', the: 'das', your: formal ? 'Ihr' : 'euer' }
    : { noun: 'Wohnung', the: 'die', your: formal ? 'Ihre' : 'eure' }

const deListing =
  (formal: boolean) =>
  ({ kind, title, household, date }: ListingPart): string => {
    const th = deThing(kind, formal)
    const quoted = title ? ` „${title}“` : ''
    const wg = kind === 'wg_room' && household ? ` in ${formal ? 'Ihrer' : 'eurer'} ${household}er-WG` : ''
    const opener = formal
      ? `Ich interessiere mich für ${th.your} ${th.noun}${quoted}${wg}`
      : `Ich habe euer Angebot${quoted} gesehen und interessiere mich für ${th.the} ${th.noun}${wg}`
    return `${opener} – ich suche ab dem ${date} etwas Neues in Tübingen.`
  }

const de: Record<Tone, Template> = {
  casual: {
    greeting: () => 'Hey ihr,',
    intro: (v) => `ich bin ${v.name}, ${v.age}, und studiere ${v.programme} im ${v.semester}. Semester (${v.degree}).`,
    listing: deListing(false),
    hobbies: (l) => `In meiner Freizeit: ${l}.`,
    close: () => 'Hättet ihr Lust, euch mal kennenzulernen? Ich komme gern vorbei, wann es euch passt.',
    signoff: 'Liebe Grüße',
  },
  friendly: {
    greeting: (kind) => (kind === 'wg_room' ? 'Hallo zusammen,' : 'Hallo,'),
    intro: (v) => `mein Name ist ${v.name}, ich bin ${v.age} Jahre alt und studiere ${v.programme} im ${v.semester}. Semester (${v.degree}).`,
    listing: deListing(false),
    hobbies: (l) => `Zu meinen Hobbys gehören ${l}.`,
    close: (kind) => `Ich würde mich sehr freuen, ${kind === 'wg_room' ? 'euch und das Zimmer' : 'die Wohnung'} kennenzulernen. Wann würde euch eine Besichtigung passen?`,
    signoff: 'Viele Grüße',
  },
  formal: {
    greeting: () => 'Guten Tag,',
    intro: (v) => `mein Name ist ${v.name}, ich bin ${v.age} Jahre alt und studiere ${v.programme} im ${v.semester}. Fachsemester (${v.degree}) an der Universität Tübingen.`,
    listing: deListing(true),
    hobbies: (l) => `In meiner Freizeit beschäftige ich mich mit ${l}.`,
    close: (kind) => `Über die Möglichkeit, ${kind === 'wg_room' ? 'das Zimmer' : 'die Wohnung'} zu besichtigen, würde ich mich sehr freuen.`,
    signoff: 'Mit freundlichen Grüßen',
  },
}

const enListing =
  (formal: boolean) =>
  ({ kind, title, household, date }: ListingPart): string => {
    const noun = kind === 'wg_room' ? 'room' : 'flat'
    const quoted = title ? ` "${title}"` : ''
    const wg = kind === 'wg_room' && household ? ` in your ${household}-person flatshare` : ''
    const opener = formal ? `I am writing about your ${noun}${quoted}${wg}` : `I saw your ad${quoted} and I'm interested in the ${noun}${wg}`
    return `${opener} – I am looking for a new place in Tübingen from ${date}.`
  }

const en: Record<Tone, Template> = {
  casual: {
    greeting: () => 'Hey there,',
    intro: (v) => `I'm ${v.name}, ${v.age}, studying ${v.programme} in my ${ordinal(v.semester)} semester (${v.degree}).`,
    listing: enListing(false),
    hobbies: (l) => `In my free time: ${l}.`,
    close: () => 'Would you like to meet? Happy to come by whenever suits you.',
    signoff: 'Cheers',
  },
  friendly: {
    greeting: (kind) => (kind === 'wg_room' ? 'Hi all,' : 'Hello,'),
    intro: (v) => `My name is ${v.name}, I'm ${v.age} years old and I study ${v.programme} in my ${ordinal(v.semester)} semester (${v.degree}).`,
    listing: enListing(false),
    hobbies: (l) => `My hobbies include ${l}.`,
    close: (kind) => `I'd love to meet ${kind === 'wg_room' ? 'you and see the room' : 'you and see the flat'}. When would a viewing suit you?`,
    signoff: 'Best wishes',
  },
  formal: {
    greeting: (kind) => (kind === 'wg_room' ? 'Dear flatmates,' : 'Dear Sir or Madam,'),
    intro: (v) => `My name is ${v.name}, I am ${v.age} years old and I study ${v.programme} in my ${ordinal(v.semester)} semester (${v.degree}) at the University of Tübingen.`,
    listing: enListing(true),
    hobbies: (l) => `In my free time I enjoy ${l}.`,
    close: (kind) => `I would be grateful for the opportunity to view the ${kind === 'wg_room' ? 'room' : 'flat'}.`,
    signoff: 'Kind regards',
  },
}

/** "3" → "3rd"; a gap stays as it is. */
function ordinal(s: string): string {
  if (!/^\d+$/.test(s)) return s
  const n = Number(s)
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${suffix}`
}
