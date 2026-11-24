/** Build-time configuration (web/AGENTS.md). */

/** Commit SHA of this build; "dev" for local builds. */
export const BUILD_SHA: string = import.meta.env.VITE_BUILD_SHA || 'dev'

/**
 * Base URL of the API without a trailing slash. Empty = no backend deployed yet (until S1.5).
 * `npm run dev` defaults to "/api", which Vite proxies to the local API.
 */
export const API_BASE: string = (
  import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? '/api' : '')
).replace(/\/$/, '')

/**
 * Fixture mode: the app answers its data requests in the browser from hand-made sample data
 * (src/api/fixtures). On with VITE_API_FIXTURES=1 or when no API base is set. The UI then shows
 * "Sample data". The health check still goes to API_BASE when one is set.
 */
export const USE_FIXTURES: boolean = import.meta.env.VITE_API_FIXTURES === '1' || !API_BASE

/**
 * Optional basemap style URL (D5). Empty = plain background without a basemap. Must point to our
 * own origin (no third-party tile hosts, A6).
 */
export const BASEMAP_STYLE: string = import.meta.env.VITE_BASEMAP_STYLE ?? ''
