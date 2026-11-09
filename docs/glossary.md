# Glossary

Project vocabulary used in code, docs, issues and prompts. People and roles ("you", "your human",
"the team") are defined in [`AGENTS.md`](../AGENTS.md).

| Term | Meaning |
|---|---|
| **Core / Stretch** | Core = required for the graded deliverable. Stretch = only after Core works and is validated (`architecture.md` §12). |
| **city boundary** | Administrative boundary of Tübingen (OSM `admin_level` 8, AGS `08416041`); defines the scoring scope and the click area of the live endpoints. |
| **scoring scope** | All populated cells whose centroid lies inside the city boundary; they get scores and deficits (O11). |
| **urban boundary** | Built-up (settlement) area of Tübingen from OSM land use (O17); defines the map area and the recommender candidates, not who is scored. |
| **cell status** | Field `cell.status` of every live answer: `scored` (cell in `cells`), `unpopulated` (centre in the city, no residents in the Zensus grid; values computed live) or `outside_city` (centre outside the city boundary, never scored). |
| **routing buffer** | 4 km around the city boundary, at least the largest prefilter reach (O20); network and facilities are loaded from boundary + buffer. |
| **routing area** | City boundary plus the routing buffer; the OSM extract (`routing.osm.pbf`), facilities and stops are clipped to it. |
| **coverage (scored share)** | Residents of scored cells ÷ residents of all populated cells touching the city area; checked against `validation.min_scored_share` in `validate`. |
| **district** | Reporting unit from OSM `boundary=administrative` at the levels in `districts.admin_levels` (Tübingen: 9 = Teilorte, 11 = core-town districts). |
| **cell** | One populated Zensus 2022 100 m grid cell; the unit of analysis. `cell_id` = original EPSG:3035 ID. |
| **origin** | Routing start point of a cell (currently the cell centroid). |
| **facility** | A service location from OSM in one of the configured categories. |
| **transit supply (S)** | Raw sum of departures on the reference weekday at stops within a 10-minute walk of a cell (`transit_supply`). |
| **category** | Facility type defined in `config/config.yaml` (e.g. grocery, pharmacy, school); see `methodology.md` §2. |
| **profile** | Travel mode with its settings: walking 3.39 km/h, walking 5.0 km/h, cycling, wheelchair. |
| **reach** | Maximum straight-line distance of a profile (speed × time budget); the prefilter uses speed × speed factor × budget + margin (`architecture.md` §6.3). |
| **category group** | Thematic group of a category in `config.yaml` (`food`, `health`, `education`, `green`); the app combines categories per group. |
| **require / exclude** | Optional conditions of a category (`key: value`, `;`-separated OSM values match if any part matches): a feature needs at least one `require` and is dropped by any `exclude` (e.g. `access=private` for parks and playgrounds). |
| **access point** | Routing point of a park or playground where a walkable way crosses its boundary (fallback: points along the boundary); a park counts once, with the minimum time over its access points. |
| **refresh** | `make refresh`: full weekly update on the host — acquire, validate, tile build and swap, Valhalla restart, remaining stages. |
| **block** | Square group of cells (`count.block_size_m`, 500 m) whose origins are the sources of one matrix request per profile (`architecture.md` §6.5 rule 2). |
| **prefilter evidence** | Matrices with widened candidate sets for sample blocks in every `count` run; shows whether any facility is reachable beyond the prefilter reach (O20, `count/report_count.json`). |
| **count (A)** | Number of facilities of a category reachable from a cell within the time budget, via Valhalla matrix. |
| **class** | Lack / insufficient / sufficient per cell, category and profile (`methodology.md` §4). |
| **deficit (U)** | Population-weighted unmet need per cell (`methodology.md` §4). |
| **k_c** | Sufficiency threshold of category *c* (`methodology.md` §2). |
| **reachable** | Facilities a cell reaches within the time budget per profile, with matrix time (`reachable` table, written by `count`); the list behind `count (A)`, read by the inspector. |
| **catchment** | Cells that reach a facility or candidate site within the time budget. |
| **candidate (zone)** | 100 m Zensus grid cell inside the urban boundary, outside excluded land use, where the recommender may place one new facility; identified by its grid id (`candidate_id`); recommendations name zones, not exact sites (`methodology.md` §5). |
| **gain (ΔW)** | Reduction of the deficit sum of a category and profile if one facility is added at a candidate: residents of its catchment weighted by the share of *k* the new facility fills (`methodology.md` §5). |
| **grid cell (snapping)** | The 100 m Zensus grid cell under a clicked point, populated or not; its id is computed from EPSG:3035 and live endpoints start from its centre, so answers are cached per (run, cell, profile) (`architecture.md` §6.5 rule 8). |
| **live endpoint** | API endpoint that calls Valhalla (`inspect`, `catchment`, `expansion`); boundary check first, cached, rate-limited. Read endpoints only read `current`. |
| **trusted proxy** | Host whose `X-Forwarded-For` header the API believes (Caddy, `api.trusted_proxies`); for any other peer the client IP is the peer address. |
| **reference weekday** | Regular Tuesday in the GTFS validity period used to count departures: first one on or after the run date that is no public or school holiday (`reference_day` in config) and has active services. |
| **provenance** | Per source and run: URL, retrieval time, SHA-256, licence (`acquire/data_sources.parquet`, published to `meta.data_sources`). |
| **matrix** | Valhalla `sources_to_targets`: travel times between many points; used for all counting. |
| **isochrone** | Valhalla polygon of the area reachable within a time; display only. |
| **access point** | Routing point of a park or playground on its boundary (a walkable way crossing it, else every 50 m); a park counts once, its time is the minimum over its access points. The app shows them next to the park outline. |
| **facility tags** | Informative OSM tags kept per facility (`facility_tags` in the config: opening hours, wheelchair, address, contact, speciality); displayed as stored, never used for counting. |
| **expansion** | Valhalla list of reached street segments with times; visualisation only. |
| **run / `run_id`** | One complete pipeline execution on one data snapshot; results are published as DB schema `run_<id>`. |
| **stage** | One pipeline step: acquire, validate inputs, build tiles, count, score, recommend, validate results, publish, cleanup. |
| **manifest** | File written by each stage listing inputs, outputs, row counts and status. |
| **validation report (part 1 / part 2)** | Part 1 (`validate`): checks of the inputs; part 2 (`validate_results`): checks of the results (completeness, totals, monotonicity, sample cells). Any failed check stops the run before `publish`; both parts are published as `validation_report`. |
| **monotonicity check** | Part-2 check that a "faster" profile reaches at least as many facilities as a "slower" one (`validation.results.monotonic`); reported as share of violating cells with warn/fail limits, because Valhalla routes by cost, not time (`notes.md` N6). |
| **published run** | A run whose schema `run_<id>` was loaded and switched to `current` by `publish` (`meta.runs.status = 'published'`); `cleanup` keeps the last 3. |
| **migration** | Numbered SQL file in `infra/db/migrations/`, applied once by `make migrate` (recorded in `meta.schema_migrations`); `infra/db/roles.sql` is re-applied every time. |
| **`current`** | DB views pointing to the latest validated run; the only schema the API reads. |
| **data contract** | Binding table and file schemas between pipeline and API (`docs/data_contract.md`). |
| **test clip** | Small OSM/GTFS/Zensus extract (~1 km²) used for integration tests. |
| **O-numbers (O1, …)** | Architecture decisions in `architecture.md` §13. |
| **M-numbers (M1, …)** | Open methodology questions in `methodology.md` §7. |
| **V-numbers (V1, …)** | Validation experiments in `methodology.md` §6; run by `make experiments` (`reach_pipeline.experiments`), interpreted in `validation_report.md`. |
| **validation report (experiments)** | `docs/validation_report.md`: method, result, interpretation and limitations of V1–V11 on one run; not to be confused with report parts 1/2 of every run. |
| **LISA** | Local Moran's I (V8): per cell, whether it and its neighbours are both high (high-high cluster), both low, or differ; significance by permutation. |
| **N-numbers (N1, …)** | Open points and future work in `notes.md`. |
| **gate G1** | Test whether slopes change walking times in Valhalla; answered 6 Nov 2026: yes, for all profiles (`architecture.md` §6.1); the effect on results is V11. |
| **ask first** | Stop, describe what you want to do and why, and wait for an explicit "yes" from your human. |
