# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Every PR with a user-visible or architectural change
adds a line under `Unreleased`.

## [Unreleased]

### Added
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

### Changed
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
