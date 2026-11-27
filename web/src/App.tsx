import { useEffect, useRef, useState } from 'react'

import { BottomSheet, type SheetTab, type Snap } from './components/BottomSheet'
import { CheckResults } from './components/CheckResults'
import { FindResults } from './components/FindResults'
import { Header } from './components/Header'
import { MapArea } from './components/MapArea'
import { ProfilePanel, ProgrammeHint } from './components/ProfilePanel'
import { StatusBanner } from './components/StatusBanner'
import { ToastProvider, useToast } from './components/Toast'
import { FitProvider } from './remote/fit'
import { ListingsProvider, useListings } from './remote/listings'
import { RefsProvider, useRefs } from './remote/refs'
import { useBreakpoint } from './hooks'
import { I18nProvider, useI18n } from './i18n/i18n'
import { sanitize } from './state/profile'
import { StoreProvider, useStore } from './state/store'

/** Once the reference lists are in: drop unknown values from the loaded profile, tell the user. */
function useLoadChecks() {
  const refs = useRefs()
  const { state, dispatch } = useStore()
  const toast = useToast()
  const { t } = useI18n()
  const done = useRef(false)

  useEffect(() => {
    if (done.current || refs.kind !== 'ok') return
    done.current = true
    const { profile, dropped } = sanitize(state.profile, {
      types: refs.refs.types,
      programmes: refs.refs.programmes,
      modes: refs.refs.meta.modes,
    })
    if (dropped) dispatch({ type: 'profile', profile })
    if (dropped || state.badLink) toast(t('error.badLink'))
    else if (state.replacedProfile) {
      const previous = state.replacedProfile
      toast(t('profile.fromLink'), {
        label: t('profile.undo'),
        run: () => dispatch({ type: 'profile', profile: previous }),
      })
    }
    dispatch({ type: 'ackLoad' })
  }, [refs, state, dispatch, toast, t])
}

function Shell() {
  const bp = useBreakpoint()
  const { t } = useI18n()
  const { state } = useStore()
  const listings = useListings()
  const [drawer, setDrawer] = useState(false)
  const [tab, setTab] = useState<SheetTab>('results')
  const [snap, setSnap] = useState<Snap>('peek')
  useLoadChecks()

  const results = state.mode === 'find' ? <FindResults /> : <CheckResults />

  // Check on mobile: show the place card at half height when a place is added (state adjusted
  // during render, https://react.dev/learn/you-might-not-need-an-effect).
  const [seenPlaces, setSeenPlaces] = useState(state.places.length)
  if (seenPlaces !== state.places.length) {
    setSeenPlaces(state.places.length)
    if (bp === 'S' && state.places.length > seenPlaces) {
      setTab('results')
      if (snap === 'peek') setSnap('half')
    }
  }

  // phones: the WGs toggle opens the results sheet so the list is visible, not only the markers
  const [seenListings, setSeenListings] = useState(listings.enabled)
  if (seenListings !== listings.enabled) {
    setSeenListings(listings.enabled)
    if (bp === 'S' && listings.enabled) {
      setTab('results')
      if (snap === 'peek') setSnap('half')
    }
  }

  return (
    <div className={`app bp-${bp} mode-${state.mode}`}>
      <a className="skip-link" href="#results">
        {t(state.mode === 'find' ? 'skip.results' : 'skip.places')}
      </a>
      <Header onProfile={bp === 'M' ? () => setDrawer((d) => !d) : undefined} />
      <StatusBanner />
      <div className="layout">
        {bp === 'L' && (
          <aside className="col-profile" aria-label="profile">
            <ProfilePanel />
          </aside>
        )}
        {bp === 'M' && drawer && (
          <aside className="drawer" aria-label="profile">
            <ProfilePanel onClose={() => setDrawer(false)} />
          </aside>
        )}
        <main className="col-map">
          <MapArea />
        </main>
        {bp !== 'S' && (
          <section id="results" className={`col-results${state.mode === 'check' && state.places.length > 1 ? ' wide' : ''}`}>
            {results}
          </section>
        )}
      </div>
      {bp === 'S' && (
        <BottomSheet
          tab={tab}
          onTab={setTab}
          snap={snap}
          onSnap={setSnap}
          hint={tab === 'results' ? <ProgrammeHint compact onOpen={() => { setTab('profile'); setSnap('full') }} /> : null}
          profileDot={!state.profile.programme}
          results={<div id="results">{results}</div>}
          profile={<ProfilePanel />}
        />
      )}
    </div>
  )
}

export default function App() {
  return (
    <I18nProvider>
      <ToastProvider>
        <RefsProvider>
          <StoreProvider>
            <FitProvider>
              <ListingsProvider>
                <Shell />
              </ListingsProvider>
            </FitProvider>
          </StoreProvider>
        </RefsProvider>
      </ToastProvider>
    </I18nProvider>
  )
}
