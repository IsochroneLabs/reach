# Implementation plan — reach

> **Status:** P0 draft (2 Nov 2026), waiting for review by Rico. This file is the **handoff between
> agent sessions**: phase status, decisions, agreed deviations, measured numbers and next steps.
> It is informative; `architecture.md` and `methodology.md` stay binding. Where this plan proposes
> something that differs from them, it is listed in [Section 5](#5-conflicts-gaps-and-ambiguities)
> and only implemented after confirmation (plus a doc update in the same branch).

---

## 1. Phase status

| Phase | Topic | Branch | Status | Target date |
|---|---|---|---|---|
| P0 | Implementation plan | `docs/rico-implementation-plan` | [x] draft PR open, waiting for answers | 2 Nov |
| P1 | Scaffold & tooling | `feature/rico-scaffold` | [ ] | 6 Nov |
| P2 | acquire + validate inputs | `feature/rico-acquire-validate` | [ ] | 11 Nov |
| P3 | tiles + count | `feature/rico-tiles-count` | [ ] | 16 Nov |
| P4 | score + publish + cleanup | `feature/rico-score-publish` | [ ] | 19 Nov |
| P5 | API | `feature/rico-api` | [ ] | 21 Nov |
| P6 | Web | `feature/rico-web` | [ ] | 24 Nov |
| — | **Interim demo (local), `v0.1.0`** | release PR `dev` → `main` on request | [ ] | 25 Nov |
| P7 | Recommender + validation V1–V9 | `feature/rico-recommender`, `feature/rico-validation` | [ ] | 10 Jan |
| P8 | Production | `feature/rico-production` | [ ] | server from ~1 Dec, hardening until 15 Jan |

The dates leave about four working days per phase until 25 Nov. To make the interim demo, P1–P6
are built at **minimal depth** (marked *interim* below); the rest of each phase (*full*) is
finished between 25 Nov and 20 Dec, before P7. Branch names contain the name of the person
driving the session (`<type>/<name>-<topic>`, e.g. `feature/rico-scaffold`), so two sessions never
work on the same branch; an issue number goes in front of the topic if an issue exists.

## 2. Phases in detail

Conventions used by every phase:

- **Stage pattern (N2):** `python -m reach_pipeline <stage> [--run-id ID] [--config PATH]`;
  `run` executes all stages in order. Each stage is a module with one public
  `run(ctx: RunContext) -> Manifest`; `RunContext` holds the typed config, `run_id` and paths.
  At start it checks the previous stage's manifest (`status == "ok"`, input checksums match), at
  the end it writes `data/runs/<run_id>/<stage>/manifest.json` (inputs with checksums, outputs,
  row counts, runtime, peak RSS, status). Re-running a stage with unchanged inputs is a no-op.
- **Run id:** UTC timestamp `YYYYMMDDTHHMMZ` (e.g. `20261116T0300Z`); DB schema `run_20261116t0300z`.
- **Measurement:** one helper logs wall time and peak memory (`resource.getrusage`, children
  included) per stage; values go into the manifest and the PR.
- **Exit codes:** 0 ok; 1 validation failed; 2 configuration error; 3 external failure (network,
  Valhalla, DB) after retries.
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
| `pipeline/src/reach_pipeline/config.py` | pydantic models + `load_config(path) -> Config`; validates: speeds > 0, `k_c ≥ 1`, unique category ids, tags non-empty, transit bounds increasing, buffer ≥ max reach of all profiles |
| `pipeline/src/reach_pipeline/{__main__.py, cli.py, context.py, manifest.py, metrics.py}` | stage pattern skeleton with a no-op `hello` stage proving the pattern end to end |
| `pipeline/tests/test_config.py`, `test_manifest.py` | valid config loads; each invalid case fails with a clear message; manifest round-trip |
| `.github/workflows/ci.yml` | `astral-sh/setup-uv` (cache), `uv sync --frozen`, ruff check + format check, `uv run pytest` |
| `.github/pull_request_template.md` | template from `CONTRIBUTING.md` §4 |
| `.github/CODEOWNERS` | per folder; content depends on Q4 |
| `pipeline/AGENTS.md`, `api/AGENTS.md` | stage pattern (N2), test layout, mocked Valhalla; API read-only from `current` |
| `docs/data_contract.md` | first draft with the tables in [Section 3](#3-proposed-data-contract-docsdata_contractmd) |
| `README.md`, `CHANGELOG.md`, `AGENTS.md` status line, `docs/notes.md` (close N2) | kept true |

**Done when:** `uv run ruff check . && uv run ruff format --check . && uv run pytest` pass;
`make up` shows `db` healthy (`docker compose ps`); `make pipeline STAGE=hello` writes a manifest;
CI green on the draft PR.

### P2 — acquire + validate inputs

| Create | Key functions |
|---|---|
| `stages/acquire.py` | `download(source) -> Path` with retries/backoff, skip if unchanged (Geofabrik `.md5`, HTTP `ETag`/`Last-Modified`, local checksum); unchanged files are hard-linked from the previous run; provenance rows (URL, retrieved at, checksum, licence) |
| `osm.py` | `osmium tags-filter` / `osmium extract -p` / `osmium export` wrappers (subprocess, streaming, no full PBF in Python) |
| `boundary.py` | `admin_boundary(...)`, `urban_boundary(landuse, admin, cfg)`: dissolve built-up land use inside the city, `buffer(+50).buffer(-50)`, drop parts < configured min area, keep Teilorte as separate parts (O17a); `routing_area = urban.buffer(4000)` |
| `zensus.py` | DuckDB streaming read of the national 100 m CSV filtered by bbox while reading; `GITTER_ID` kept as `cell_id`; cell polygon + centroid in 25832 |
| `gtfs.py` | DuckDB reads `stops.txt`, `calendar*.txt`; `reference_weekday(feed, holidays)`; stops of `location_type 0` inside the routing area |
| `facilities.py` | tag → category mapping from config; points stay points, polygons → `representative_point`; parks/playgrounds → access points (see C4); de-duplication of node + area of the same facility |
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
| `compose.yaml` `valhalla-build` | one-shot: `valhalla_build_elevation` (cached in volume) → `valhalla_build_tiles` → `valhalla_build_extract` → `valhalla_tiles.new.tar`; swap: `tiles.tar → tiles.prev.tar`, `new → tiles.tar`; restart `valhalla`; skipped if PBF checksum unchanged |
| `stages/tiles.py` | checks PBF checksum vs. last build, invokes the build (see C2 for orchestration), waits for `/status`, writes manifest |
| `valhalla/client.py` | async `httpx` client, `asyncio.Semaphore(concurrency)`, retries with backoff on timeouts/5xx, `matrix(sources, targets, costing, options) -> np.ndarray` (seconds, `None` = unreachable) |
| `count.py` | `make_blocks(cells, size_m)`, `prefilter(block, facilities, reach_m)` (exact; see C1 for margin), `count_block(...)`: one matrix for all categories + stops, split by category via `groupby`, min time per facility id (multi-point facilities) |
| `stages/count.py` | all cells × categories × profiles → `access_counts.parquet` (`count`, `nearest_min`); stops within 10 min for walking profiles → `transit_supply.parquet` (C3) |
| `transit.py` | departures per stop on the reference weekday (DuckDB over `stop_times.txt` joined to active `service_id`s) |
| tests | recorded Valhalla matrix responses (`pipeline/tests/fixtures/valhalla/*.json`, replayed with `respx`); block/prefilter tests (no facility within reach dropped); split-by-category; departure counting |
| `tests/integration/test_golden.py` | 3–5 cell → facility pairs with hand-checked times (map measurement ÷ speed, ± tolerance), against local Valhalla on the test clip; marked `integration` |

**Done when:** counts for all cells × categories × profiles exist; departures for walking
profiles; runtime and peak memory of `tiles` and `count` (and Valhalla RSS via `docker stats`)
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
| `stages/validate_results.py` | report part 2: monotonicity (5.0 km/h ≥ 3.39 km/h counts; cycling ≥ walking where expected; wheelchair ≤ walking 3.39), totals (residents in classes = scored residents), sample checks, fail → no publish |
| `stages/publish.py` | `COPY` into new schema `run_<id>` in one transaction, then `CREATE OR REPLACE VIEW current.*` in one transaction; `meta.runs` status; failure webhook if `FAILURE_WEBHOOK_URL` is set |
| `stages/cleanup.py` | keep last 3 published runs (schemas + `data/raw|runs/<run_id>/`) |
| tests | SQL contract test against a disposable PostGIS (`integration` marker, also run in CI as a service container if Q4/infra allows), scores view against hand-computed classes/deficits |

**Done when:** `make pipeline` publishes a run; `current.scores` returns classes/deficits that
match hand computation for sample cells; re-publishing switches `current` atomically; only 3 runs remain.

*Interim:* `scores` + `district_scores`, roles, publish; cleanup and report part 2 minimal.

### P5 — API

| Create | Content |
|---|---|
| `api/src/reach_api/{main.py, settings.py, db.py, valhalla.py, cache.py, ratelimit.py}` | psycopg pool on `app_read`; pydantic-settings; small in-process LRU per (cell, profile); token-bucket rate limit per client IP (no new dependency) |
| `routes/read.py` | `GET /api/meta`, `/api/districts`, `/api/districts/{id}/scores`, `/api/cells?category=&profile=` (GeoJSON, `ST_Transform(…, 4326)`), `/api/recommendations` (empty until P7) |
| `routes/live.py` | `POST /api/inspect` (cell lookup → precomputed values + one isochrone call with 5/10/15 contours + routes to nearest facility per category, from the cell origin), `POST /api/catchment`, `POST /api/expansion`; boundary check before any Valhalla call |
| `infra/api.Dockerfile` | `uv sync --frozen --no-dev --package api` |
| tests | `TestClient` with fake DB layer and `respx`-mocked Valhalla; boundary rejection; cache hit avoids second call; rate limit; GeoJSON shape |

**Done when:** all endpoints respond on the local stack; `curl` examples in the PR; tests pass.
*Interim:* read endpoints + `inspect`; `catchment`/`expansion` after the interim.

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
CI job building `linux/amd64` images tagged with git SHA, `make deploy`, systemd service + timer
(Monday 03:00 UTC, `flock`), nightly `pg_dump`, failure webhook, server setup script, firewall
notes. Measure memory on the CX23 (Section 4).

### Dependencies expected per phase (each asked before adding)

| Phase | Candidate | Why |
|---|---|---|
| P1 | none (pydantic, pyyaml already present) | — |
| P2 | `osmium-tool` CLI (system binary: Homebrew locally, apt in the pipeline image) | clip/filter/export PBF by streaming |
| P2 | DuckDB `spatial` extension? | only if needed; must be installed in the image at build time, not downloaded at runtime |
| P5 | none planned | cache and rate limit hand-written |
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
| `transit_supply` *(proposed, C3)* | cell × profile | `cell_id`, `profile_id`, `stops_count`, `departures`, `nearest_stop_min` |
| `thresholds` | category / transit class | `category`, `k`, `class`, `lower`, `upper` |
| `scores` (view) | cell × category × profile | `class`, `deficit` |
| `transit_scores` (view, C3) | cell × profile | `class` (lack/insufficient/medium/high) |
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
| VF1 | Slopes change walking times (gate G1, §6.1) | Out of Core. In P3 only prove the tiles contain elevation (`/height` or `route` with `elevation_interval` returns heights). G1 itself: route old town → castle and city → Waldhäuser-Ost both directions with default vs. hill-related pedestrian options; compare times | P3 (elevation present), P7 (G1) |
| VF2 | Cycling costing applies elevation (§6.1) | Same steep pair uphill vs. downhill with `bicycle`; asymmetric times = elevation used; repeat with `use_hills` 0 vs. default; record numbers in the PR | P3 |
| VF3 | Memory budget (§11) | Locally: `docker stats` for PostGIS, Valhalla, API during a full count + live calls; pipeline peak RSS from manifests. On the CX23: same plus `free -m` during a weekly run | P3/P4 (local), P8 (server) |
| VF4 | Tile build fits on CX23 with swap (§11.1) | Locally run `valhalla-build` with `--memory 1.5g` (approximating the share left on the server) and measure; then a same-day test server build | P3 (local), P8 (server) |
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
| Matrix limits / runtime for cycling (3.75 km reach → many targets per block) | block size per profile from config; measure in P3; raise limits in `valhalla.json` |
| Prefilter not exact because of snapping and downhill cycling (C1) | configurable margin, tested in P3 |
| PostGIS or Valhalla image lacks arm64 → slow emulation on the Mac | check in P1, ask before switching image |
| OSM incompleteness per category (M1) | counts per category in report part 1; V2 in P7 |
| Elevation download needs network during tile build; CI cannot build elevation for the test clip | test clip tiles built without elevation (C6) |
| 4 GB RAM in production | streaming reads, bounded concurrency, swap, measurement (VF3) |

## 5. Conflicts, gaps and ambiguities

| # | Finding | Where | Recommended resolution |
|---|---|---|---|
| C1 | The straight-line prefilter is called **exact**, but (a) Valhalla snaps origin and target to the network and does not count the snap distance as travel time, so two snapped points can be closer than the raw points; (b) bicycle costing can be faster than 15 km/h downhill and on good surfaces | arch. §6.3, §6.5 rule 3; methodology §1 | Add config `count.prefilter_margin_m` (e.g. 150 m) and a per-profile `max_speed_factor` (1.0 walking, measured for cycling in P3); keep the word "exact" by defining reach = speed × factor × budget + margin. Needs a doc update (Q3) |
| C2 | The pipeline container runs `tiles`, but starting `valhalla-build` and restarting `valhalla` from inside a container needs the Docker socket (security and complexity) | arch. §7, §11 | Orchestrate on the host: `make pipeline` / systemd unit runs `pipeline acquire validate` → `docker compose run valhalla-build` (only if PBF changed) → `docker compose restart valhalla` → `pipeline count … cleanup`. The `tiles` stage inside Python only decides "rebuild needed" and verifies the result. Needs a doc update (Q2) |
| C3 | Transit supply has no place in the table list: `access_counts` has `count`, `nearest_min`, but $S_i$ (sum of departures) and the 4 transit classes need their own columns | arch. §8, methodology §3 | Add `transit_supply` table and `transit_scores` view (Q1) |
| C4 | Parks, playgrounds and schools are often large polygons; one representative point inside a large park undercounts access | methodology §2 | Represent area facilities by their representative point, and parks/playgrounds additionally by access points (boundary points where paths cross the park edge, fallback: points every 100 m on the boundary); a facility counts once via `min` time over its points. Keep in config; note in methodology on confirmation |
| C5 | "Walking profiles only" for transit vs. the reach table that also lists wheelchair stops (565 m) | methodology §3 vs. arch. §6.1 | Compute transit supply for walking 3.39, walking 5.0 **and** wheelchair; not for cycling. Small wording fix in methodology §3 |
| C6 | Tiles are "always built with elevation", but the CI/test clip cannot download elevation (network, size) | arch. §6.1 vs. AGENTS tests | Test clip tiles without elevation via `config/test_clip.yaml`; production always with elevation |
| C7 | School holidays for the reference weekday need a data source; a public holiday API at runtime is not allowed and a `holidays` package does not cover school holidays | arch. §6.3 | List BW public and school holidays for the feed period in `config/config.yaml` (source: Kultusministerium BW), validated to cover the feed's validity window |
| C8 | Districts at admin levels 9–11 overlap; `cells.district_id` needs one level | arch. §5.2 | Config key `districts.admin_level` (decided in P2 after inspecting the data); other levels can be added later |
| C9 | API needs the urban boundary (live check), districts and the profile costing for live isochrones; none of these are DB tables in §8 | arch. §8, §9 | Add `urban_boundary`, `districts`, `profiles` tables to the run schema (gaps G1/G2 in Section 3), so live answers use exactly the published run's costing |
| C10 | Changing thresholds "never requires re-routing", but only `publish` writes to PostGIS and thresholds are copied per run | arch. §6.3, §8 | `count` is cached by (PBF checksum, cells/facilities checksum, profile config hash); a threshold change re-runs the pipeline as a new run that reuses cached counts, so no re-routing happens |
| C11 | Stage names differ: AGENTS lists 7 stages, arch. §7 lists 9 (incl. "validate results", "cleanup"); `make pipeline STAGE=validate` is ambiguous | AGENTS, arch. §7 | CLI names `acquire, validate, tiles, count, score, recommend, validate_results, publish, cleanup`; `validate` = inputs |
| C12 | Cells outside the urban boundary: stored or not? | arch. §4, §8 | `cells` holds only scored cells; outside residents appear as totals in the validation report |
| C13 | P0 forbids changing other docs, but AGENTS asks to keep `README.md` (documentation table) and `CHANGELOG.md` true | AGENTS vs. P0 task | Add the plan to the README documentation table and CHANGELOG in P1 |
| C14 | No owners in `CODEOWNERS` yet (T2 due 4 Nov); P1 touches `pipeline`, `api`, `config`, `infra`, `.github` → "ask first" for multi-folder changes | AGENTS boundaries | Q4 |

## 6. Questions for Rico

1. **Transit storage (C3):** add `transit_supply` (cell × profile) and `transit_scores` to
   `architecture.md` §8 (v0.11)? *Recommended: yes.*
2. **Tile build orchestration (C2):** orchestrate `valhalla-build` and the Valhalla restart on the
   host (Makefile / systemd), not from inside the pipeline container? *Recommended: yes, host-side;
   update arch. §7/§11 accordingly.*
3. **Prefilter margin (C1):** add `prefilter_margin_m` and a cycling speed factor to config and
   reword "exact" in arch. §6.3/§6.5 and methodology §1? *Recommended: yes, value measured in P3.*
4. **Folder approval and CODEOWNERS (C14):** does confirming a phase plan count as the "ask
   first" approval for the folders listed in that phase? And which CODEOWNERS for P1?
   *Recommended: yes per phase; CODEOWNERS lists all three of you for every folder until T2 is
   settled.*
5. **Parks and large facilities (C4):** access points on the park boundary (min time per facility)
   instead of a single point? *Recommended: yes for parks/playgrounds; representative point for
   all other polygons; documented in methodology §2.*

Other recommendations in Section 5 (C5–C13) are taken as defaults unless you object.

## 7. Decisions made, deviations agreed, measured numbers

| Date | Item | Result |
|---|---|---|
| 2026-11-02 | Defaults from the start prompt | O17 option (a); M1 table as config defaults; O14 webhook optional, no-op if unset; O16 local demo |

Measured numbers (runtime, peak memory, counts) are added here at the end of every phase.

## 8. Next steps

1. Rico answers Q1–Q5 and reviews this plan (comments on the PR).
2. Apply the agreed answers to this file; doc changes to `architecture.md`/`methodology.md` happen
   in the phase that needs them (P1 for C3/C9/C11, P3 for C1/C2), with version bump and change log.
3. Start P1 in a new session from fresh `dev` after explicit confirmation.

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
