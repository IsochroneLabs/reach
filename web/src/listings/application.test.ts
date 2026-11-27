// Unit tests for the application text (F4.8, `npm run test:unit`). Snapshots per language and
// tone: a change to a template shows up here and is reviewed as text.
import assert from 'node:assert/strict'
import { beforeEach, test } from 'node:test'

import { draftApplication, type ApplicationInput, type Lang, type Tone } from './application.ts'
import { clearLines, emptyLines, type KeyValueStore, loadLines, PERSONAL_KEY, sanitizeLines, saveLines } from './personal.ts'

const input = (lang: Lang, tone: Tone): ApplicationInput => ({
  lang,
  tone,
  student: {
    programme: lang === 'de' ? 'Informatik' : 'Computer Science',
    degree: 'bachelor',
    semester: 3,
    hobbies: lang === 'de' ? ['Tennis', 'Chor'] : ['tennis', 'choir'],
  },
  personal: { name: 'Alex', age: '21', about: lang === 'de' ? 'Ich bin ruhig und koche gern.' : 'I am quiet and like cooking.', extra1: '', extra2: '' },
  listing: { kind: 'wg_room', title: 'Helles Zimmer in Wanne', household_size: 3, available_from: '2026-12-01' },
})

const SNAPSHOTS: Record<string, string> = {
  'de.casual': "Hey ihr,\n\nich bin Alex, 21, und studiere Informatik im 3. Semester (Bachelor).\n\nIch habe euer Angebot „Helles Zimmer in Wanne“ gesehen und interessiere mich für das Zimmer in eurer 3er-WG – ich suche ab dem 1. Dezember 2026 etwas Neues in Tübingen.\n\nIch bin ruhig und koche gern.\n\nIn meiner Freizeit: Tennis und Chor.\n\nHättet ihr Lust, euch mal kennenzulernen? Ich komme gern vorbei, wann es euch passt.\n\nLiebe Grüße\nAlex",
  'de.friendly': "Hallo zusammen,\n\nmein Name ist Alex, ich bin 21 Jahre alt und studiere Informatik im 3. Semester (Bachelor).\n\nIch habe euer Angebot „Helles Zimmer in Wanne“ gesehen und interessiere mich für das Zimmer in eurer 3er-WG – ich suche ab dem 1. Dezember 2026 etwas Neues in Tübingen.\n\nIch bin ruhig und koche gern.\n\nZu meinen Hobbys gehören Tennis und Chor.\n\nIch würde mich sehr freuen, euch und das Zimmer kennenzulernen. Wann würde euch eine Besichtigung passen?\n\nViele Grüße\nAlex",
  'de.formal': "Guten Tag,\n\nmein Name ist Alex, ich bin 21 Jahre alt und studiere Informatik im 3. Fachsemester (Bachelor) an der Universität Tübingen.\n\nIch interessiere mich für Ihr Zimmer „Helles Zimmer in Wanne“ in Ihrer 3er-WG – ich suche ab dem 1. Dezember 2026 etwas Neues in Tübingen.\n\nIch bin ruhig und koche gern.\n\nIn meiner Freizeit beschäftige ich mich mit Tennis und Chor.\n\nÜber die Möglichkeit, das Zimmer zu besichtigen, würde ich mich sehr freuen.\n\nMit freundlichen Grüßen\nAlex",
  'en.casual': "Hey there,\n\nI'm Alex, 21, studying Computer Science in my 3rd semester (Bachelor).\n\nI saw your ad \"Helles Zimmer in Wanne\" and I'm interested in the room in your 3-person flatshare – I am looking for a new place in Tübingen from 1 December 2026.\n\nI am quiet and like cooking.\n\nIn my free time: tennis and choir.\n\nWould you like to meet? Happy to come by whenever suits you.\n\nCheers\nAlex",
  'en.friendly': "Hi all,\n\nMy name is Alex, I'm 21 years old and I study Computer Science in my 3rd semester (Bachelor).\n\nI saw your ad \"Helles Zimmer in Wanne\" and I'm interested in the room in your 3-person flatshare – I am looking for a new place in Tübingen from 1 December 2026.\n\nI am quiet and like cooking.\n\nMy hobbies include tennis and choir.\n\nI'd love to meet you and see the room. When would a viewing suit you?\n\nBest wishes\nAlex",
  'en.formal': "Dear flatmates,\n\nMy name is Alex, I am 21 years old and I study Computer Science in my 3rd semester (Bachelor) at the University of Tübingen.\n\nI am writing about your room \"Helles Zimmer in Wanne\" in your 3-person flatshare – I am looking for a new place in Tübingen from 1 December 2026.\n\nI am quiet and like cooking.\n\nIn my free time I enjoy tennis and choir.\n\nI would be grateful for the opportunity to view the room.\n\nKind regards\nAlex",
}

