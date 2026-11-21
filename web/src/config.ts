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
