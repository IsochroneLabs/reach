/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BUILD_SHA?: string
  readonly VITE_API_BASE?: string
  readonly VITE_API_FIXTURES?: string
  readonly VITE_BASEMAP_STYLE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
