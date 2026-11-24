# web/AGENTS.md

Folder rules for the student web app. The root `AGENTS.md` applies; this file adds what is
specific to `web/`.

**Status (S0.5):** placeholder page (name, build SHA, API health) with Playwright smoke tests,
deployed to Cloudflare by the workflows. The app itself (map with profile panel, modes Find and Check;
MapLibre GL JS) starts in Phase 2 with its own step plans.

## Layout

| Path | Content |
|---|---|
| `src/config.ts` | Build-time config: `BUILD_SHA`, `API_BASE` |
| `src/health.ts` | `GET /api/health` client |
| `src/App.tsx`, `src/main.tsx`, `src/index.css` | Placeholder page |
| `tests/` | Playwright tests (`smoke.spec.ts`) |
| `playwright.config.ts` | Local runs build + `vite preview`; `BASE_URL` runs the same tests against a deployed site |
| `wrangler.jsonc` | Cloudflare Worker `reach` with static assets from `dist/` (docs/deployment.md) |
| `.nvmrc` | Node major version for CI and local development |

## Rules

- **Static build only.** No server-side code, no Worker script, no Cloudflare bindings. Data comes
  from the API; nothing is fetched from public data APIs (root rule 8).
- **Build-time config** comes from `VITE_*` variables, never hard-coded URLs:
  `VITE_BUILD_SHA` (set by CI to the commit SHA; `dev` locally; also in
  `<meta name="build-sha">`, which the deploy smoke test checks) and `VITE_API_BASE` (public API
  base URL without trailing slash; empty = no backend yet; `npm run dev` defaults to `/api`, which
  Vite proxies to `127.0.0.1:${API_PORT:-8000}`). New variables go into `src/config.ts`,
  `src/vite-env.d.ts`, this list and `.env.example`.
- **Privacy (root rule 9):** the student profile lives in the URL and `localStorage` only; no
  cookies, tracking, analytics or third-party scripts and fonts.
- **Every number on screen is explainable** (docs/product.md): show data date, trip window, mode
  and source next to it; label missing or uncertain values, never hide them (the placeholder shows
  "unreachable" when the API fails).
- **Mobile first, German and English,** accessible contrast; Playwright runs a desktop and a mobile
  project.
- **Deploys only through the workflows** (`ci.yml` previews, `deploy.yml` production). Never run
  `wrangler deploy` or `wrangler preview` by hand.

## Tests

- Playwright tests never call a real API: `page.route` answers `/api/*` with fixtures. Keep
  fixtures next to the tests, in the shapes of `docs/data_contract.md`.
- Tests that only make sense locally skip when `BASE_URL` is set; everything else also runs as the
  deploy smoke test against the live site (`EXPECTED_SHA` = deployed commit).

## Commands (from `web/`)

| Task | Command |
|---|---|
| Install | `npm ci` |
| Dev server | `npm run dev` (with the API from `make up` for live data) |
| Lint, type check + build | `npm run lint && npm run build` |
| Smoke tests | `npx playwright install chromium` once, then `npm run test:e2e` |

Versions are pinned in `package.json` and `package-lock.json`; adding or upgrading a package needs
a yes (root `AGENTS.md`).
