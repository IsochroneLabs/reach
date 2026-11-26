# Implementation plan — reach

> **Version:** v1.0 draft (21 Nov 2026). This is the single place for progress. Update the status
> block at the end of every step. A new session continues with: *"Continue with the next open step
> in docs/implementation_plan.md."*

reach helps students who are new to Tübingen decide where to live, by showing how long their own
everyday trips take from each part of the city on foot, by bike (with hills) and by bus, and
explaining the differences in plain language.

## Status

| | |
|---|---|
| **Done** | S0.1 (restatement, port table, answers of 21 Nov 2026) · S0.2 (this plan, confirmed 21 Nov 2026 with three changes) · S0.3 (sources of truth, PR #78 merged 21 Nov 2026) · S0.4 foundation (PR #80, merged 24 Nov 2026) · S0.5 walking skeleton code (PR #81, merged 24 Nov 2026; preview and dispatch test still open) |
| **In progress** | Product v1.1 (`docs/rico-two-modes`, draft PR #87) · S2.1 screen plan confirmed 24 Nov 2026 (PR #89) · Phase 2 web app on fixtures, stacked on #89: S2.2 app shell (`feature/rico-app-shell`, PR #90) → S2.3 profile panel (`feature/rico-profile-panel`, PR #91) → S2.4 result map (`feature/rico-result-map`, PR #92) → S2.5 place check (`feature/rico-place-check`) → S2.6 compare (`feature/rico-compare`); next: S2.7 quality (axe, keyboard), CI step for unit tests, basemap (N18); decisions of 24 Nov: D5 proposal N18, API gaps N17, default campus mix in `config/campus.yaml` |
| **Next** | set required checks on `dev` → preview URL from a `dev` push + `workflow_dispatch` of `deploy.yml` with target preview → S0.6 release PR v0.1.0 on instruction · bring the docs stack `docs/juju-t1-decision` … `docs/juju-fit-formula` (PRs #83–#86, merged only into each other) into `dev` · align its methodology and API proposal with product v1.1 (notes N16) |
| **Extensions** | [`docs/extension_plan.md`](extension_plan.md), phases F0–F5 (programmes from Alma, favourite supermarkets and sport/hobby categories, daily WG-Gesucht listings with application text, design *Atelier*). QF1–QF6 decided by Juju 26 Nov 2026 and recorded as architecture O22–O27 (v1.3-draft) and methodology v1.2-draft on `docs/juju-extension-plan`; `product.md` v1.2 and AGENTS.md rule 6 updated; open: WG-Gesucht permission (N20), Alma reachability (N21); next: F1.1, F2.1, F3.1 |
| **Blocked** | S0.5 preview check and S0.6: Cloudflare account, API token and the GitHub environments `preview`/`production` (a human sets them up, `docs/deployment.md`) |
| **Decided** | T1 → O17 OpenTripPlanner (PR #82, in `dev`); D1–D4 as O18–O21, fit formula proposal and API shapes on the Juju docs stack, **not yet in `dev`** |
| **Open decisions** | D5 basemap (recommendation: self-hosted PMTiles, `docs/app_screens.md` §5.1) · fit formula (proposal on the stack) · default campus mix without a programme (recommendation: Tal + Morgenstelle equal, §7) · Zensus rent: keep as reference or drop (notes N16) · API gaps for the app: data date, populated flag per cell, address search via POST (`docs/app_screens.md` §9) |
| **PRs** | [#78](https://github.com/IsochroneLabs/reach/pull/78) sources of truth (merged) · [#79](https://github.com/IsochroneLabs/reach/pull/79) T1 spike report (closed, not merged) · [#80](https://github.com/IsochroneLabs/reach/pull/80) foundation (merged) · [#81](https://github.com/IsochroneLabs/reach/pull/81) walking skeleton (merged) · [#82](https://github.com/IsochroneLabs/reach/pull/82) T1 as O17 (merged) · #83–#86 docs stack (merged into each other, not into `dev`) |
| **Deviations** | S0.4 and S0.5 were built on `feature/juju-phase0` and `feature/juju-delivery-skeleton` instead of the `rico-…` branches named below (at Juju's request; Rico to confirm) |
| **Risks now** | naldo GTFS feed ends 12 Dec 2026 (notes N14): v0.2.0 on 14 Dec needs a newer feed |
| **Releases** | – (main still holds the old project of 31 Oct 2026) |

## How to use this plan

- Steps are numbered `S<phase>.<n>`. Each step lists branch, files, tables/workflows, checks and
  a done criterion. Order inside a phase: plan → yes from your human → small commits on the
  branch → checks → draft PR into `dev` → report → stop.
- When this plan is confirmed, it counts as the AGENTS.md confirmation for the folders, files,
  `compose*.yaml`, `infra/`, workflows, data-contract tables and structure it **names
  explicitly**. Still needing their own "yes": every dependency, existing config values,
  deviations from this plan, every change to `docs/architecture.md` / `docs/methodology.md`, the
  fit formula, and T1/D1–D5.
- Report at the end of each step: what changed, checks with results, PR link, open points. At the
  end of each phase also: branches, commits, workflow runs, preview/deploy URLs, runtime/memory,
  doc changes, on track yes/no.
- Never: merge, mark ready, tag, release or delete branches without an explicit instruction; push
  to `dev`/`main`; touch `archive/2026-11-21-planner`; create, read or print secrets.

## Milestones and releases

| Phase | Target | Release (PR `dev` → `main`, 2 approvals, merged by a human) |
|---|---|---|
| 0 Plan and foundation | 30 Nov 2026 | **v0.1.0** walking skeleton: placeholder page through `main` → `deploy.yml` → Cloudflare; backend job skipped with a warning. First real test of the deploy chain. |
| 1 Backend | 14 Dec 2026 | **v0.2.0** real production with backend: pipeline + API on the server of D1, deployed by `deploy.yml` with smoke test and rollback |
| 2 Student web app | 9 Jan 2027 | **v0.3.0** *Find* and *Check* in the browser |
| 3 Hardening | 16 Jan 2027 | **v0.4.0** scheduled refresh, measured memory, backups, rollback drill, validation report |
| Buffer | 22 Jan 2027 | **v1.0.0** submission |

Versions follow SemVer (`CONTRIBUTING.md`). Every release PR moves the `Unreleased` entries of
`CHANGELOG.md` into a version section and bumps `version` in the `pyproject.toml` files and
`web/package.json`. Tags and GitHub Releases only on explicit instruction.

## Assumptions recorded on 21 Nov 2026 (S0.1)

| # | Assumption / answer |
|---|---|
| A1 | Origins = populated Zensus 100 m cells **plus** cells containing an OSM residential address (for *Check*); rankings use populated cells only. |
| A2 | Computation per 100 m cell; ranking and reasons per district / Teilort (OSM admin levels 9 and 11); the map colours cells; *Check* shows the user's own cell. |
| A3 | Trip windows: weekday + reference date per window; GTFS times > 24:00 handled correctly; night window on Fri/Sat nights. |
| A4 | Refresh runs **sequentially** (routing engines and pipeline not at peak at the same time); assumption for T1 and the 8 GB memory budget. |
| A5 | Role `supervisor_read` kept, marked **[VERIFY]** (Rico checks whether it is a course requirement). |
| A6 | D5 basemap decided in Phase 2; criterion: no user data to third parties. |
| A7 | `issue-sync.yml` / `github_sync.py` are not ported; progress lives in this file. |
| A8 | Archive `requirements.txt` is not ported (uv only; `uv export` can regenerate it on request). Archive `.dockerignore` is ported in S0.4 and adapted (no web entries; pipeline image added). |

## Phase 0 — Plan and foundation (target 30 Nov 2026)

### S0.1 Restatement and port table — done (21 Nov 2026)

Answers: A1–A8 above. Port table: see S0.4.

### S0.2 Implementation plan — done (21 Nov 2026)

- **Branch:** `docs/rico-foundation` (shared with S0.3; one draft PR after S0.3).
- **Files:** `docs/implementation_plan.md`.
- **Done when:** your human confirmed the plan; committed as `docs(repo): add implementation plan for the rebuild`.

### S0.3 Sources of truth — done (21 Nov 2026, PR #78)

- **Branch:** `docs/rico-foundation`.
- **Before writing:** read the archive's `docs/notes.md`, `docs/data_contract.md`,
  `docs/osm_tagging.md`, `docs/validation_report.md` and `config/config.yaml` in full; check
  whether Zensus 2022 publishes average net rent on the 100 m grid (source, licence, suppression).
- **Files, in this order, one commit each, diff shown before each commit:**
  1. `docs/glossary.md` — new terms (mode, routing profile, student profile, persona, destination,
     destination type, fit, trip window, area, origin kinds, …); kept old terms (cell, run, stage,
     manifest, `current`, provenance, test clip, …); old terms removed (15-minute city, class,
     deficit, lack/sufficient, recommender, housing potential, …).
  2. `AGENTS.md` — project line, status, terms, sources of truth, commands (marked *planned*
     until they exist), stack, architecture rules (incl. "transit engine: decision pending"),
     delivery rules, where things are, branch/release/commit rules, Never list.
  3. `README.md` — title + summary, status with CI/deploy badges (*planned* until the workflows
     exist), what it does, architecture picture, layout, getting started, data sources, docs,
     team, milestones.
  4. `docs/product.md` — user, their questions, U1–U3, non-goals, cut order, onboarding draft.
  5. `docs/architecture.md` v1.0-draft — components, data flow, CRS, spatial model (A1, A2),
     routing profiles, trip windows (A3), pipeline stages, DB schemas, API, frontend, delivery
     pipeline, memory budget (A4); decisions: carried-over O-numbers (renumbered, with origin),
     **T1, D1–D5 [OPEN]**; change log.
  6. `docs/methodology.md` v1.0-draft — origins and destinations, modes and trip windows, travel
     time definition per mode (incl. transit legs), **fit [OPEN]** with formula proposal and
     examples, weekly travel time, explanations, rent (if a legal source exists), relation to
     classic accessibility measures; validation **V1–V8** (below); change log.
  7. `docs/deployment.md` — environments, delivery flow, workflows, every secret (name, purpose,
     minimal scope, exact creation steps), required status checks, runbook skeleton.
  8. `docs/data_contract.md` — roles (`supervisor_read` [VERIFY]), `meta`, manifest, file layout;
     result tables marked *planned (S1.4)*.
  9. `docs/notes.md` — carried-over findings with origin (Valhalla memory per worker, slopes in
     all costings, cost vs. time routing, `costmatrix` only, block vs. one-source matrix) and new
     open points.
  10. `docs/osm_tagging.md` — how tags are read, access rule, student destination types and hobby
     categories with tags (draft, completeness checked in S1.6).
  11. `CHANGELOG.md`, `.env.example`, `config/config.yaml`, `config/campus.yaml`,
     `config/personas.yaml` (drafts with comments; values that need evidence marked).
- **Checks:** every link and path exists or is marked *planned*; terms match the glossary;
  `architecture.md`/`methodology.md`/`AGENTS.md`/`README.md` use the same one-line definition.
- **Done when:** all files committed, draft PR `docs(repo): sources of truth for the student rebuild` into `dev`.

### S0.4 Port the foundation — target 27 Nov · ready to merge (PR #80, approved 23 Nov 2026)

- **Branch:** `refactor/rico-port-foundation`. Every commit message names its archive source path
  (`git checkout archive/2026-11-21-planner -- <path>`, then adapt). After every commit:
  `uv run ruff check . && uv run ruff format --check . && uv run pytest` green.
- **Commits (one per area):**

| # | Area | Archive source → target | How |
|---|---|---|---|
| 1 | uv workspace + tooling | `pyproject.toml`, `.python-version`, `pipeline/pyproject.toml`, `api/pyproject.toml` | descriptions; drop dev deps `pulp`, `highspy`, `matplotlib` (experiments only); `uv lock` fresh (not copied) |
| 2 | Pipeline core | `config.py`, `context.py`, `errors.py`, `notify.py`, `manifest.py`, `metrics.py`, `cli.py`, `db.py` + tests | config models for kept sections only; stage list reduced to ported stages |
| 3 | Acquire + inputs | `stages/acquire.py`, `osm.py`, `zensus.py`, `boundary.py`, `gtfs.py`, `transit.py` + tests, `tests/fixtures/tiny.osm` | `gtfs.py`: reference weekday → reference date per trip window (A3) is done in S1.6, ported as is here |
| 4 | Validate + tiles + Valhalla | `stages/validate.py`, `stages/tiles.py`, `valhalla/client.py`, `config/valhalla.json` + tests | validate keeps population, coverage and GTFS checks; facility-subtype checks dropped |
| 5 | Publish + cleanup + DB | `stages/publish.py`, `stages/cleanup.py`, `infra/db/roles.sql`, `infra/db/migrations/0001_meta.sql` + `db` tests | publish mechanism (`run_<id>`, atomic `current` switch) kept; old result tables removed; `run_schema.sql` rewritten in S1.9 |
| 6 | API skeleton | `api/src/reach_api/{__init__,main,settings,deps,db,cache,ratelimit,valhalla}.py` + `test_health` | health only (+ build SHA), error handlers, CORS allowlist from config; old read/live routes and queries dropped |
| 7 | Compose, Makefile, images | `compose.yaml`, `Makefile`, `infra/api.Dockerfile`, `.dockerignore`, `config/test_clip.yaml`; new `infra/pipeline.Dockerfile` | services db, valhalla, valhalla-build, api, pipeline (no Caddy locally); Makefile without slides/experiments/old stages |
| 8 | Folder rules + contributing | `pipeline/AGENTS.md`, `api/AGENTS.md`, `CONTRIBUTING.md` | rewritten for the new project; dev 0 approvals (a human merges after own review), main 2 approvals |

- **Not ported:** `count`, `score`, `recommend`, `housing`, `scoring.py`, `results.py`,
  `landuse.py`, `validate_results.py`, `experiments/`, API `routes/`, `web/`, `slides/`,
  `issue-sync.yml`, `github_sync.py`, `requirements.txt`, `infra/web.Dockerfile`; `infra/Caddyfile`
  waits for D2. Ideas carried over: block batching + prefilter + `costmatrix` (→ S1.8), matrix
  vs. `/route` check, monotonicity → "bike ≤ walk", completeness checks, sensitivity, slope
  comparison, reproducibility (→ V-numbers).
- **Checks:** lint + tests green; `uv run pytest -m db` against local PostGIS green;
  `docker build -f infra/api.Dockerfile .` and `-f infra/pipeline.Dockerfile .` succeed;
  `make refresh REACH_CONFIG=config/test_clip.yaml` runs acquire → tiles on the clip.
- **Done when:** draft PR `refactor(repo): port the foundation from the archive` into `dev`.

### S0.5 Walking skeleton — target 29 Nov · ready to merge after #80 (PR #81); Cloudflare setup open

- **Branch:** `feature/rico-delivery-skeleton`.
- **Dependencies to confirm first:** Vite, React, TypeScript, ESLint, Playwright (versions
  proposed in the step plan); Cloudflare's current recommendation (Pages vs. Workers static
  assets) checked with sources; official Wrangler action pinned to a commit SHA.
- **Files:** `web/` placeholder (name + build SHA from build-time config, `VITE_API_BASE`),
  `web/tests/` Playwright smoke test; `.github/workflows/ci.yml` (jobs: python, db-contract, web
  lint/build/Playwright, docker-build without push; **preview deploy job on pull requests from
  branches of this repository and on push to `dev`**, URL in the run summary; skipped for fork
  PRs, which get no secrets); `.github/workflows/deploy.yml` (full structure: `ci` on the merge
  commit → build and push images to GHCR by SHA → frontend to Cloudflare → backend job **skipped
  with a warning** without server secrets → smoke test → rollback + webhook on failure → summary;
  triggers: push to `main` and `workflow_dispatch` with a SHA and a target input; one
  `production` environment restricted to `main`; `concurrency`; least-privilege `permissions:`;
  all third-party actions pinned to SHAs).
- **Constraint (checked 21 Nov 2026, GitHub docs "Manually running a workflow"):**
  `workflow_dispatch` only works for workflows that exist on the default branch, here `dev`. So
  the PR itself is tested through the preview job in `ci.yml`; `deploy.yml` can be dispatched only
  after the merge into `dev`. Where the preview's Cloudflare secret lives (the `production`
  environment only admits `main`) is decided in the S0.5 step plan.
- **Your human does:** create the Cloudflare account/project and API token, the environments
  and their secrets as documented in `docs/deployment.md`; set the required status checks on
  `dev`. I list the exact names and scopes.
- **Checks:** CI incl. the preview job green on the PR, preview URL loads; after the merge into
  `dev`: `workflow_dispatch` of `deploy.yml` on `dev` with target **preview** deploys and
  smoke-tests the placeholder (never a push to `main`).
- **Done when:** draft PR into `dev`; after merge a `dev` push produces a working preview URL and
  the dispatch test passed.

### S0.6 Release v0.1.0 — target 30 Nov

- **Branch:** release PR `dev` → `main`, title `chore(release): v0.1.0`.
- **Files:** `CHANGELOG.md` (section 0.1.0), versions in `pyproject.toml` files and
  `web/package.json`.
- **Note:** the diff against `main` removes the old project; this is intended and stated in the PR.
- **Done when:** PR opened for Socke and Juju to approve; after a human merges it, `deploy.yml`
  deploys the placeholder to production on Cloudflare, the backend job is skipped with a warning,
  the frontend smoke test passes, and the summary shows SHA and URL. Tag only on instruction.

**Phase 0 done when:** plan confirmed and in the repo, docs consistent, foundation ported, CI
green and required on `dev`, a `dev` push produces a working Cloudflare preview URL, v0.1.0
deployed (or its PR waiting for approvals).

## Phase 1 — Backend: destinations, trip windows, transit, fit API (target 14 Dec 2026)

Code steps start after T1 and the fit formula are confirmed. Step plan first, wait, then commits.

### S1.0 Reference trips for V1 — 1 Dec to 12 Dec (runs alongside)

- Team collects ≥ 25 cell × destination pairs per mode: transit from the naldo/DB journey planner
  at the same trip window, walk/bike from a routing website or measured trips. I prepare the pair
  list and the collection sheet by 1 Dec (branch `docs/rico-reference-trips`); results are stored
  as fixtures, never queried by tests or the pipeline.

### S1.1 T1 transit engine — target 3 Dec · decided 23 Nov 2026 (O17, OpenTripPlanner)

- **Branch:** `exp/rico-transit-engine` (spike, not merged) + `docs/rico-t1-decision`.
- **Work:** compare (a) Valhalla multimodal (does `sources_to_targets` support it in 3.9.1 or a
  newer release?), (b) r5py / R5, (c) OpenTripPlanner, or a combination. Measure on the test clip
  and, if feasible, the city: matrix cell × destination, trip-window handling (arrival time,
  night), runtime, peak memory under A4, Docker/CI fit, image size, licence, bike as access mode
  (bike + transit). Fallback: departures at nearby stops, labelled approximate. Sources cited.
- **Done when:** recommendation presented, your human said yes, recorded as an O-decision in
  `architecture.md` (version + change log), AGENTS.md rule updated.

### S1.2 D1–D4 deployment decisions — target 3 Dec

- **Branch:** `docs/rico-deploy-decisions`.
- **Work:** D1 bwCloud vs. Hetzner (RAM, cost within 20 €, public IP/ports, how Actions reach
  it); D2 Cloudflare Tunnel vs. Caddy on 443 + SSH deploy; D3 own domain vs. free hostnames + CORS;
  D4 frontend–API wiring and where dev previews get data. Sources cited; recommendation; ask.
- **Done when:** decisions recorded in `architecture.md`; runbook outline in `deployment.md`, so
  your human can book the server right away (I never create or book one).

### S1.3 Fit formula — target 4 Dec

- **Branch:** `docs/rico-fit-formula`.
- **Work:** final proposal in `methodology.md`: smooth time decay around the user's "fine" time
  per destination type, importance weights, combination over modes and trip windows, weekly
  travel time, explanation selection (2–4 facts), worked examples with personas. Ask first.
  Open points from the S0.3 review: calibrate so that *s(t_d)* ≈ 0.9 (methodology M1); weight
  several campus sites by days per week instead of the mean (M7).
- **Done when:** confirmed and recorded (version + change log).

### S1.4 Data contract for results — target 5 Dec

- **Branch:** `docs/rico-data-contract-results`.
- **Tables (proposal, details in the step plan):** `cells` (origin kind: populated / address),
  `districts`, `destination_types`, `destinations`, `campus_sites`, `addresses`, `stops`,
  `stop_departures` (stop × trip window), `travel_times` (cell × destination × mode × trip window:
  time and transit legs), `rent` (optional), `validation_report`; `current` views; API response
  schemas.
- **Done when:** confirmed; `docs/data_contract.md` updated.

### S1.5 Production backend and deploy — target 7 Dec

- **Branch:** `feature/rico-backend-deploy`. Needs D1–D4 decided and the server booked and set up
  by your human from the runbook.
- **Files:** `compose.prod.yaml` (images from GHCR by SHA, + `cloudflared` if D2 = tunnel,
  persistent volumes, no public ports for PostGIS, Valhalla or the transit engine, secrets only in
  `.env` on the server), `infra/Caddyfile` if D2 = Caddy, runbook in `docs/deployment.md`;
  `deploy.yml` backend job enabled: pull images by SHA, run migrations, `docker compose -f
  compose.prod.yaml up -d`, keep data volumes; smoke test (frontend loads, API health); rollback
  of backend and frontend to the previous SHA on failure.
- **Checks:** `workflow_dispatch` on `dev` against the server deploys a SHA, smoke test passes;
  one deliberately broken SHA must roll back and fail the run with a webhook message.
- **Done when:** backend runs in production with the health endpoint; smoke test is extended in
  S1.10 with a fit request (persona) and a cell request.

### S1.6 Acquire: destinations, campus, addresses, GTFS windows — target 8 Dec

- **Branch:** `feature/rico-acquire-destinations`.
- **Files:** `pipeline/…/destinations.py` (from `facilities.py`), `addresses.py`, `campus.py`,
  `gtfs.py` (reference date per trip window, times > 24:00), `stages/validate.py`; config sections
  `destination_types`, `trip_windows`; tests with small fixtures.
- **Checks:** completeness (every campus site found, every hobby category ≥ 1 destination, GTFS
  covers every trip window, fails loudly otherwise); test clip run.

### S1.7 Transit engine service — target 9 Dec

- **Branch:** `feature/rico-transit-engine`.
- **Files:** compose service or pipeline step per T1 (image pinned), build inside `make refresh`
  (sequential, A4), Dockerfile if needed, recorded engine responses as test fixtures.
- **Checks:** `make refresh REACH_CONFIG=config/test_clip.yaml` builds the engine; peak memory logged.

### S1.8 Travel-time stage — target 11 Dec

- **Branch:** `feature/rico-travel-times`.
- **Files:** `stages/travel_times.py`: cell × destination × mode × trip window, nearest k per
  destination type, all campus sites; batched (blocks, prefilter, `costmatrix` for walk/bike),
  idempotent, manifest, runtime and peak memory logged.
- **Checks:** unit tests with recorded responses; plausibility checks of V2 in the stage report.

### S1.9 Publish + data-contract tests + validation — target 12 Dec

- **Branch:** `feature/rico-publish-results`.
- **Files:** `infra/db/run_schema.sql`, `stages/publish.py`, `stages/validate_results.py` (V2, V3
  checks with warn/fail limits from config), data-contract tests (`-m db`).
- **Checks:** CI db-contract job green; full test clip run publishes to `current`.

### S1.10 API — target 13 Dec

- **Branch:** `feature/rico-fit-api`.
- **Endpoints:** `GET /api/health`, `GET /api/destination-types`, `GET /api/campus-sites`,
  `GET /api/addresses?q=` (PostGIS search), `POST /api/fit` (student profile → ranked areas with
  reasons, < 500 ms for the whole city; POST bodies not logged; cache keyed on the weight vector
  only), `GET /api/cell/{id}` (all trips per mode and window), live route incl. a transit leg (*Check*).
- **Checks:** unit tests, response-time test, integration test on the test clip; `make up`
  serves the API; Dockerfiles for all backend images build in CI; `deploy.yml` smoke test extended
  with one fit request (persona) and one cell request.

### S1.11 First production data + release v0.2.0 — target 14 Dec

- Your human runs the first `make refresh` on the server from the runbook (scheduling follows in
  S3.1); `current` switches only after validation passes; peak memory recorded.
- V1 fixtures from S1.0 committed; first V1 numbers in `docs/validation.md`.
- Release PR `chore(release): v0.2.0` for Socke and Juju; after the merge `deploy.yml` deploys
  frontend and backend, smoke test incl. fit and cell request passes.

**Phase 1 done when:** `make refresh REACH_CONFIG=config/test_clip.yaml` runs end to end with
transit, `make up` serves the API, CI green, docs updated, runtime/memory in the PRs, and v0.2.0
runs in production with backend (or its PR waits for approvals).

## Phase 2 — Student web app (target 9 Jan 2027)

Starts after Phase 1 is merged into `dev`; S2.1 and the fixture-based parts of S2.2–S2.4 may start earlier because they need only the API shapes of S1.4 (API fixtures). Plan screens and components first, wait for yes. Product v1.1 (24 Nov 2026): two modes, no onboarding questionnaire.

| Step | Branch | Content | Target |
|---|---|---|---|
| S2.0 | `docs/rico-user-interviews` | user test round 1: short interview guide on destinations, defaults and wording (which destinations students expect, whether the defaults fit, what the panel should call things); your human runs the interviews; findings feed S2.1 and `docs/validation.md` | before 17 Dec |
| S2.1 | `docs/rico-app-screens` | screens and components for *Find*, *Check* and the profile panel (desktop + mobile bottom sheet), texts (EN first, DE), defaults from S2.0, D5 basemap research and decision | 17 Dec |
| S2.2 | `feature/rico-app-shell` | app shell, i18n, student profile in URL/localStorage only, API base URL from build config | 19 Dec |
| S2.3 | `feature/rico-profile-panel` | profile panel with the default profile, live update of the map, programme hint while no programme is set, personas as example profiles | 22 Dec |
| S2.4 | `feature/rico-result-map` | *Find*: MapLibre map opening with the default profile, cell fits, best areas with plain-language reasons | 30 Dec |
| S2.5 | `feature/rico-place-check` | *Check* for one place: address search in the header or pin, fit, rank in the city, trips per mode and window, optional listing rent | 3 Jan |
| S2.6 | `feature/rico-compare` | *Check* for two or three places side by side, differences in plain language incl. rent, kept in the URL | 5 Jan |
| S2.7 | `feature/rico-app-quality` | mobile-first, contrast, Playwright *Find* and *Check* mobile + desktop with API fixtures, axe without serious violations | 7 Jan |
| S2.8 | `docs/rico-user-test` | user test round 2: short app test with a task script (find a place for persona X, check an address, compare two places) for 5 students, sessions run by your human in early January; findings → changes + section in `docs/validation.md` | 9 Jan |
| S2.9 | release | `chore(release): v0.3.0` | 9 Jan |

CI checks: `npm run lint && npm run build`, Playwright, axe. No tracking or analytics.

## Phase 3 — Hardening (target 16 Jan 2027)

Production runs since v0.2.0 (S1.5, S1.11). Starts after Phase 2 is merged. Plan, wait for yes.

| Step | Branch | Content | Target |
|---|---|---|---|
| S3.1 | `feature/rico-scheduled-refresh` | scheduled `make refresh` on the server, `current` switches only after validation, failure notification, measured peak RAM during refresh | 12 Jan |
| S3.2 | `feature/rico-ops-hardening` | backups and restore test, reboot recovery, rollback drill with a deliberately broken SHA on the current release, runbook completed | 14 Jan |
| S3.3 | `docs/rico-validation-report` | `docs/validation.md` complete for V1–V8 | 16 Jan |
| S3.4 | release | `chore(release): v0.4.0` for Socke and Juju; not merged by me | 16 Jan |

Buffer until 22 Jan: fixes, final docs, `v1.0.0` release PR on instruction.

## Validation (defined in `methodology.md`, reported in `docs/validation.md`)

| # | What |
|---|---|
| V1 | Travel times vs. external reference, ≥ 25 pairs per mode, median and 90th-percentile deviation |
| V2 | Plausibility: transit ≥ walk to first stop + wait; transit never faster than straight line at bus speed; night never better than morning; bike ≤ walk for > 95 % of pairs (warn/fail limits in config) |
| V3 | Completeness: campus sites found and routable, every hobby category ≥ 1 destination, GTFS covers all trip windows |
| V4 | Sensitivity: rankings under fit parameters ±25 % and other trip windows (rank correlation); explanations match the numbers |
| V5 | Matrix vs. single route (from the archive's V10) for walk and bike |
| V6 | Users: interviews on destinations and defaults (S2.0) and the app test (S2.8) |
| V7 | Deployment: smoke-test results per release |
| V8 | Reproducibility: a teammate runs the pipeline from the README only |

## Risks

| Risk | Effect | Mitigation |
|---|---|---|
| No transit engine fits 8 GB next to Valhalla, PostGIS and API | transit mode late or approximate | sequential refresh (A4), measure in S1.1, fallback "departures at nearby stops, labelled approximate" |
| Night/weekend service not in the GTFS feed or feed expiring | trip windows fail | validity check fails loudly (S1.6); window dates configurable |
| OSM incomplete for Mensa, university sports, hobbies | missing destinations | manual tables (`campus.yaml`), completeness check V3, gaps listed in the app |
| No legal rent source | rent context missing | rent is typed in per listing in *Check* (product v1.1); the input is the first cut after bike + transit |
| Server not booked and set up soon after D1–D4 (3 Dec) | S1.5 and v0.2.0 with backend slip | runbook outline with D1–D4; S1.6–S1.10 do not depend on the server |
| Cloudflare secrets not ready in time | S0.5/S0.6 blocked | list secrets early in `deployment.md`; backend job skips without secrets |
| Two approvals for `main` over the holidays | releases wait | open release PRs early with a summary; plan reviews with Socke and Juju |
| Christmas break and exam period | Phase 2 slips | cut order: bike + transit, rent input, comparing several places; buffer week |
| 20 € budget | server time limited | D1 with costs; server only from when it is needed until after grading |
| Phase 0 in 9 days | late start of Phase 1 | docs short and factual; port as is where possible |
