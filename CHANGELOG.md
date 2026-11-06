# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Every PR with a user-visible or architectural change
adds a line under `Unreleased`.

## [Unreleased]

### Added (recommender, P7)
- Pipeline stage `recommend` (methodology v0.6 §5, architecture v0.18 §6.4): 100 m grid
  candidates inside the urban boundary without forest, farmland, water and protected areas
  (industrial allowed), catchments per profile in candidate groups (`costmatrix`, cells →
  zone centre), greedy per category × profile with gain = reduction of the deficit sum; top 5
  per category, minimum gain 50 residents, profiles `walking_339`, `walking_500`,
  `wheelchair_339` (cycling off for now); new config section `recommend`.
- Run tables `recommendations` and `recommendation_catchments`; `validate_results` check
  `recommendations_consistent` (replays the gains on `access_counts`) and a report section;
  `publish` drops `current` views of relations a run does not have (data contract v0.10).
- API: `GET /api/recommendations` returns the ranked zones (GeoJSON, with district);
  `POST /api/catchment` accepts `{candidate_id, category, profile}` and answers with the stored
  catchment of the zone (`source: precomputed`).
- Web: "Recommended sites" panel and ranked markers on the map; a click shows the zone's
  catchment (cells and reverse isochrone) and today's classes of its residents; stated limits
  in the panel; hidden when a run has no recommendations.
- `make refresh` and `make pipeline` run `recommend` between `score` and `validate_results`.

### Changed
- Wheelchair profile documented as it behaves (notes N11): it avoids steps but not steep
  sections, because Valhalla 3.9.1 ignores `max_grade`; known limitation (wheelchair counts
  optimistic on hillsides) in `methodology.md` v0.5 §1, `architecture.md` v0.17 §6.1 and the
  `wheelchair_339` comment in `config/config.yaml`. Counts and config values unchanged.
- Web inspector shows the travel time first: the route to the nearest facility reads
  "Route to the nearest: 16.4 min · 697 m" (time from /route, length secondary) instead of only
  its length, and the times of the reachable facilities are no longer greyed out (notes N9).
