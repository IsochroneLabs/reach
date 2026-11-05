# Implementation plan — reach

> **Status:** P0 done (2 Nov 2026): Q1–Q5, C6–C12 and review points confirmed and applied
> (then architecture v0.11, methodology v0.2). P1 merged (PR #19). P2 merged (PR #20; N3
> decision → architecture v0.12, methodology v0.3). P3 merged (PR #21, 5 Nov 2026; full depth:
> all profiles and categories; open decisions N4, N5, cycling factor). P4 merged (PR #22, 5 Nov
> 2026; full depth; monotonicity with tolerance, N6). P5 merged (PR #24, 5 Nov 2026, full depth,
> architecture v0.14); N8 follow-up: one matrix algorithm + `reachable` (architecture v0.15). Next: P6. This file is the **handoff between
> agent sessions**: phase status, decisions, agreed deviations, measured numbers and next steps.
> It is informative; `architecture.md` and `methodology.md` stay binding. Where this plan proposes
> something that differs from them, it is listed in [Section 5](#5-conflicts-gaps-and-ambiguities)
> and only implemented after confirmation (plus a doc update in the same branch).

---

## 1. Phase status

| Phase | Topic | Branch | Status | Target date |
|---|---|---|---|---|
| P0 | Implementation plan | `docs/rico-implementation-plan` | [x] PR #17 | 2 Nov |
| P1 | Scaffold & tooling | `feature/rico-scaffold` | [x] merged PR #19 | 6 Nov |
| P2 | acquire + validate inputs | `feature/rico-acquire-validate` | [x] merged PR #20 (interim depth; test-clip script open) | 11 Nov |
| P3 | tiles + count | `feature/juju-tiles-count` | [x] merged PR #21, 5 Nov (full depth) | 16 Nov |
| P4 | score + publish + cleanup | `feature/juju-score-publish` | [x] merged PR #22, 5 Nov (full depth) | 19 Nov |
| P5 | API | `feature/rico-api` | [x] merged PR #24, 5 Nov (full depth; N7/N8 follow-up `fix/rico-matrix-algorithm`) | 21 Nov |
| P6 | Web | `feature/rico-web` | [ ] | 24 Nov |
| — | **Interim demo (local), `v0.1.0`** | release PR `dev` → `main` on request | [ ] | 25 Nov |
| P7 | Recommender + validation V1–V9 | `feature/rico-recommender`, `feature/rico-validation` | [ ] | 10 Jan |
| P8 | Production | `feature/rico-production` | [ ] | server from ~1 Dec, hardening until 15 Jan |

The dates leave about four working days per phase until 25 Nov. To make the interim demo, P1–P6
are built at **minimal depth** (marked *interim* below); the rest of each phase (*full*) is
finished between 25 Nov and 20 Dec, before P7. Branch names contain the name of the person
driving the session (`<type>/<name>-<topic>`, AGENTS.md since PR #18, e.g. `feature/rico-scaffold`), so two sessions never
work on the same branch; an issue number goes in front of the topic if an issue exists.

## 2. Phases in detail

Conventions used by every phase:

- **Stage pattern (N2):** `python -m reach_pipeline <stage> [--run-id ID] [--config PATH]`;
  `run` executes all stages in order. Each stage is a module with one public
  `run(ctx: RunContext) -> Manifest`; `RunContext` holds the typed config, `run_id` and paths.
  At start it checks the previous stage's manifest (`status == "ok"`, input checksums and config
  digest match; since P5 each stage hashes only its `CONFIG_SECTIONS`), at
  the end it writes `data/runs/<run_id>/<stage>/manifest.json` (inputs with checksums, outputs,
  row counts, runtime, peak RSS, status). Re-running a stage with unchanged inputs is a no-op.
- **Run id:** UTC timestamp with seconds `YYYYMMDDTHHMMSSZ` (e.g. `20261116T030000Z`, no collisions on manual
  reruns); DB schema `run_20261116t030000z`.
- **Measurement:** one helper logs wall time and peak memory (`resource.getrusage` for self and
  children, normalised to MB: `ru_maxrss` is KB on Linux and bytes on macOS; children = maximum of
  any child, not the sum) per stage; values go into the manifest and the PR.
- **Exit codes:** 0 ok; 1 validation failed; 2 configuration error; 3 external failure (network,
  Valhalla, DB) after retries. `tiles check` signals "rebuild needed" with a flag file
  `data/runs/<run_id>/tiles/rebuild_needed`, not with an exit code (see P3).
- **Logging:** `logging` with one format (`time level stage message`), no `print`.

### P1 — Scaffold & tooling

*Interim = full* (everything in P1 is needed for the demo).

| Create / change | Content |
|---|---|
| `Makefile` | `up`, `down`, `logs`, `pipeline` (`STAGE=` optional), `test`, `lint`, `format`; thin wrappers around `uv` and `docker compose` |
| `compose.yaml` | `db` (PostGIS, healthcheck `pg_isready`), `valhalla` (official image, tag pinned, internal network, `/status` healthcheck; port published to `127.0.0.1` only for local dev), `api` (hot reload, placeholder until P5), `caddy` (serves placeholder until P6); `valhalla-build` and `pipeline` under a Compose profile so `make up` does not start them |
| `.env.example` | DB passwords per role, `REACH_CONFIG`, `VALHALLA_URL`, `DATABASE_URL`s, `FAILURE_WEBHOOK_URL` (optional, empty = no-op), each with a comment |
| `config/config.yaml` | study area (city name, admin boundary relation, urban boundary rules O17a, buffer 4000 m), profiles (§6.1 incl. costing options), time budgets (15 / 10 min), categories + OSM tags + `k_c` (methodology §2), transit classes (methodology §3), data source URLs, validation thresholds; every key commented |
| `config/test_clip.yaml` | override for the ~1 km² test clip (used from P2 on) |
| `pipeline/src/reach_pipeline/config.py` | pydantic models + `load_config(path) -> Config`; validates: speeds > 0, `k_c ≥ 1`, unique category ids, tags non-empty, transit bounds increasing, routing buffer ≥ largest prefilter reach (speed × `max_speed_factor` × budget + `prefilter_margin_m`) of all profiles (O20) |
| `pipeline/src/reach_pipeline/{__main__.py, cli.py, context.py, manifest.py, metrics.py}` | stage pattern skeleton with a no-op `hello` stage proving the pattern end to end |
| `pipeline/tests/test_config.py`, `test_manifest.py` | valid config loads; each invalid case fails with a clear message; manifest round-trip |
| `.github/workflows/ci.yml` | `astral-sh/setup-uv` (cache), `uv sync --frozen`, ruff check + format check, `uv run pytest` |
| `.github/pull_request_template.md` | template from `CONTRIBUTING.md` §4 |
| `.github/CODEOWNERS` | `@RicoS03 @konstantinholl @nicholas-tuebi` for every folder until T2 is settled (Q4) |
| `pipeline/AGENTS.md`, `api/AGENTS.md` | stage pattern (N2), test layout, mocked Valhalla; API read-only from `current` |
| `docs/data_contract.md` | first draft with the tables in [Section 3](#3-proposed-data-contract-docsdata_contractmd) |
| `README.md`, `CHANGELOG.md`, `AGENTS.md` status line, `docs/notes.md` (close N2) | kept true |

**Done when:** `uv run ruff check . && uv run ruff format --check . && uv run pytest` pass;
`make up` shows `db` healthy (`docker compose ps`); `make pipeline STAGE=hello` writes a manifest;
CI green on the draft PR.

### P2 — acquire + validate inputs

| Create | Key functions |
|---|---|
| `stages/acquire.py` | `download(source) -> Path` with retries/backoff, skip if unchanged (Geofabrik `.md5`, HTTP `ETag`/`Last-Modified`, local checksum); unchanged files are hard-linked from the previous run; provenance rows (URL, retrieved at, checksum, licence); zip archives (GTFS, Zensus) are unpacked to the needed members (`stops.txt`, `stop_times.txt`, `trips.txt`, `calendar*.txt`, Zensus CSV) in `data/raw/<run_id>/`, because DuckDB does not read inside zips |
| `osm.py` | `osmium tags-filter` / `osmium extract -p` / `osmium export` wrappers (subprocess, streaming, no full PBF in Python). Order (two passes): 1. `tags-filter` admin boundaries + land use from the full regbez PBF; 2. compute urban boundary and routing area (`boundary.py`); 3. `extract -p` with the routing area as EPSG:4326 polygon → clipped PBF; 4. `tags-filter`/`export` facilities, ways and districts from the clipped PBF |
| `boundary.py` | `admin_boundary(...)`, `urban_boundary(landuse, admin, cfg)`: dissolve built-up land use inside the city, `buffer(+closing_m).buffer(-closing_m)` (100 m since v0.12), drop parts < configured min area, keep Teilorte as separate parts (O17); `routing_area = city.buffer(4000)` (O13, v0.12); `scoring_scope` (O11) |
| `zensus.py` | DuckDB streaming read of the national 100 m CSV filtered by bbox in EPSG:3035 (cell-centre columns, expected `x_mp_100m`/`y_mp_100m`) while reading; the grid id column (expected `GITTER_ID_100m`, verified in P2) kept as `cell_id`; cell polygon + centroid in 25832 |
| `gtfs.py` | DuckDB reads `stops.txt`, `calendar*.txt`; `reference_weekday(feed, holidays)`; stops of `location_type` 0 or empty inside the routing area |
| `facilities.py` | tag → category mapping from config; points stay points, polygons → `representative_point`; parks/playgrounds → access points: intersections of walkable ways with the park boundary, fallback every 50 m along the boundary, at most `max_points` per park, chosen evenly spaced along the boundary (config; methodology §2); edge cases: a footway running along the boundary (intersection is a line → use its end points), playgrounds mapped as nodes (the node itself); de-duplication of node + area of the same facility |
| `stages/validate.py` | schema + plausibility checks (CRS, non-empty, population total vs. official city total ± tolerance, cells inside boundary, facilities per category > 0, GTFS validity covers reference day); writes cleaned GeoParquet (`cells`, `facilities`, `stops`, `districts`, `urban_boundary`, `routing_area`) and validation report part 1 (`report_inputs.json` + Markdown) |
| `scripts/build_test_clip.py` (or `python -m reach_pipeline make-test-clip`) | cuts ~1 km² (old town incl. Neckar bridge) from a real run into `tests/fixtures/clip/` (< 1 MB each; PBF, Zensus subset CSV, GTFS subset) |
| tests | unit tests with tiny synthetic fixtures for boundary closing, facility mapping/dedupe, reference weekday (holiday + `calendar_dates` exceptions), Zensus parsing |

**Done when:** `make pipeline STAGE=acquire` and `STAGE=validate` run for Tübingen; report lists
cells, residents (scored / outside boundary), facilities per category, stops, reference weekday,
runtime and peak memory per stage; second `acquire` run skips downloads.

*Interim:* full acquire; validation with the core checks; test-clip script may follow later.

### P3 — tiles + count

| Create | Key functions |
|---|---|
| `config/valhalla.json` | generated once with `valhalla_build_config` from the pinned image, then edited: `tile_extract`, matrix/isochrone limits for our block sizes, `mjolnir.concurrency` and `thor`/`loki` threads = vCPUs, moderate cache |
| `Makefile` `refresh` + `compose.yaml` `valhalla-build` | tiles live in a host bind mount `data/valhalla/` (not a named volume), so the swap is two `mv` on the host; one-shot: `valhalla_build_elevation` (cached in volume) → `valhalla_build_tiles` → `valhalla_build_extract` → `valhalla_tiles.new.tar`; swap: `tiles.tar → tiles.prev.tar`, `new → tiles.tar`; restart `valhalla`; skipped if PBF checksum unchanged; `make refresh` = `pipeline acquire validate` → `pipeline tiles check` → if flag file: `valhalla-build`, swap, `docker compose restart valhalla` → `pipeline tiles verify` → `pipeline count … cleanup` (O19) |
| `stages/tiles.py` | two subcommands: `tiles check` compares the clipped PBF checksum with the last build and writes the flag file; `tiles verify` checks `/status`, one golden route and that the graph carries grades (VF1); writes manifest; never touches Docker (O19) |
| `valhalla/client.py` | async `httpx` client, `asyncio.Semaphore(concurrency)`, retries with backoff on timeouts/5xx, `matrix(sources, targets, costing, options) -> np.ndarray` (seconds, `None` = unreachable) |
| `count.py` | `make_blocks(cells, size_m)`, `prefilter(block, facilities, reach_m)` with reach per O20, `count_block(...)`: one matrix for all categories + stops, split by category via `groupby`, min time per facility id (multi-point facilities) |
| `stages/count.py` | all cells × categories × profiles → `access_counts.parquet` (`count`, `nearest_min`); stops within 10 min for walking and wheelchair profiles → `transit_supply.parquet` (raw departure sum, O18) |
| `scripts` / `count` diagnostics | **prefilter evidence (O20):** on a sample of blocks (city centre, edge, steep areas) send a **widened** candidate set (reach × 1.5 + 500 m), so facilities the normal prefilter would drop are measured too; report per profile the maximum implied speed (straight-line distance ÷ time) and every facility reachable beyond the nominal reach. Snapping can make walking/wheelchair faster than nominal (snap distance is not counted as time); if any such facility exists, propose a margin (ask first). Cycling: `max_speed_factor` = measured max ÷ 15 km/h (rounded up), then check reach ≤ routing buffer; if not, propose a larger buffer (ask first) |
| `transit.py` | departures per stop on the reference weekday (DuckDB over `stop_times.txt` joined to active `service_id`s) |
| tests | recorded Valhalla matrix responses (`pipeline/tests/fixtures/valhalla/*.json`, replayed with `respx`); block/prefilter tests (no facility within reach dropped); split-by-category; departure counting |
| `tests/integration/test_golden.py` | 3–5 cell → facility pairs with hand-checked times (map measurement ÷ speed, ± tolerance), against local Valhalla on the test clip; marked `integration` |

**Done when:** counts for all cells × categories × profiles exist; departures for walking
and wheelchair profiles; runtime and peak memory of `tiles` and `count` (and Valhalla RSS via `docker stats`)
reported; touched [VERIFY] items resolved (Section 4).

*Interim:* profile `walking_339` and ≥ 3 categories (grocery, pharmacy, school) are enough; the
code is profile/category generic, so the full run is a config change.

### P4 — score + publish + cleanup

| Create | Content |
|---|---|
| `infra/db/roles.sql` | `app_read`, `pipeline_write`, `supervisor_read`, default privileges |
| `infra/db/migrations/0001_meta.sql` … | `meta.runs`, `meta.data_sources`; plain numbered SQL files applied by a small `migrate` command (no new framework) |
| `infra/db/run_schema.sql` | template for `run_<id>`: tables, indexes (GiST on geometries), `scores` / `transit_scores` views, `district_scores` materialized view |
| `stages/score.py` | thresholds from config → `thresholds.parquet`; no derived score tables (§7) |
| `stages/validate_results.py` | report part 2: monotonicity: hard fail only on 5.0 km/h ≥ 3.39 km/h counts (same costing, only speed differs); cycling ≥ walking and wheelchair ≤ walking 3.39 are reported as share of violating cells with a tolerance (costings differ, so no guarantee); totals (residents in classes = scored residents), sample checks, fail → no publish. *Changed in P4 (Juju, 4 Nov 2026):* 5.0 ≥ 3.39 is not guaranteed either (Valhalla routes by cost, N6), so it fails only above a share of violating cells (`validation.results.monotonic`) |
| `stages/publish.py` | `COPY` into new schema `run_<id>` in one transaction, then `CREATE OR REPLACE VIEW current.*` in one transaction; `meta.runs` status; failure webhook if `FAILURE_WEBHOOK_URL` is set |
| `stages/cleanup.py` | keep last 3 published runs (schemas, `data/raw/<run_id>/` and `data/runs/<run_id>/`) |
| tests | SQL contract test against a disposable PostGIS (`integration` marker, also run in CI as a service container if Q4/infra allows), scores view against hand-computed classes/deficits |

**Done when:** `make pipeline` publishes a run; `current.scores` returns classes/deficits that
match hand computation for sample cells; re-publishing switches `current` atomically; only 3 runs remain.

*Interim:* `scores` + `district_scores`, roles, publish; cleanup and report part 2 minimal.

### P5 — API

| Create | Content |
|---|---|
| `api/src/reach_api/{main.py, settings.py, db.py, valhalla.py, cache.py, ratelimit.py}` | connection pool on `app_read` (`psycopg[pool]`, dependency asked first; fallback one connection per request); pydantic-settings; small in-process LRU per (cell, profile); token-bucket rate limit per client IP (no new dependency) |
| `routes/read.py` | `GET /api/meta`, `/api/districts`, `/api/districts/{id}/scores`, `/api/cells?category=&profile=` (GeoJSON, `ST_Transform(…, 4326)`), `/api/recommendations` (empty until P7) |
| `routes/live.py` | `POST /api/inspect` (cell lookup → precomputed values + one isochrone call with 5/10/15 contours + routes to nearest facility per category, from the cell origin), `POST /api/catchment`, `POST /api/expansion`; boundary check before any Valhalla call |
| `infra/api.Dockerfile` | `uv sync --frozen --no-dev --package api` |
| tests | `TestClient` with fake DB layer and `respx`-mocked Valhalla; boundary rejection; cache hit avoids second call; rate limit; GeoJSON shape |

**Done when:** all endpoints respond on the local stack; `curl` examples in the PR; tests pass.
*Interim:* read endpoints + `inspect`; `catchment`/`expansion` after the interim.
*Changed in P5 (Rico, 5 Nov 2026):* full depth; extra module `deps.py` (shared state, run
context); `infra/api.Dockerfile` installs package `reach-api`; `.dockerignore` and `make up --build`
added with it; boundary check and inspector snapping per architecture v0.14 (K1, K2).

### P6 — Web

`web/` (Vite + React + TypeScript + MapLibre, npm, own lockfile, `web/AGENTS.md`): category and
profile selector, class map from `/api/cells`, district statistics panel, pin-drop inspector,
data & validation page with attribution (OSM, GTFS, Zensus, basemap). Basemap: a free style that
needs no key (decided in P6, licence checked). Caddy serves `web/dist` and proxies `/api`.
**Done when:** `npm run lint && npm run build` pass; `make up` + browser shows the map with real
data; screenshot in the PR. *Interim:* map + selector + inspector + attribution.

### P7 — Recommender and validation

`recommend.py` (candidates per methodology §5, land-use filter, block catchments §6.5 rule 7,
greedy with marginal gain ΔW, ranked zones), `recommendations` table; experiments V1–V9 as
scripted analyses under `pipeline/src/reach_pipeline/experiments/` producing a Markdown/HTML
report (`docs/validation_report.md` or the app page); V4 needs an MILP solver (dependency, ask).

### P8 — Production

`compose.prod.yaml` (GHCR images, no published DB/Valhalla ports), Caddy HTTPS via `sslip.io`,
CI job building `linux/amd64` images tagged with git SHA, `make deploy`, systemd service + timer calling `make refresh`
(Monday 03:00 UTC, `flock`), nightly `pg_dump`, failure webhook, server setup script, firewall
notes. Measure memory on the CX23 (Section 4).

### Dependencies expected per phase (each asked before adding)

| Phase | Candidate | Why |
|---|---|---|
| P1 | none (pydantic, pyyaml already present) | — |
| P2 | `osmium-tool` CLI (system binary: Homebrew locally, apt in the pipeline image) | clip/filter/export PBF by streaming |
| P2 | DuckDB `spatial` extension? | only if needed; must be installed in the image at build time, not downloaded at runtime |
| P5 | `psycopg[pool]` (extra of the existing psycopg) | connection pool; cache and rate limit hand-written |
| P6 | `maplibre-gl`, `react`, `vite`, `typescript` (npm) | stack from AGENTS.md |
| P7 | `pulp` (CBC) | V4 exact comparison |

## 3. Proposed data contract (`docs/data_contract.md`)

Names and key columns only; details (types, nullability, units) in P1. Geometries in EPSG:25832.

**Schema `meta`**

| Table | Key columns |
|---|---|
| `runs` | `run_id` PK, `started_at`, `finished_at`, `status`, `osm_snapshot`, `gtfs_valid_from/to`, `reference_weekday`, `config_hash` |
| `data_sources` | `run_id`, `source`, `url`, `retrieved_at`, `checksum`, `licence` |

**Schema `run_<id>`** (and `current.*` views with the same names)

| Table / view | Grain | Key columns |
|---|---|---|
| `cells` | scored cell | `cell_id` (3035 id) PK, `population`, `district_id`, `geom`, `origin_geom` |
| `districts` *(new, gap G1)* | district | `district_id`, `name`, `admin_level`, `geom` |
| `urban_boundary` *(new, gap G1)* | part | `part_id`, `name`, `geom` |
| `facilities` | facility | `facility_id` (`n123`/`w456`/`r789`), `category`, `name`, `geom` |
| `stops` | GTFS stop | `stop_id`, `name`, `weekday_departures`, `geom` |
| `profiles` *(new, gap G2)* | profile | `profile_id`, `costing`, `costing_options` (jsonb), `time_budget_min` |
| `access_counts` | cell × category × profile | `cell_id`, `category`, `profile_id`, `count`, `nearest_min` |
| `facility_points` *(new)* | routing point of a facility | `facility_id`, `point_id`, `kind` (`node`, `representative`, `access`), `geom` |
| `transit_supply` *(O18)* | cell × walking/wheelchair profile | `cell_id`, `profile_id`, `departures` (raw sum), `stops_count`, `nearest_stop_min` |
| `thresholds` | category / transit class | `category`, `k`, `class`, `lower`, `upper` |
| `scores` (view) | cell × category × profile | `class`, `deficit` |
| `transit_scores` (view, O18) | cell × profile | `class` (lack/insufficient/medium/high) |
| `district_scores` (mat. view) | district × category × profile | `share_lack`, `share_insufficient`, `share_sufficient`, `deficit_sum`, `residents_lack` |
| `recommendations` | candidate × category × profile | `rank`, `population_gain`, `geom` |
| `validation_report` | check | `check`, `stage`, `status`, `value`, `message` |

**Files** (`data/runs/<run_id>/<stage>/`): GeoParquet layers with the same columns as the tables
above, `manifest.json` (stage, run_id, inputs[path, checksum], outputs[path, rows], runtime_s,
peak_rss_mb, status, started_at, finished_at), validation reports (JSON + Markdown).

## 4. Risks and [VERIFY] items

### [VERIFY] items from `architecture.md`

| # | Item (arch. line) | How it will be tested | Phase |
|---|---|---|---|
| VF1 | Slopes change walking times (gate G1, §6.1) | Out of Core. In P3 only prove the routing graph carries grades: `trace_attributes` on a steep route returns `edge.weighted_grade` / `max_upward_grade` ≠ 0 (`/height` would only read the raw elevation tiles), plus the asymmetric bicycle times of VF2. G1 itself: route old town → castle and city → Waldhäuser-Ost both directions with default vs. hill-related pedestrian options; compare times | P3 (elevation present), P7 (G1) |
| VF2 | Cycling costing applies elevation (§6.1) | Same steep pair uphill vs. downhill with `bicycle`; asymmetric times = elevation used; repeat with `use_hills` 0 vs. default; record numbers in the PR | P3 |
| VF3 | Memory budget (§11) | Locally: `docker stats` for PostGIS, Valhalla, API during a full count + live calls; pipeline peak RSS from manifests. On the CX23: same plus `free -m` during a weekly run | P3/P4 (local), P8 (server) |
| VF4 | Tile build fits on CX23 with swap (§11.1) | Locally run `valhalla-build` with `--memory 1.5g` (approximating the share left on the server) and measure; then a same-day test server build. Geofabrik updates daily, so the weekly rebuild is effectively unconditional → VF4 is on the critical path for P8 | P3 (local), P8 (server) |
| VF5 | Valhalla via Apptainer on bwUniCluster (§11.1) | Only if a heavy build is needed: `apptainer pull docker://<image>` and build the same tar; compare checksum of outputs/golden times | deferred (not on the critical path) |
| VF6 | Tiles independent of build CPU architecture (§11.1) | Build tiles on arm64 (laptop) and amd64 (CI runner or test server) from the same PBF; golden pairs and 100 random matrix cells must give identical times | P8 (before first release on the server) |

### External facts to check before use (no guessing)

| Fact | Check | Phase |
|---|---|---|
| Official Valhalla image name, tag, multi-arch (arm64 + amd64), included CLI tools | registry manifest (`docker manifest inspect`), image `--help` | P1 |
| PostGIS image with arm64 + amd64 for the same tag | `docker manifest inspect`; fall back to a multi-arch alternative only after asking | P1 |
| Valhalla matrix options: compact output (`verbose: false`), limits keys in `service_limits`, pedestrian `type: wheelchair`, `walking_speed`, `step_penalty`, bicycle `cycling_speed`, `bicycle_type`, `use_hills` | Valhalla API docs for the pinned version + one recorded request each | P3 |
| Geofabrik `.md5` next to the PBF; NVBW naldo GTFS URL and caching headers; Zensus 2022 100 m CSV URL, file name, column names, separators, encoding | `curl -I`, download once, inspect header | P2 |
| `osmium-tool` version and `extract --strategy` behaviour on multipolygons | `osmium --version`, test on the clip | P2 |
| Admin levels of Tübingen districts in OSM | inspect boundaries in the extract | P2 |

### Project risks

| Risk | Mitigation |
|---|---|
| Interim deadline (23 days for P1–P6) | *interim* depth per phase; one profile + 3 categories for the demo; API/web minimal |
| Review latency: six sequential PRs, each needs approval by another member before the next phase starts from `dev` | fixed same-day review slot in the team; if a review is late, the next phase branches from the open PR branch (stacked) and is rebased after the merge |
| Routing buffer likely too small for cycling (4 km leaves 6.7 % headroom over 3.75 km; any factor > 1.067 breaks it) | measured in P3: no facility reachable beyond 0.94 × nominal reach in 25 blocks; implied speed near the budget ≤ 1.01 × 15 km/h; factor 1.05 would still fit the 4 km buffer |
| Valhalla keeps ~0.5–1.4 GB per worker thread after matrix requests (2.8–3.0 GB peak during a full count with 2 threads) | N4: restart after `count` and/or 1 thread on the CX23; decide with VF3 in P8 |
| Matrix limits / runtime for cycling (3.75 km reach → many targets per block) | block size per profile from config; measure in P3; raise limits in `valhalla.json` |
| Prefilter not exact because of snapping and downhill cycling (C1) | configurable margin, tested in P3 |
| PostGIS or Valhalla image lacks arm64 → slow emulation on the Mac | check in P1, ask before switching image |
| OSM incompleteness per category (M1) | counts per category in report part 1; V2 in P7 |
| Elevation download needs network during tile build; CI cannot build elevation for the test clip | test clip tiles built without elevation (C6) |
| 4 GB RAM in production | streaming reads, bounded concurrency, swap, measurement (VF3) |
| osmium memory grows with the highest OSM node ID (~13.9 billion → ~1.7 GB per ID bitmap), not with the file: `extract -s smart` peaks at 3.9 GB RSS on Linux (2.5 GB on macOS), `tags-filter` at 1.8 GB | measured in P2; options for P8: run `validate` while Valhalla is stopped or before it starts, `-s simple` for the clip (~1.9 GB), more swap; decide with VF3 on the CX23 |

## 5. Conflicts, gaps and ambiguities

| # | Finding | Where | Recommended resolution |
|---|---|---|---|
| C1 | The straight-line prefilter is called **exact**, but (a) Valhalla snaps origin and target to the network and does not count the snap distance as travel time, so two snapped points can be closer than the raw points; (b) bicycle costing can be faster than 15 km/h downhill and on good surfaces | arch. §6.3, §6.5 rule 3; methodology §1 | **Resolved (Q3 → O20):** factor 1.0 + margin 0 for walking/wheelchair, cycling factor measured in P3, buffer check |
| C2 | The pipeline container runs `tiles`, but starting `valhalla-build` and restarting `valhalla` from inside a container needs the Docker socket (security and complexity) | arch. §7, §11 | **Resolved (Q2 → O19):** `make refresh` on the host; no Docker socket |
| C3 | Transit supply has no place in the table list: `access_counts` has `count`, `nearest_min`, but $S_i$ (sum of departures) and the 4 transit classes need their own columns | arch. §8, methodology §3 | **Resolved (Q1 → O18):** `transit_supply` table + `transit_scores` view |
| C4 | Parks, playgrounds and schools are often large polygons; one representative point inside a large park undercounts access | methodology §2 | **Resolved (Q5 → methodology v0.2 §2):** access points, 50 m fallback, max N per park, counted once with min time |
| C5 | "Walking profiles only" for transit vs. the reach table that also lists wheelchair stops (565 m) | methodology §3 vs. arch. §6.1 | **Resolved with Q1:** walking 3.39, walking 5.0 and wheelchair; methodology v0.2 §3 |
| C6 | Tiles are "always built with elevation", but the CI/test clip cannot download elevation (network, size) | arch. §6.1 vs. AGENTS tests | **Confirmed:** Test clip tiles without elevation via `config/test_clip.yaml`; production always with elevation |
| C7 | School holidays for the reference weekday need a data source; a public holiday API at runtime is not allowed and a `holidays` package does not cover school holidays | arch. §6.3 | **Confirmed:** List BW public and school holidays for the feed period in `config/config.yaml` (source: Kultusministerium BW), validated to cover the feed's validity window |
| C8 | Districts at admin levels 9–11 overlap; `cells.district_id` needs one level | arch. §5.2 | **Resolved (P2):** list `districts.admin_levels: [9, 11]` (9 = Teilorte, 11 = core-town districts; 10 overlaps 11), `validate` checks gaps and overlaps against the city area (Rico, 2 Nov 2026) |
| C9 | API needs the urban boundary (live check), districts and the profile costing for live isochrones; none of these are DB tables in §8 | arch. §8, §9 | **Confirmed:** Add `urban_boundary`, `districts`, `profiles` and `facility_points` (access points from Q5, needed for live routes to the nearest point) tables to the run schema (gaps G1/G2 in Section 3), so live answers use exactly the published run's costing |
| C10 | Changing thresholds "never requires re-routing", but only `publish` writes to PostGIS and thresholds are copied per run | arch. §6.3, §8 | **Confirmed:** `count` is cached by (PBF checksum, cells/facilities checksum, profile config hash); a threshold change re-runs the pipeline as a new run that reuses cached counts, so no re-routing happens |
| C11 | Stage names differ: AGENTS lists 7 stages, arch. §7 lists 9 (incl. "validate results", "cleanup"); `make pipeline STAGE=validate` is ambiguous | AGENTS, arch. §7 | **Confirmed:** CLI names `acquire, validate, tiles, count, score, recommend, validate_results, publish, cleanup`; `validate` = inputs |
| C12 | Cells outside the urban boundary: stored or not? | arch. §4, §8 | **Confirmed:** `cells` holds only scored cells; outside residents appear as totals in the validation report |
| C13 | P0 forbids changing other docs, but AGENTS asks to keep `README.md` (documentation table) and `CHANGELOG.md` true | AGENTS vs. P0 task | **Resolved:** README documentation table and CHANGELOG updated in this PR (#17) |
| C14 | No owners in `CODEOWNERS` yet (T2 due 4 Nov); P1 touches `pipeline`, `api`, `config`, `infra`, `.github` → "ask first" for multi-folder changes | AGENTS boundaries | **Resolved (Q4):** confirmed phase plan = approval for its folders; CODEOWNERS all three |

## 6. Questions and answers

| # | Question | Answer (Rico, 2 Nov 2026) |
|---|---|---|
| Q1 | Transit storage | Yes: only `transit_supply` (raw departure sum, cell × profile, walking and wheelchair profiles) as table; `transit_scores` as view over `transit_supply` + `thresholds` (rule 5). Architecture v0.11, O18 |
| Q2 | Tile build orchestration | Yes, on the host: one command (`make refresh`) builds tiles, swaps them atomically, restarts Valhalla and runs the pipeline; the systemd timer calls exactly this command; no Docker socket in the pipeline container. Architecture §7/§11, O19 |
| Q3 | Prefilter margin | Yes: `prefilter_margin_m` = 0 for walking/wheelchair (exact while elevation is ignored; only raised if P3 shows Valhalla faster than nominal); cycling factor from measured maximum speeds in P3; check routing buffer ≥ largest reach incl. factor, propose a larger buffer if needed. O20 |
| Q4 | Folder approval, CODEOWNERS | A confirmed phase plan approves the folders it names; deviations from the plan and changes to `architecture.md`/`methodology.md` stay "ask first". CODEOWNERS for P1: RicoS03, konstantinholl, nicholas-tuebi for all folders until T2 |
| Q5 | Parks | Yes for parks and playgrounds: access points = intersections of ways with the park boundary, fallback points every 50 m along the boundary, at most N points per park (config); counted once if any access point is reachable, time = minimum. All other polygons: representative point. Methodology v0.2 §2 |

Confirmed by Rico (2 Nov 2026): C6–C12 as recommended in Section 5; Q4 also covers `compose*.yaml`, `infra/`, CI workflows, the data contract and repository structure **as far as they are named in a confirmed phase plan** (recorded in `AGENTS.md`, PR #18); walking/wheelchair margin wording "exact up to the snap distance, margin 0 until P3 evidence" (arch. §6.3).

## 7. Decisions made, deviations agreed, measured numbers

| Date | Item | Result |
|---|---|---|
| 2026-11-02 | Defaults from the start prompt | O17 option (a); M1 table as config defaults; O14 webhook optional, no-op if unset; O16 local demo |
| 2026-11-02 | Q1–Q5 | Applied: architecture v0.11 (O18–O20), methodology v0.2 (§2 facility locations, §3 profiles) |
| 2026-11-02 | Branch names | `<type>/<name>-<topic>` (PR #18) |
| 2026-11-02 | C6–C12, Q4 scope, margin wording | Confirmed as recommended; P0 closed |
| 2026-11-02 | P1 PostGIS image | `postgis/postgis` has no arm64 build → `imresamu/postgis:18-3.6` (multi-arch build of the official image) locally and in production (confirmed by Rico) |
| 2026-11-02 | P1 Valhalla in `make up` | Deviation: `valhalla` sits behind Compose profile `routing` until P3 provides `config/valhalla.json` and tiles; P3 removes the profile (confirmed) |
| 2026-11-02 | P1 placeholders | API: `reach_api/main.py` with `GET /api/health`, run in the official uv image with bind mount and `--reload` (no Dockerfile until P5); Caddy: `infra/Caddyfile` + `infra/web-placeholder/` proxying `/api` (confirmed) |
| 2026-11-02 | P1 pins | `ghcr.io/valhalla/valhalla:3.9.1`, `imresamu/postgis:18-3.6`, `caddy:2.11.7-alpine`, `ghcr.io/astral-sh/uv:0.13.6-python3.12-trixie-slim` (all amd64 + arm64, checked with `docker manifest inspect`); CI `actions/checkout@v7.0.1`, `astral-sh/setup-uv@v10.3.3` with uv 0.13.6 |
| 2026-11-02 | P1 assumptions | `make pipeline` runs on the host with uv; Compose `pipeline` uses the uv image until osmium needs an own image (P2/P8). Ports bind to 127.0.0.1 on the default network ("internal" = not public; Docker `internal: true` networks cannot publish ports). City boundary selected by `admin_level` 8 + AGS `08416041` instead of a relation id (the id found, 167128, returns HTTP 410). New values: `min_part_area_m2` 10,000, `access_points.max_points` 20, `population_tolerance_pct` 5, cycling `max_speed_factor` 1.0 (provisional, O20), test clip bbox approximate. Speed only in `speed_kmh` (Valhalla `walking_speed`/`cycling_speed` set by the client), so `profiles` in the data contract gets `speed_kmh`. `extends:` key for `test_clip.yaml`. Single stage without `--run-id` reuses the latest run. Exceptions in `errors.py` (module not named in the plan) |

| 2026-11-02 | P2 answers (Rico) | `osmium-tool` as system requirement (Homebrew 1.19.1 locally, apt in CI, pipeline image by P8), no DuckDB `spatial`; OSM read as `tags-filter` → `export` GeoJSONSeq → GeoPandas. `districts.admin_levels` list with coverage check. Holidays as static config data (Kultusministerium BW, school years 2026/27 and 2027/28). `hello` removed; planned stages fail clearly (single) or are logged as skipped (`run`) |
| 2026-11-02 | P2 values | `validation.official_population` 90,499 (Zensus 2022, Destatis via citypopulation.de); `districts.admin_levels` [9, 11]; `reference_day.covered` 2026-07-30..2028-06-17; Zensus columns `GITTER_ID_100m;x_mp_100m;y_mp_100m;Einwohner` (`;`, ASCII, 3,088,037 rows); naldo feed valid 2026-07-12..2026-12-12 with `calendar.txt`, `calendar_dates.txt`, `feed_info.txt`; Geofabrik `.md5` exists, `latest` redirects (307) to a dated file; NVBW sends only `Last-Modified`, Destatis `ETag` + `Last-Modified`, both answer 304 |
| 2026-11-02 | P2 assumptions | The OSM processing (pass 1, urban boundary, `extract`, facilities) runs in `validate`, not `acquire`: `acquire` only downloads and unpacks raw files (arch. §7 table), `validate` writes `routing.osm.pbf` for `tiles`. Districts come from pass 1 (complete boundaries), not from the clipped PBF. `acquire` as first stage starts a new run without `--run-id`. Reference weekday = first Tuesday on or after the run date (past days may already be cut from the feed). `extract` strategy `smart`. Dedupe: node + area with the same tag → point categories keep the node, access-point categories the area. Facilities and stops are kept inside the routing area. Test clip: `official_population: null` (warning). New keys `download`, `sources.*.members`, `access_points.walkable_highways`, `districts.coverage_tolerance_pct` (0.5 %) |
| 2026-11-02 | P2 finding | 8.0 % of residents outside the urban boundary, mostly in the core town (N3) |
| 2026-11-02 | P2 review (fresh agent) | Fixed: `unpack` wrote into hard-linked members of the previous run (now `.part` + replace, test); access-point cap now evenly spaced around the closed ring; `acquire` re-runs if its outputs are missing; `read_stops` checks columns, optional `location_type`, invalid coordinates; routing points outside the routing area dropped; CRS check covers `origin_geom`; new caching headers kept on SHA-256 reuse; empty `.md5` → clear error; unit tests for `validate.checks()`; plan/README/contract fixes. Left open (listed in PR): Geofabrik md5 race not retried; `feed_info.txt` required in config although optional in GTFS; `members[0]` not validated; `EXTRACT_STRATEGY`/`_SAME_POINT_M` constants not in config; dedupe only matches identical tags (childcare node in kindergarten area counts twice) |
| 2026-11-02 | N3 decision (Rico) | Scoring scope = populated cells with centre inside the city boundary; coverage check `validation.min_scored_share` 0.98 (base: all populated cells touching the city; excluded residents per district by largest overlap); routing area = city + 4 km; urban boundary (land use + `education`, `institutional`, `religious`, `closing_m` 100; `industrial` excluded because it joins Teilorte) only for map, live check, recommender candidates. Architecture v0.12, methodology v0.3, glossary, data contract v0.3. Test clip: `min_scored_share` 0 (the clip box cuts through cells) |

| 2026-11-03 | P3 branch | `feature/juju-tiles-count` (driven by Juju, AGENTS.md branch rule) instead of `feature/rico-tiles-count` |
| 2026-11-03 | P3 assumptions | `config/valhalla.json` = `valhalla_build_config` 3.9.1 output with paths under `/data/valhalla`, then edited: `mjolnir.concurrency` 2, `max_cache_size` 256 MB, `use_admin_db` false (the clipped PBF has no complete country boundaries; country access overrides not applied, Germany ≈ OSM defaults), pedestrian/bicycle `max_matrix_location_pairs` 25,000; service with 2 worker threads (`compose.yaml`). `valhalla-build` mounts `<data_dir>/valhalla/build` as `/data/valhalla`, so the same config builds next to the live tiles; elevation tiles (`-b` routing-area bbox) cached in `<data_dir>/valhalla/elevation`; test clip blanks `additional_data.elevation` in a temp copy. Tile directory = `<data_dir>/valhalla` (`VALHALLA_DIR`, set by `make`). Rebuild fingerprint = SHA-256 over PBF + `valhalla.json` + elevation flag, recorded in `tiles_source.sha256` after a successful swap and restart. `tiles check` writes no manifest; `run`/`make pipeline` runs `tiles verify`, which fails if Valhalla serves another tile set (mtime vs. `/status` `tileset_last_modified`) and only warns if the tiles were built from another run's PBF. `make refresh` without a rebuild runs `docker compose up -d --wait valhalla` (no restart if unchanged). `nearest_min` only up to the budget (exactness of the prefilter); departures = stop events of active trips without `pickup_type` 1; reference weekday from `validate`'s report. Matrix times as NaN (plan: None). Integration tests deselected by default (`-m 'not integration'`). Count caching across runs (C10) not implemented yet: `count` is a no-op only within a run |
| 2026-11-03 | P3 finding (VF1/VF2, G1) | With elevation in the tiles, default `pedestrian` times depend on slopes (Marktplatz → Schloss 681 s up / 619 s down at 3.39 km/h, flat 537 s; Hbf → Waldhäuser-Ost 3,950 / 3,335 s); `use_hills` 0/default/1 does not change them. Bicycle asymmetric as expected (677/591 s; 1,196/865 s); `use_hills` 0 = default. Conflicts with arch. §6.1/O7 ("ignored for now") → N5, decision open |
| 2026-11-03 | P3 finding (O20) | Prefilter evidence: no reachable facility beyond the prefilter reach for any profile (4 sample blocks per run; 25-block experiment for walking 3.39 and cycling). Implied speed ÷ profile speed is high only for short pairs (snap distance not counted: up to 5–6 for < 60 s, 1.41 for cycling at 60–180 s) and ≤ 1.017 (walking) / 1.008 (cycling) for 600–900 s. Walking/wheelchair margin stays 0 (O20). Cycling factor: proposal open (keep 1.0 or 1.05, ask first) |
| 2026-11-03 | P3 finding (VF3) | Valhalla memory grows per worker thread and is not released (N4) |

| 2026-11-04 | P4 branch and base | `feature/juju-score-publish` (Juju drives), stacked on `feature/juju-tiles-count` because P3 (#21) is not merged yet; rebase onto `dev` after the merge (Juju) |
| 2026-11-04 | P4 answers (Juju) | Full depth (real `cleanup`, full report part 2); `DATABASE_URL_ADMIN` in `.env` for `migrate` (`make migrate`, and first step of `publish` when set); PostGIS data-contract test as CI job `db-contract` with a service container, documented |
| 2026-11-04 | P4 deviation (Juju) | Monotonicity 5.0 ≥ 3.39 km/h fails 6 of 1,699 cells on real data (steps avoided at higher speed, N6) → tolerance check instead of hard fail: warn > 0, fail > 1 % of cells; cycling ≥ walking 3.39 and walking 3.39 ≥ wheelchair warn > 5 %, never fail |
| 2026-11-04 | P4 assumptions | `migrate` = CLI command (`python -m reach_pipeline migrate`), not a stage; `roles.sql` re-applied every time, migrations once (`meta.schema_migrations`, new table in the contract); role passwords only set when their `*_PASSWORD` variable is present. Privileges: `app_read` reads `current.*` and `meta` only (view-owner rights cover the run tables), `supervisor_read` every run schema via default privileges, `pipeline_write` owns `current` and the run schemas. `current` views `SELECT *`; current run found via `pg_depend` of `current.cells`. Re-publishing the current run: load + switch in one transaction (the `DROP SCHEMA … CASCADE` would otherwise drop the views first). `meta.runs` row upserted as `running` before the load; `failed` on a DB error unless already published. `profiles.costing_options` = the options as sent to Valhalla (incl. speed). Districts/urban boundary forced to MultiPolygon. Failure webhook in the CLI for every stage (not only `publish`, arch. §11 "a failed run posts"), body `{"text": …}`. `cleanup`: deletes runs older than the oldest kept published run (schemas, `meta.runs` rows, `data/raw/<id>/`, `data/runs/<id>/`), never the current run or newer unpublished runs; nothing with ≤ 3 published runs. Report part 2 sample cells = nearest cells to `count.evidence.sample_points`. `make` passes `.env` via `uv run --env-file` |
| 2026-11-04 | P4 conflict (reported) | AGENTS.md rule 6 "only `publish` writes to PostGIS" vs. arch. §7: `cleanup` drops old run schemas → implemented as in the architecture; AGENTS.md wording to be aligned (ask); **resolved 5 Nov 2026 (Rico):** rule 6 now names `cleanup` |
| 2026-11-05 | P3/P4 review and merge (Rico) | Reviewed and run locally (lint, unit, `-m db`, `-m integration` on the clip tiles, `make refresh`), approved; #21 merged, #22 retargeted to `dev` (no rebase needed: the P3 commits were unchanged) and merged |
| 2026-11-05 | P5 answers (Rico) | Full depth (if not done by 12 Nov: shorten `catchment`/`expansion` so P6 stays on time); dependencies `psycopg[binary,pool]` (psycopg-pool 3.3.3), `pyyaml` 6.0.3 (api), `httpx2` 2.16.0 (dev), no other upgrades; K1 accepted: live point allowed inside urban boundary + margin **or** a scored cell (86 scored cells, 1,144 residents lie outside boundary + 100 m); K2 (a): one live matrix origin → facility points within the count prefilter, same costing, differences only logged; (b) → notes N7; K3 (a): `api` section in `config/config.yaml`, `.env` only URLs, DSN, `REACH_CONFIG`; Dockerfile and compose change approved. Changed assumptions: unpopulated clicks snap to the centre of their 100 m grid cell (id from EPSG:3035) and are cached like scored cells; `X-Forwarded-For` only from Caddy (trusted proxy), API port not published, test; `/api/cells` with 6 decimals, gzip in Caddy, ETag/cache per run id. Architecture v0.14 (§6.5 rules 8 and 12, §9) |
| 2026-11-05 | P5 assumptions | Pipeline `Config` keeps `api` as an unvalidated mapping (its models forbid unknown keys); ~~changing `api` values therefore changes the config checksum and re-runs `count`~~ — fixed before the merge: each stage hashes only the config sections it uses (`CONFIG_SECTIONS`, manifest input `config:<sections>`), `api` belongs to none; `meta.runs.config_hash` covers all sections except `api`. API reads its own view of the config (`extends` merged like the pipeline): `api`, category names, `max_speed_factor`/`prefilter_margin_m`, `valhalla.max_matrix_pairs`; speed, budget and costing options from `current.profiles`. Current run = run schema behind `current.cells` (as `publish`), one query per request; profiles/categories cached per run id. Grid id = `CRS3035RES100mN<north>E<east>` of the lower-left corner (checked against `current.cells`), origin = centre. Prefilter around the single origin (the pipeline uses the block bbox, a superset). Weakest category = worst class, then largest deficit; null if all sufficient. Routes only to nearest facilities within the budget. Catchment: reverse isochrone from the facility point; matrix sources = scored cells within the prefilter reach of any routing point; `residents_by_class` for the facility's categories. Expansion = Valhalla `action: isochrone`, budget = profile budget, own small LRU. Rate limit only on live endpoints, cache hits cost a token; client IP = last `X-Forwarded-For` entry from a trusted peer; Caddy resolved by name, re-resolved at most every 30 s. ETag `W/"<run_id>:…"` + `Cache-Control: no-cache` on all read endpoints; `/api/recommendations` returns an empty collection with `available: false` (no table yet). Errors 422 (outside, unknown values, no street near the point), 429, 502, 503. HEAD is not served. Category names from the config, not the run |
| 2026-11-05 | P5 finding (N8) | Live counts differ from precomputed ones in 24 of 960 cell × category pairs (2.5 %, always ±1; 40 random cells × 4 profiles): Valhalla `select_optimal` answers one-source matrices with `timedistancematrix` and block matrices with `costmatrix`, which differ near the budget (example: 463 s vs. unreachable). Logged only, as agreed |
| 2026-11-05 | P5 before merge (Rico) | (1) Config digest per stage: `CONFIG_SECTIONS` per stage module, manifest input `config:<sections>` instead of the config files, `require_ok` recomputes it; `publish` uses all pipeline sections; `api` triggers no stage (tests). One-time effect: manifests of earlier runs list the config files, so after this change the first run of each stage re-runs. Changes to unused sections (e.g. `cleanup`) no longer re-run `count`; a change in a used section still does (C10 caching across runs stays open). (2) `inspect` shows the precomputed count for scored cells (`count`, `count_source`), the live matrix only lists facilities; differences logged (N8). (3) HEAD on every GET endpoint |
| 2026-11-05 | N8 decision (Rico, after PR #24) | Variant C: `costmatrix` fixed in `config/valhalla.json` (only settable there in 3.9.1); `count` writes `reachable` (cell × profile × facility within the budget, `time_s` smallint), the inspector reads it for scored cells; live matrix only for grid cells without residents and catchments, own client `api.live_matrix` (timeout 10 s, concurrency 1, no retry), `source: live`, 504 on timeout. Architecture v0.15, data contract v0.7, N7/N8 settled. Branch `fix/rico-matrix-algorithm` (AGENTS.md name rule instead of `fix/matrix-algorithm`) |
| 2026-11-05 | N8 assumptions | `reachable` without primary key: the key index would take 55 MB per run, the deduplicated (`cell_id`, `profile_id`) index 4–6 MB; uniqueness is guaranteed by `count` and checked by `reachable_matches_counts` (fail). Route line of a listed facility goes to its routing point nearest to the origin by straight line (display only; the time is the run's matrix time). Catchments keep a live matrix (cells → facility); reading them from `reachable` is possible later. `matrix_vs_route` samples 25 pairs per profile (80 % near the budget), seed from the run id, warns above 60 s, never fails; needs the running Valhalla in `validate_results` (`valhalla` added to its config sections). Methodology not changed (proposal in the PR) |
| 2026-11-05 | P5 review (fresh agent) | Fixed: live caches held Python dicts (~10× the JSON size; 2,000 cycling inspects ≈ 1 GB) → caches hold serialized JSON bytes, defaults lowered (`live_entries` 500, `expansion_entries` 10; worst case ~60 MB) and size comments corrected; rate-limit dependency was sync (threadpool, unlocked limiter state) → async; concurrent misses of one key now share one Valhalla computation (rule 10); `rank_share_lack` ranked districts without residents first → `NULLS LAST`; Valhalla retries now wait `api.valhalla.backoff_s * 2**attempt` (new key); matrix larger than the limit on both axes raises; meta ETag includes the config category names; unit tests no longer resolve DNS; db test covers a scored cell with a real grid id outside the urban boundary (K1) and snapping; contract lists 500/502 causes; commits reordered (code with its contract, `chore` types). Left: none |

Measured numbers (runtime, peak memory, counts) are added here at the end of every phase.

| Phase | Measurement (MacBook arm64, Docker 29.9.2) | Value |
|---|---|---|
| P1 | `make up` (images pulled, warm uv cache) until db, api, caddy healthy | 11 s |
| P1 | Idle memory (`docker stats`): db / api (uvicorn `--reload` + uv) / caddy | 34 MB / 366 MB / 17 MB |
| P1 | `make pipeline STAGE=hello`: runtime / peak RSS | < 0.01 s / 33.5 MB |
| P1 | `uv run pytest` | 31 passed in < 1 s |
| P2 | `acquire`, first download (350 MB): runtime / peak RSS | 99 s / 137 MB |
| P2 | `acquire`, unchanged sources (md5, 304, 304; hard links) | 0.5 s / 143 MB |
| P2 | `validate` (Tübingen, city scope): runtime / peak RSS (osmium child) | 10 s / 2,173–2,601 MB |
| P2 | `validate` steps: pass 1 / boundaries / extract / facilities / Zensus / GTFS | 3.4 / 0.2 / 1.5 / 3.3 / 0.1 / 0.2 s |
| P2 | osmium peak RSS on Linux (Debian, osmium 1.18): `extract -s smart` / `tags-filter` | 3,991 MB / 1,842 MB |
| P2 | Results before N3 (urban-boundary scope): scored cells / residents scored / outside | 1,325 / 83,123 / 7,232 |
| P2 | Results after N3 (city scope): scored cells / residents scored / coverage base / excluded | 1,699 / 90,355 (official 90,499, −0.16 %) / 90,443 / 88 (99.90 %; Unterjesingen 73, Lustnau-Zentrum 11, Weilheim 4) |
| P2 | Urban boundary parts / area; routing area; districts | 12 / 16.6 km² (scored residents outside it: 4,974); 345.6 km² (was 240.8); 31 (gap 0 %, overlap 0 %) |
| P2 | Facilities in routing area (city + 4 km): grocery / pharmacy / doctors / childcare / school / parks; routing points | 60 / 30 / 164 / 176 / 71 / 434; 1,529 (points inside the routing area only) |
| P2 | Stops in routing area (city + 4 km); reference weekday; active services | 907 (720 around the urban boundary); 2026-11-03; 470 |
| P2 | Test clip (`config/test_clip.yaml`): scored cells / residents / validate runtime | 67 / 6,848 in the clip / 7.8 s |
| P2 | `uv run pytest` | 93 passed in ~3 s (after review fixes) |
| P3 | Tile build Tübingen (routing area 346 km², PBF 10.6 MB) with elevation, `--memory 1.5g`: first build incl. elevation download (2 SRTM tiles, 20 MB) / rebuild (cached elevation) | 15.6 s / 6 s; peak 234–236 MB (cgroup); `valhalla_tiles.tar` 12 MB (VF4 local) |
| P3 | Tile build test clip (no elevation) | 5 s, 124 MB |
| P3 | `tiles verify` | 0.2 s, 135 MB; golden route 506 m (straight 474 m), max grade 11.7 % |
| P3 | `count` Tübingen, 4 profiles × 6 categories, 1,699 cells, 161 blocks of 500 m: runtime / pipeline peak RSS | 195–204 s / 286–289 MB; 628 matrix requests |
| P3 | `count` per profile: runtime / pairs / targets per block (max, median) | walking 3.39: 11.5 s / 246k / 476, 49 · walking 5.0: 22.6 s / 420k / 622, 110 · cycling: 123.6 s / 1.23 M / 970, 754 · wheelchair: 12.4 s / 246k / 476, 49 |
| P3 | `count` test clip (67 cells, 6 blocks) | 39 s / 279 MB |
| P3 | Departures (DuckDB over `stop_times.txt`, 67 MB) on 2026-11-03 | 0.1 s; 470 services; 6,272 stops with departures |
| P3 | Valhalla memory (`docker stats`): idle / during full count (2 threads) / after | 54 MB / 2.8–3.0 GB peak / 2.2 GB (1 thread: 1.4 GB peak, cycling 216 s; N4) |
| P3 | Other services idle (`docker stats`): db / api / caddy | 32 MB / 482 MB / 18 MB |
| P3 | Results (walking 3.39): residents with ≥ 1 facility within 15 min — grocery / pharmacy / doctors / childcare / school / parks | 67 % / 57 % / 83 % / 94 % / 71 % / 98 %; transit: 1.3 % of residents without departures within 10 min (median 364 departures per cell) |
| P3 | `uv run pytest` (macOS and Linux container) | 132 passed; `uv run pytest -m integration` on the clip tiles: 5 passed (1 of 5 fails on the Tübingen tiles with elevation, N5) |
| P4 | `make pipeline` (new run `20261104T202436Z`, all stages, count recomputed): total | 3 min 46 s; acquire 4.3 s, validate 8.0 s, tiles verify 0.04 s, count 211 s, score < 0.01 s, validate_results 0.14 s, publish 0.89 s, cleanup 0.01 s |
| P4 | `publish` alone (re-publish of the current run): runtime / peak RSS | 0.89 s / 185 MB; 40,776 access rows, 5,097 transit rows, 1,699 cells, 935 facilities, 907 stops |
| P4 | PostGIS: database size with one run / container peak during 4 publishes (`docker stats`) | 31 MB / 200 MB (Valhalla 3.1 GB during count, N4) |
| P4 | Report part 2 (walking 3.39): residents lacking grocery / pharmacy / school | 32.8 % / 42.9 % / 29.1 % (grocery insufficient 26.2 %); monotonicity: 5.0 < 3.39 in 6 cells (0.35 %, warn), wheelchair > walking 3.39 in 107 cells (6.3 %, warn), cycling < walking 3.39 in 0 |
| P4 | Hand check of `current.scores` as `app_read` (7 cells incl. 3 "insufficient", all profiles × categories) | 168 rows, 0 mismatches |
| P4 | Cleanup demo (separate DB `reach_demo`, 4 cloned runs published) | 3 schemas, 3 `meta.runs` rows, 3 run and raw folders left |
| P4 | `uv run pytest` / `uv run pytest -m db` (local PostGIS 18-3.6) | 161 passed / 10 passed (a broken `scores` view fails 4 of them) |
| P4 | Review run on `dev` after the merge (Rico, 5 Nov): `make refresh` without tile rebuild, run `20261105T184022Z`: acquire / validate / count / publish / cleanup | 3.2 s / 24.4 s (2,062 MB) / 289 s (289 MB) / 1.1 s / 0.03 s; `validate_results` 0 fail, 2 warn (N6); `current.scores` 40,776 rows, class and deficit recomputed from raw tables: 0 mismatches |
| P5 | Response times through Caddy (local stack, run `20261105T184022Z`): `/api/cells` grocery walking 3.39, first after restart / cached / 304 | 56 ms / 9 ms / 4 ms; 1,699 features, 680 KB plain, 59 KB gzip (transit 705 / 64 KB) |
| P5 | `/api/districts` / `/api/meta` / district scores | 290 KB (81 KB gzip), 10–41 ms / 3.0 KB, 27 ms / 1.6 KB, 9 ms |
| P5 | `POST /api/inspect` (miss: 1 isochrone + 1 matrix + ≤ 6 routes), Marktplatz walking 3.39 / cycling / cache hit | 180 ms (18.5 KB) / 292 ms (52 KB) / 4 ms; 40 random cells (host): median 36 ms walking 3.39, 55 ms walking 5.0, 200 ms cycling, 37 ms wheelchair, max 248 ms |
| P5 | `POST /api/catchment` (pharmacy, walking 3.39) / `POST /api/expansion` Marktplatz walking / cycling | 37 ms, 82 cells, 6,574 residents / 25–30 ms, 3,410 edges, 477 KB (45 KB gzip) / 73 ms, 9,714 edges, 1.37 MB |
| P5 | Rejected point (outside boundary) | 2–3 ms, no Valhalla call |
| P5 | API memory (`docker stats`): dev (`--reload`) idle / after load; image CMD idle / after 24 cell bodies + 3 cycling expansions + 4 cycling inspects | 78 / 101 MB; 51 / 111 MB with Python objects in the live caches, **82 MB** after the review fix (serialized bodies) (P1–P4 with `uv run` in the uv image: 366–482 MB idle). Image 357 MB |
| P5 | Other services at the same time: db / valhalla / caddy | 96 MB / 2.2 GB (after the earlier count, N4) / 22 MB |
| P5 | `uv run pytest` / `-m db` | 194 passed / 15 passed (API: 35 unit, 5 db; after the review fixes) |
| P5 | Before merge: `make pipeline` with per-stage config digests (new run `20261105T195315Z`, every stage re-ran once because older manifests list the config files) / `count` with a config that only changes `api` | 3 min 46 s (acquire 33 s, validate 9.9 s, count 202 s, publish 1.0 s) / skipped in 0.04 s ("inputs unchanged") |
| P5 | `uv run pytest` / `-m db` before merge | 200 passed / 15 passed; `make up` + curl: 9 endpoints 200, HEAD 200 on all 6 GET endpoints |
| N8 | `count` per algorithm (fresh Valhalla, 2 threads, run `20261105T195315Z`): `select_optimal` / `costmatrix` / `timedistancematrix` | 243 s, 2.6 GB / 279 s, 2.5 GB / 54 s, 195 MB (Valhalla peak); rows differing from `costmatrix`: 28 / – / 975 (616 wheelchair) |
| N8 | Matrix vs. /route, facility decisions where the algorithms disagree (24 pairs + 40 random of 975) | `costmatrix` closer in 58 of 73; `costmatrix` vs. /route mean 53.8 s, median 1 s, max 1,027 s (11 of 73 above 60 s) |
| N8 | After the change: `make refresh` (tile rebuild 259 MB, run `20261105T203046Z`): count / validate_results / publish; Valhalla peak | 264 s (293 MB) / 0.9 s / 7.5 s (6.5 s re-publish); 2.78 GB; final `make pipeline` (run `20261105T203945Z`): count 294 s, publish 6.6 s, `matrix_vs_route` max 1 s |
| N8 | `reachable`: rows (walking 3.39 / 5.0 / cycling / wheelchair) / Parquet / PostGIS heap + index | 552,917 (37,048 / 75,254 / 407,949 / 32,666) / 1.3 MB / 46.2 + 6.2 = 52.4 MB per run, ~157 MB for 3 kept runs (with a primary key: 101.6 MB, ~305 MB) |
| N8 | `matrix_vs_route` in report part 2 (100 random pairs, 80 % near the budget) | mean 0.5 s, max 4.1 s (wheelchair), 0 flips |
| N8 | `inspect` through Caddy, cache miss: scored walking / cycling (n = 5) · unscored (live matrix) walking / cycling (n = 4) | median 44 / 66 ms (max 131 / 82) · 77–388 ms / 2.7–3.0 s |

## 8. Next steps

1. ~~Confirm C6–C12 and the review points~~ — done 2 Nov 2026; P0 closed.
2. ~~P1 scaffold~~ — merged (PR #19).
3. ~~P2~~ — merged (PR #20). Open from P2: decide N3 (urban boundary land-use
   values / closing distance, ask first); `scripts/build_test_clip.py` and the clip bbox
   refinement (interim: may follow later); osmium memory for the CX23 (risk table, VF3); extend
   `reference_day` before 2028-06-17 (the run fails with a clear message otherwise). N3 settled
   (architecture v0.12). P3 must measure the effect of the larger routing area (346 km², 1,699
   cells) on tile build and count runtime.
4. ~~P3~~ — merged (PR #21, 5 Nov 2026). Open from P3: decide the
   cycling `max_speed_factor` (1.0 or 1.05, O20), N4 (Valhalla memory per thread, before P8) and
   N5 (walking times include slopes: architecture/methodology wording, G1); the golden pairs
   need a manual map check (PR #21).
5. ~~P4~~ — merged (PR #22, 5 Nov 2026). Open from P4:
   N6 (cause of the monotonicity violations, methodology wording); count caching
   across runs (C10): every config change, also a threshold or a validation key, invalidates the
   `count` manifest and re-routes (3.5 min) — needed before thresholds are tuned (M2);
   `publish` is a no-op when its manifest is up to date even if the database lost the schema
   (delete `publish/manifest.json` to force); `current.*` views are `SELECT *` replaced with
   `CREATE OR REPLACE VIEW`, so a run schema that drops or reorders columns makes the switch fail
   (needs a migration path with the first contract change); add `DATABASE_URL_ADMIN` to
   existing local `.env` files.
   The §7 conflict in `architecture.md` about `cleanup` is resolved (v0.13, confirmed by Rico).
6. ~~Open from P1: `httpx2` as dev dependency against the Starlette TestClient warning~~ —
   done in P5. The pytest-asyncio loop-scope warning is fixed
   (`asyncio_default_fixture_loop_scope = "function"`).
7. ~~P5~~ — merged (PR #24, `88093ef`); N7 and N8 settled after it (variant C, branch
   `fix/rico-matrix-algorithm`). Open: report the `timedistancematrix` wheelchair gap upstream (N8);
   N4 (Valhalla memory comes from `costmatrix`); `catchment` for recommender candidates gets
   its candidates in P7; production command, HTTPS and no published ports in `compose.prod.yaml` (P8); measure API memory and
   inspect latency on the CX23 (VF3). Next: P6 (web) on `/api/cells`, `/api/districts`,
   `/api/inspect`, `/api/meta`.

## 9. Working rules (copy from the start prompt)

```text
- Follow AGENTS.md "How to work on a task" in every phase: understand → whole-project view →
  plan and confirm → small steps → verify with evidence → docs → report.
- Keep docs/implementation_plan.md as the handoff between sessions: phase status checkboxes,
  decisions made, deviations agreed, measured numbers, next steps, and a copy of these
  <working_rules>. Update it at the end of every phase.
- Spec over invention: if something is unspecified, choose the simplest option consistent with
  the docs and list it under "Assumptions" in the PR. If the docs are wrong, contradictory or
  impossible to implement as written, STOP and ask first (AGENTS.md docs-sync rule).
- Never guess external APIs: check the official docs or run a small test for Valhalla request
  parameters, Docker image names/tags and their arm64/amd64 support, osmium, DuckDB, GTFS files.
  Pin exact versions.
- Respect the 4 GB production budget: stream large files, vectorise, batch Valhalla calls,
  measure runtime and peak memory of every pipeline stage.
- Tests never use the network; Valhalla calls are mocked with recorded responses.
- Commit and PR rules from AGENTS.md/CONTRIBUTING.md: small Conventional Commits, CHANGELOG
  entry, README kept true, draft PRs only, never push to dev/main, never merge.
- Before a PR leaves draft: run a review with a fresh subagent that checks the diff against
  AGENTS.md, architecture.md, methodology.md and the data contract; fix its findings or list them.
```
