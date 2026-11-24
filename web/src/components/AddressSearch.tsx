import { useEffect, useId, useRef, useState } from 'react'

import { getApi } from '../api/client'
import type { AddressHit } from '../api/types'
import { useDebounced } from '../hooks'
import { useI18n } from '../i18n/i18n'
import { MAX_PLACES, SEARCH_DEBOUNCE_MS } from '../settings'
import { useStore } from '../state/store'
import { useToast } from './Toast'

type SearchState =
  | { kind: 'idle' }
  | { kind: 'short' }
  | { kind: 'loading' }
  | { kind: 'hits'; hits: AddressHit[] }
  | { kind: 'error' }

/**
 * Address search in the header: ARIA 1.2 combobox with a listbox of up to 10 hits. The typed text
 * goes to the API in a POST body (proposed, notes N17), never in a query string.
 */
export function AddressSearch({ onDone }: { onDone?: () => void }) {
  const { t } = useI18n()
  const { state, dispatch } = useStore()
  const toast = useToast()
  const id = useId()
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  /** answer for one query text; idle/short/loading are derived, not stored */
  const [answer, setAnswer] = useState<{ q: string; hits: AddressHit[] | null } | null>(null)
  const dq = useDebounced(q, SEARCH_DEBOUNCE_MS)
  const inputRef = useRef<HTMLInputElement>(null)
  const text = dq.trim()

  useEffect(() => {
    if (text.length < 3) return
    const ctrl = new AbortController()
    getApi()
      .then((api) => api.searchAddresses(text, ctrl.signal))
      .then((hits) => {
        setAnswer({ q: text, hits })
        setActive(hits.length ? 0 : -1)
      })
      .catch(() => {
        if (!ctrl.signal.aborted) setAnswer({ q: text, hits: null })
      })
    return () => ctrl.abort()
  }, [text])

  const res: SearchState = !q.trim()
    ? { kind: 'idle' }
    : q.trim().length < 3
      ? { kind: 'short' }
      : !answer || answer.q !== text || text !== q.trim()
        ? { kind: 'loading' }
        : answer.hits
          ? { kind: 'hits', hits: answer.hits }
          : { kind: 'error' }

  const pick = (hit: AddressHit) => {
    if (state.places.length >= MAX_PLACES) {
      toast(t('check.max'))
      return
    }
    dispatch({ type: 'addPlace', place: { point: hit.point, cellId: hit.cell_id, label: hit.label } })
    setQ('')
    setOpen(false)
    onDone?.()
  }

  const hits = res.kind === 'hits' ? res.hits : []
  const listId = `${id}-list`
  const statusText =
    res.kind === 'short'
      ? t('search.tooShort')
      : res.kind === 'loading'
        ? t('search.loading')
        : res.kind === 'error'
          ? t('error.serverNoResult')
          : res.kind === 'hits' && !hits.length
            ? t('search.noHit')
            : ''

  return (
    <div className="search">
      <label htmlFor={`${id}-input`} className="visually-hidden">
        {t('search.label')}
      </label>
      <input
        ref={inputRef}
        id={`${id}-input`}
        type="search"
        role="combobox"
        aria-expanded={open && hits.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 ? `${id}-opt-${active}` : undefined}
        autoComplete="off"
        placeholder={t('search.placeholder')}
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setOpen(true)
            setActive((a) => Math.min(hits.length - 1, a + 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setActive((a) => Math.max(0, a - 1))
          } else if (e.key === 'Enter' && open && hits[active]) {
            e.preventDefault()
            pick(hits[active])
          } else if (e.key === 'Escape') {
            setOpen(false)
            onDone?.()
          }
        }}
      />
      {open && (statusText || hits.length > 0) && (
        <div className="search-pop">
          {hits.length > 0 && (
            <ul id={listId} role="listbox" aria-label={t('search.label')} className="search-list">
              {hits.map((h, i) => (
                <li
                  key={h.label + i}
                  id={`${id}-opt-${i}`}
                  role="option"
                  aria-selected={i === active}
                  className="search-opt"
                  onMouseDown={(e) => {
                    e.preventDefault()
                    pick(h)
                  }}
                  onMouseEnter={() => setActive(i)}
                >
                  {h.label}
                </li>
              ))}
            </ul>
          )}
          {statusText && <p className="search-status">{statusText}</p>}
        </div>
      )}
      <span className="visually-hidden" role="status" aria-live="polite">
        {res.kind === 'hits' ? (hits.length ? t('search.hits', { n: hits.length }) : t('search.noHit')) : ''}
      </span>
    </div>
  )
}