- Documented that walking and wheelchair times include Valhalla's slope model (notes N5
  settled, decision: keep it, counts unchanged): `architecture.md` v0.16 §6.1 and O7 (what
  Valhalla does with elevation per profile, with evidence), `methodology.md` v0.4 (speeds are
  flat-ground speeds, results conservative; new experiments V10 "matrix vs. /route" (existing checks)
  and V11 "with vs. without slopes" (P7); architecture §7 names the /route checks of
  `validate results`.
- `validation.results.false_negatives.warn_above` 0 → 0.005: one missed pair in a sample of
  ~480 (rare block `costmatrix` effect, notes N9) no longer warns; fail stays above 2 %.

### Added (validation)
- `validate_results` check `budget_flips` (methodology V10): per profile and direction the share
  of sampled pairs on which matrix and /route lie on different sides of the budget, from the
  `matrix_vs_route` and `false_negatives` samples; report section "Budget flips", warns above
  `validation.results.budget_flips.warn_above` (5 %), never fails (data contract v0.9).

### Added
- `validate_results` check `false_negatives` (notes N9): random cell × facility pairs within the
  prefilter reach that are not in `reachable` are routed with /route; the share reached within
  the budget is reported per profile and category (report part 2, section "Missed facilities")
  and warns above `validation.results.false_negatives.warn_above` (0), fails above
  `fail_above` (2 %). Golden tests replay the recorded count blocks of the three N9 examples.
- Web app (`web/`, P6): React + TypeScript + Vite + MapLibre GL JS, served by Caddy at `:8080`
  (`infra/web.Dockerfile`: Node 24 build → `caddy:2.11.7-alpine`). Profile and category
  selector, class map of cells from `/api/cells` with a colour-blind-safe legend (ordered
  lightness, checked with simulated deuteranopia/protanopia), residents per class, district
  statistics, pin-drop inspector (`POST /api/inspect`: classes, counts, weakest category,
  reachable facilities, route to the nearest, 5/10/15 min isochrone; live results labelled,
  messages for 422/429/502/503/504), data & validation page from `/api/meta` with known
  limitations, attribution always visible; recommendations layer hidden until P7. Basemap:
  OpenFreeMap Positron (no key). CI job `web`: lint, type check, build, bundle sizes, Playwright
  smoke test against recorded API responses.
- `GET /api/meta`: `profiles[].transit_budget_min` (walking time to stops, from
  `time_budgets_min.transit`; null without transit; data contract v0.8); the transit legend
  shows it.
- `reachable` table (`count/reachable.parquet`, run schema, data contract v0.7): every
  facility a cell reaches within the budget per profile with its matrix time; the pin-drop
  inspector lists reachable facilities from it, so list and count match the map by construction
  (notes N7 settled). `validate_results` checks `reachable_matches_counts` and compares a
  sample of matrix times with Valhalla /route (`matrix_vs_route`, known limitation in report
  part 2; `validation.results.route_check`). API: own live-matrix client for grid cells without
  residents and catchments (`api.live_matrix`: timeout, concurrency), `source: live`, 504 on
  timeout.
- `docs/implementation_plan.md`: phase plan P0–P8, proposed data contract, [VERIFY] items, risks,
  conflicts and decisions; handoff file between agent sessions.
- `docs/architecture.md`: target architecture with Valhalla as the single routing engine,
  Zensus 100 m grid, weekly validated pipeline, PostGIS, FastAPI, React + MapLibre, Hetzner CX23 hosting.
- `AGENTS.md` and `CLAUDE.md`: shared rules for coding agents, incl. task workflow, docs-sync rule,
  efficiency rules, commit and version-history rules, prompting guide, terms and roles.
- `CONTRIBUTING.md`: branch, commit, PR, review and release workflow.
- `.gitignore` for Python/uv, secrets, local data and frontend builds.
- `README.md` rewritten: summary, status, features, architecture diagram, layout, setup, data
  sources, documentation, team, milestones; agents keep it up to date automatically.
- `docs/methodology.md`: binding categories, thresholds, scoring, recommender, validation
  experiments (V1–V9) and open methodology questions (M1–M6).
- `docs/glossary.md`: project vocabulary, moved out of `AGENTS.md`.
- Python uv workspace: root `pyproject.toml` (dev tools, ruff and pytest config), `pipeline` and
  `api` packages with baseline dependencies and smoke tests, `.python-version` 3.12,
  `uv.lock` and `requirements.txt` export.
- `docs/prompts/implementation.md`: start prompt (P0) and per-phase prompt for implementing the
  architecture with a coding agent.
- P1 scaffold: `Makefile` (`up`, `down`, `logs`, `pipeline`, `test`, `lint`, `format`),
  `compose.yaml` (PostGIS `imresamu/postgis:18-3.6`, API placeholder with hot reload, Caddy
  placeholder; Valhalla 3.9.1, `valhalla-build` and `pipeline` behind Compose profiles),
  `.env.example`, `infra/Caddyfile`.
- `config/config.yaml` (study area, profiles, categories, transit classes, sources, validation)
  and `config/test_clip.yaml`; typed loader with validation (`reach_pipeline.config`).
- Pipeline stage pattern: `python -m reach_pipeline <stage>`, run ids, manifests with checksums,
  runtime and peak memory, exit codes; no-op `hello` stage.
- API placeholder `GET /api/health`.
- CI workflow (ruff + pytest with uv), PR template, CODEOWNERS.
- `docs/data_contract.md` draft v0.1; `pipeline/AGENTS.md`, `api/AGENTS.md`.
- P2 pipeline stage `acquire`: downloads OSM (Geofabrik), GTFS (NVBW naldo) and Zensus 2022 with
  retries; skips unchanged sources (`.md5`, `ETag`/`Last-Modified`, SHA-256) and hard-links them
  from the previous run; provenance in `data_sources.parquet`; unpacks the needed zip members.
- P2 pipeline stage `validate`: osmium-based OSM processing (admin boundary, urban boundary O17a,
  routing area, clipped `routing.osm.pbf`, facilities with park access points, districts), Zensus
  cells, GTFS stops and reference weekday; cleaned GeoParquet layers and validation report part 1
  (`report_inputs.json` + `.md`).
- Config: `districts.admin_levels` (list, coverage check), `reference_day` (BW public and school
  holidays 2026–2028, static), `download`, zip `members`, `access_points.walkable_highways`,
  `validation.official_population` 90,499 (Zensus 2022).
- osmium-tool as a system requirement (README) and installed in CI.
- `validate` coverage check `scored_share` (≥ `validation.min_scored_share` 0.98) and excluded
  residents per district in the validation report.
- P3 Valhalla: `config/valhalla.json` (generated with `valhalla_build_config` 3.9.1, matrix
  limit 25,000 pairs for pedestrian/bicycle, 2 build threads, 256 MB tile cache, no admin
  database); `compose.yaml` `valhalla-build` one-shot (elevation download, tiles, tar extract
  into `<data_dir>/valhalla/build/`); `make refresh` (acquire → validate → `tiles check` →
  build + `mv` swap + restart if needed → `tiles verify` → `count`, O19).
- P3 pipeline stage `tiles`: `tiles check` writes the rebuild flag from a fingerprint of the
  clipped PBF, `config/valhalla.json` and the elevation setting; `tiles verify` checks that
  Valhalla serves this config's tiles, routes a golden pair and checks grades (VF1).
- P3 pipeline stage `count`: async Valhalla client (bounded concurrency, retries, compact
  matrix), 500 m blocks, exact straight-line prefilter, one matrix per block and profile for all
  categories and stops; `access_counts.parquet`, `transit_supply.parquet`, `stops.parquet` with
  weekday departures (DuckDB over `stop_times.txt`), `report_count.json` with prefilter evidence
  (O20).
- Config: `tiles.verify`, `valhalla` (url, concurrency, timeouts, retries, matrix pair limit),
  `count` (block size, prefilter evidence sample).
- Golden travel-time integration tests (`tests/integration/`, marker `integration`, deselected
  by default); recorded Valhalla matrix fixture for unit tests.
- `docs/notes.md` N4 (Valhalla memory per worker thread) and N5 (walking times depend on slopes
  when tiles carry elevation); data contract v0.4 (`tiles/`, `count/` files); glossary: block,
  prefilter evidence.
- P4 database: `infra/db/roles.sql` (`pipeline_write`, `app_read`, `supervisor_read`, default
  privileges), `infra/db/migrations/0001_meta.sql` (`meta.runs`, `meta.data_sources`, schema
  `current`), `infra/db/run_schema.sql` (run tables with GiST indexes, `scores` and
  `transit_scores` views, `district_scores` materialized view); `python -m reach_pipeline
  migrate` / `make migrate` (roles, passwords from `.env`, numbered migrations recorded in
  `meta.schema_migrations`).
- P4 pipeline stages `score` (`thresholds.parquet`), `validate_results` (validation report
  part 2: completeness, value ranges, thresholds, class totals, monotonicity between profiles,
  sample cells), `publish` (COPY into `run_<id>` in one transaction, then all `current` views in
  one transaction; `meta.runs` status) and `cleanup` (keeps the last 3 published runs: schemas,
  `data/raw/<run_id>/`, `data/runs/<run_id>/`).
- Failure webhook: a failed stage posts to `FAILURE_WEBHOOK_URL` if set.
- Config: `validation.results.monotonic` (warn/fail share per profile pair), `database`
  (`sql_dir`, connection retries), `cleanup.keep_published_runs`; category id `transit` reserved.
- PostGIS data-contract tests (marker `db`, `REACH_TEST_DATABASE_URL`) and CI job `db-contract`
  with a PostGIS service container.
- `.env.example`: `DATABASE_URL_ADMIN`, `REACH_TEST_DATABASE_URL`; data contract v0.5;
  `docs/notes.md` N6 (faster walking can reach fewer facilities: Valhalla routes by cost);
  glossary: validation report, monotonicity check, published run, migration.
- P5 API (`api/`): read endpoints `GET /api/meta`, `/api/districts`,
  `/api/districts/{id}/scores`, `/api/cells` (GeoJSON in EPSG:4326 built in PostGIS, transit
  classes via `category=transit`, ETag per run, gzip via Caddy) and `/api/recommendations`
  (empty until P7); live endpoints `POST /api/inspect`, `/api/catchment`, `/api/expansion`
  (Valhalla isochrone/matrix/route/expansion, snapped to the 100 m grid cell, boundary check,
  LRU cache per run/cell/profile, token-bucket rate limit per client IP behind Caddy);
  `infra/api.Dockerfile`, `.dockerignore`, `api` section in `config/config.yaml`; tests with a
  fake database, recorded Valhalla responses and PostGIS (`-m db`). `inspect` shows the
  precomputed count for scored cells (`count_source`); every GET endpoint also answers HEAD; data contract v0.6 (API responses); `docs/notes.md` N7
  (store the nearest facility in the pipeline) and N8 (live and block matrices use different
  Valhalla algorithms); glossary: grid cell (snapping), live endpoint, trusted proxy.

### Changed
- Valhalla config is effective by construction (notes N9): the `valhalla` service mounts
  `config/` (not the single file, whose bind mount kept the old inode after a git checkout),
  copies `valhalla.json` to `<data_dir>/valhalla/valhalla.effective.json` at every start and
  serves that copy. New `make valhalla-config` recreates the service if the copy differs (run
  by `make up`, `make refresh` and `make pipeline`); `count` fails if Valhalla runs another
  config and records the copy (input checksum, `report_count.json` `valhalla`, incl.
  `thor.source_to_target_algorithm`); `validate_results` fails if Valhalla's config changed
  since `count`.
- `make up` builds the Caddy image with the web app; `infra/web-placeholder/` removed.
- `config/valhalla.json`: `thor.source_to_target_algorithm` `costmatrix` instead of
  `select_optimal`, so every matrix request uses one algorithm (notes N8 settled; architecture
  v0.15 §6.5 rules 2, 6, 8). `count` 264–294 s (was ~243 s), `publish` ~7 s (was ~1 s).
- Pipeline manifests: each stage records the digest of only the config sections it uses
  (`CONFIG_SECTIONS`, input `config:<sections>`) instead of the config files, so the `api`
  section or unused sections no longer re-run stages such as `count`; `meta.runs.config_hash`
  covers all sections except `api`. Manifests of older runs trigger one re-run per stage.
- `docs/architecture.md` v0.14: inspector snaps every point to its 100 m grid cell and uses one
  live matrix for the reachable facilities (§6.5 rule 8); live endpoints also accept points in
  scored cells outside the urban boundary (rule 12); §9 endpoint details.
- `compose.yaml`: the `api` service runs the `infra/api.Dockerfile` image (78 MB idle instead of
  ~400 MB); `make up` builds it. New dependencies `psycopg-pool`, `pyyaml` (api) and `httpx2`
  (dev, removes the Starlette TestClient warning).
- `AGENTS.md` rule 6: `cleanup` may drop old run schemas and their `meta` rows (aligned with
  architecture §7; reported in P4).
- `docs/architecture.md` v0.13: §7 names `cleanup` as dropping old run schemas (matches rule 6).
- `make pipeline`/`make refresh` pass `.env` to the pipeline (`uv run --env-file`) and run all
  stages up to `cleanup`; `recommend` (P7) is the only stage still logged as skipped.
- Monotonicity 5.0 ≥ 3.39 km/h is checked with a tolerance instead of failing on any violation
  (implementation plan P4, decision by Juju; `docs/notes.md` N6).
- Valhalla is part of `make up` once tiles exist (Compose profile `routing` removed); it runs
  with 2 worker threads and serves `$VALHALLA_DIR` (`<data_dir>/valhalla`).
- Scoring scope = every populated cell whose centre lies inside the city boundary (was: urban
  boundary); the routing area is the city boundary + 4 km; the urban boundary only defines the
  map area, the live-endpoint check and recommender candidates (architecture v0.12: O11, O13,
  O17 settled; methodology v0.3; glossary). Urban boundary land use extended by `education`,
  `institutional`, `religious`, `closing_m` 100.
- `CONTRIBUTING.md` §1–2 and `AGENTS.md`: topic branches carry the driving person's name
  (`<type>/<name>-<topic>`); never work on a branch with another person's name.
- `AGENTS.md`: a confirmed phase plan counts as "ask first" approval for what it names explicitly.
- `docs/architecture.md` v0.11: settled O18 (`transit_supply` table + `transit_scores` view),
  O19 (`make refresh` orchestrates tile build and pipeline on the host), O20 (prefilter reach with
  speed factor and margin, routing buffer check).
- `docs/methodology.md` v0.2: facility locations (access points for parks and playgrounds),
  transit supply for walking and wheelchair profiles.
- `docs/glossary.md`: reach, access point, refresh, transit supply.
- `AGENTS.md`: project status line, sources of truth, test/fixture rules (mocked Valhalla),
  notebook policy, `.env.example` rule; agents may push their own branch and open draft PRs;
  new config keys and docs-only changes no longer need confirmation.
- `docs/features.md` and `docs/project_management_decisions.md` updated to the current
  architecture (profiles, Hetzner hosting, O/M/V numbers, new roadmap).
- `docs/architecture.md` v0.9: methodology references point to `methodology.md`.
- `docs/architecture.md` v0.10: `scores` and `district_scores` are views over raw counts and a
  `thresholds` table (classes and deficits derived at read time).

### Removed
- No-op `hello` stage (replaced by `acquire` as first stage); `make pipeline STAGE=<planned stage>`
  now fails with a clear message, `make pipeline` logs planned stages as skipped.
- `docs/architecture_proposal.md` (superseded by `architecture.md` and `methodology.md`).
- `docs/2026_10_19_kickoff.md` (superseded early concept).
