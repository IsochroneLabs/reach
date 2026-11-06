/// <reference types="vite/client" />

// Build-time settings from .env.development / .env.production (web/AGENTS.md).
interface ImportMetaEnv {
  readonly VITE_API_BASE: string
  readonly VITE_BASEMAP_STYLE: string
  readonly VITE_BASEMAP_ATTRIBUTION: string
  readonly VITE_DOCS_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
