# web/AGENTS.md

Rules for agents working in `web/` (React + TypeScript + Vite + MapLibre GL JS). The root
`AGENTS.md` applies; this file wins where it is more specific.

- **Status:** P6 — class map, profile/category selector, legend, pin-drop inspector, district
  statistics, data & validation page; recommendations layer prepared (hidden while
  `/api/recommendations` reports `available: false`).
- **Toolchain:** Node 24 LTS (`.nvmrc`, `engines`); npm with `package-lock.json`, exact versions
  (`--save-exact`). Not part of the uv workspace. New or upgraded packages: ask first.
- **Layout:** `src/api.ts` (all requests, `ApiError`, user messages per status), `src/types.ts`
  (response shapes of `docs/data_contract.md`), `src/palette.ts` (class colours and legend
  rules), `src/route.ts` (view and selection in the URL hash), `src/labels.ts`,
  `src/attribution.ts`, `src/components/` (`MapView`, `Controls`, `Inspector`, `DistrictPanel`,
  `DataPage`). One stylesheet, `src/styles.css`.
- **Read the API, do not re-derive.** Categories, names, `k`, profiles, transit class bounds and
  run data come from `/api/meta`; classes, deficits and district shares from the API. Only
  display aggregates (e.g. residents per class in the legend) are summed here. No thresholds,
  category names, API or basemap URLs in code; fixed UI text (attribution links, the transit
  label, the known limitations on the data page with their doc links) is fine.
- **Settings** are build-time Vite variables in `.env.development` and `.env.production`
  (committed, no secrets; keep both in sync): `VITE_API_BASE`, `VITE_BASEMAP_STYLE`,
  `VITE_BASEMAP_ATTRIBUTION`, `VITE_DOCS_URL`; `VITE_DEV_API_PROXY` for `npm run dev` only. Type
  new ones in `src/vite-env.d.ts`.
- **Colours** live only in `src/palette.ts`. Classes are ordered and their colours get
  monotonically lighter (CIELAB L*); a change must be re-checked with a simulated
  deuteranopia/protanopia/tritanopia (min. ΔE stated in the file) and a screenshot.
- **Caching:** read endpoints carry an ETag per run; rely on the browser cache (`fetch` default)
  instead of an extra in-memory cache. Live calls (`/api/inspect`) are aborted when a new pin
  is dropped; the previous answer stays (dimmed) and the spinner shows only after 300 ms, so
  fast answers do not flicker. The map stays mounted on the data page (position kept).
- **Attribution** (OSM, Destatis, NVBW, basemap) stays visible on the map (`compact: false`)
  and on the data page.
- **MapLibre 6:** named imports only; the worker is emitted via `?url` and `setWorkerUrl`.
  `window.__reachMap` exists on the dev server only.
- **Checks:** `npm ci && npm run lint && npm run build`. Browser smoke test: `npx playwright
  test` (production preview, API replayed from `tests/fixtures/`, basemap blocked; CI job
  `web`), `E2E_LIVE=1 npx playwright test` against `make up` on `http://localhost:8080`.
  Fixtures are recorded from the local API, each < 1 MB (cells thinned).
- **Serving:** `infra/web.Dockerfile` builds `dist/` with Node and copies it into the Caddy
  image with `infra/Caddyfile`; `make up` rebuilds it. Hot reload: `npm run dev`
  (http://127.0.0.1:5173, proxies `/api` to the stack).
