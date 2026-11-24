import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import type { Label, Lang } from '../api/types'
import { storage } from '../state/storage'
import { de } from './de'
import { en, type TextKey } from './en'

const DICTS: Record<Lang, Record<TextKey, string>> = { en, de }
const LANG_KEY = 'reach.v1.lang'

export type Vars = Record<string, string | number>

export interface I18n {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: TextKey, vars?: Vars) => string
  /** API label in the current language. */
  label: (l: Label) => string
  num: (n: number, digits?: number) => string
  /** "12 min" / "1 h 05 min" */
  duration: (min: number) => string
  /** "Tue, arrive by 8:10" */
  date: (iso: string) => string
}

const Ctx = createContext<I18n | null>(null)

function fill(s: string, vars?: Vars): string {
  return vars ? s.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : s
}

export function I18nProvider({ children }: { children: ReactNode }) {
  // English first (product v1.1); the choice is remembered in this browser only.
  const [lang, setLangState] = useState<Lang>(() => (storage.get(LANG_KEY) === 'de' ? 'de' : 'en'))

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    storage.set(LANG_KEY, l)
  }, [])

  const value = useMemo<I18n>(() => {
    const locale = lang === 'de' ? 'de-DE' : 'en-GB'
    const nf = new Intl.NumberFormat(locale)
    const t = (key: TextKey, vars?: Vars) => fill(DICTS[lang][key] ?? en[key], vars)
    return {
      lang,
      setLang,
      t,
      label: (l) => l[lang] ?? l.en,
      num: (n, digits = 0) =>
        new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(n),
      duration: (min) => {
        const m = Math.round(min)
        if (m < 60) return t('time.min', { min: nf.format(m) })
        return t('time.hmin', { h: Math.floor(m / 60), min: String(m % 60).padStart(2, '0') })
      },
      date: (iso) =>
        new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', year: 'numeric' }).format(
          new Date(`${iso}T12:00:00`),
        ),
    }
  }, [lang, setLang])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useI18n(): I18n {
  const v = useContext(Ctx)
  if (!v) throw new Error('useI18n outside I18nProvider')
  return v
}
