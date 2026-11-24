import { useState } from 'react'

import { USE_FIXTURES } from '../config'
import { useI18n } from '../i18n/i18n'
import { useStore, type AppMode } from '../state/store'
import { AboutDialog } from './AboutDialog'
import { AddressSearch } from './AddressSearch'

export function Header({ onProfile }: { onProfile?: () => void }) {
  const { t, lang, setLang } = useI18n()
  const { state, dispatch } = useStore()
  const [about, setAbout] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const modes: AppMode[] = ['find', 'check']

  return (
    <header className="app-header">
      <h1 className="logo">
        <span aria-hidden="true" className="logo-mark" />
        {t('app.name')}
      </h1>
      <nav className="mode-switch" aria-label={t('mode.switch.label')}>
        {modes.map((m) => (
          <button
            key={m}
            type="button"
            className="mode-tab"
            aria-pressed={state.mode === m}
            onClick={() => dispatch({ type: 'mode', mode: m })}
          >
            {t(m === 'find' ? 'mode.find' : 'mode.check')}
          </button>
        ))}
      </nav>
      <div className={`header-search${searchOpen ? ' open' : ''}`}>
        <AddressSearch onDone={() => setSearchOpen(false)} />
      </div>
      <div className="header-tools">
        <button
          type="button"
          className="btn-icon search-toggle"
          aria-label={t('search.open')}
          aria-expanded={searchOpen}
          onClick={() => setSearchOpen((o) => !o)}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="M15.5 15.5 21 21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
        {onProfile && (
          <button type="button" className="btn btn-quiet profile-toggle" onClick={onProfile}>
            {t('profile.open')}
          </button>
        )}
        {USE_FIXTURES && (
          <button type="button" className="badge badge-sample" onClick={() => setAbout(true)} data-testid="sample-badge">
            {t('data.demo')}
          </button>
        )}
        <button
          type="button"
          className="btn btn-quiet"
          lang={lang === 'en' ? 'de' : 'en'}
          aria-label={t('lang.switch.label')}
          onClick={() => setLang(lang === 'en' ? 'de' : 'en')}
        >
          {lang === 'en' ? 'DE' : 'EN'}
        </button>
        <button type="button" className="btn-icon" aria-label={t('about.open')} onClick={() => setAbout(true)}>
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="M12 11v6M12 7.5v.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <AboutDialog open={about} onClose={() => setAbout(false)} />
    </header>
  )
}