for (const lang of ['de', 'en'] as const) {
  for (const tone of ['casual', 'friendly', 'formal'] as const) {
    test(`snapshot ${lang} ${tone}`, () => {
      const d = draftApplication(input(lang, tone))
      assert.equal(d.text, SNAPSHOTS[`${lang}.${tone}`])
      assert.deepEqual(d.gaps, [])
      assert.equal(d.tooLong, false)
    })
  }
}

test('missing values stay visible gaps; nothing is invented', () => {
  const d = draftApplication({
    lang: 'de',
    tone: 'friendly',
    student: { programme: null, degree: null, semester: null, hobbies: [] },
    personal: emptyLines(),
    listing: { kind: 'flat', title: null, household_size: null, available_from: null },
  })
  assert.deepEqual(d.gaps, ['[Name]', '[Alter]', '[Studiengang]', '[Semester]', '[Bachelor/Master]', '[Einzugsdatum]', '[ein, zwei Sätze über dich]'])
  assert.match(d.text, /^Hallo,\n/)
  assert.match(d.text, /für die Wohnung –/)
  assert.doesNotMatch(d.text, /WG|Hobby|Freizeit|„/)
})

test('only the hobbies passed in are named, at most three', () => {
  const base = input('en', 'friendly')
  const d = draftApplication({ ...base, student: { ...base.student, hobbies: ['tennis', ' ', 'choir', 'chess', 'climbing'] } })
  assert.match(d.text, /My hobbies include tennis, choir and chess\./)
  assert.doesNotMatch(d.text, /climbing/)
  const none = draftApplication({ ...base, student: { ...base.student, hobbies: [] } })
  assert.doesNotMatch(none.text, /hobbies/)
})

test('studio and flat use the feminine noun in German and no flatshare', () => {
  const base = input('de', 'formal')
  const d = draftApplication({ ...base, listing: { ...base.listing, kind: 'studio', household_size: 2 } })
  assert.match(d.text, /Ich interessiere mich für Ihre Wohnung „Helles Zimmer in Wanne“ – /)
  assert.match(d.text, /die Wohnung zu besichtigen/)
  assert.doesNotMatch(d.text, /WG/)
})

test('extra lines follow the about line; long drafts are flagged', () => {
  const base = input('de', 'casual')
  const d = draftApplication({ ...base, personal: { ...base.personal, extra1: 'Ich habe ein Fahrrad.', extra2: '  ' } })
  assert.match(d.text, /koche gern\.\n\nIch habe ein Fahrrad\.\n\nIn meiner Freizeit/)
  const long = draftApplication({ ...base, personal: { ...base.personal, about: 'x'.repeat(1300) } })
  assert.equal(long.tooLong, true)
})

test('an invalid date is a gap, ordinals in English', () => {
  const base = input('en', 'casual')
  const d = draftApplication({ ...base, student: { ...base.student, semester: 12 }, listing: { ...base.listing, available_from: '1.12.2026' } })
  assert.deepEqual(d.gaps, ['[move-in date]'])
  assert.match(d.text, /12th semester/)
})

// --- personal lines in localStorage -----------------------------------------------------------

const map = new Map<string, string>()
const store: KeyValueStore = {
  get: (k) => map.get(k) ?? null,
  set: (k, v) => void map.set(k, v),
  remove: (k) => void map.delete(k),
}
beforeEach(() => map.clear())

test('personal lines are saved, loaded and deleted in localStorage only', () => {
  saveLines(store, { ...emptyLines(), name: 'Alex', age: '21' })
  assert.deepEqual(JSON.parse(map.get(PERSONAL_KEY) ?? ''), { ...emptyLines(), name: 'Alex', age: '21' })
  assert.equal(loadLines(store).name, 'Alex')
  clearLines(store)
  assert.equal(map.has(PERSONAL_KEY), false)
  assert.deepEqual(loadLines(store), emptyLines())
})

test('empty lines remove the entry; bad stored values are ignored', () => {
  saveLines(store, { ...emptyLines(), name: 'Alex' })
  saveLines(store, emptyLines())
  assert.equal(map.has(PERSONAL_KEY), false)
  map.set(PERSONAL_KEY, '{not json')
  assert.deepEqual(loadLines(store), emptyLines())
  assert.deepEqual(sanitizeLines({ name: 7, age: '123456', about: 'ok', phone: '0170' }), { ...emptyLines(), age: '123', about: 'ok' })
})
