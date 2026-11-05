# Data contract — reach

> **Status:** draft v0.6 (5 Nov 2026), from `implementation_plan.md` §3. Binding for the tables
> and files exchanged between pipeline and API once a phase implements them; every change needs
> confirmation (AGENTS.md) and a data-contract test. Tables marked *(planned, Pn)* do not exist yet.

Conventions:

- Geometries: PostGIS `geometry(<type>, 25832)`; GeoParquet with CRS EPSG:25832. The API
  transforms to EPSG:4326 at query time.
- Times in minutes (`double precision`), distances in metres, timestamps `timestamptz` in UTC.
- `profile_id` = key under `profiles` in `config/config.yaml` (e.g. `walking_339`);
  `category` = `categories[].id`.
- Unreachable within the budget: `count = 0`, `nearest_min` = `NULL`.
- Derived values (classes, deficits, district shares) are views; the pipeline stores raw counts
  and times only (AGENTS.md rule 5).

## Roles *(implemented, P4: `infra/db/roles.sql`)*

| Role | Rights |
|---|---|
| `pipeline_write` | `publish`/`cleanup`: creates and drops `run_<id>` schemas, owns the `current` views, reads and writes `meta.runs` and `meta.data_sources` |
| `app_read` | API: `SELECT` on `current.*`, `meta.runs`, `meta.data_sources`; no access to `run_<id>` schemas |
| `supervisor_read` | `SELECT` on `current.*`, `meta.*` tables and every `run_<id>` schema (default privileges) |

Roles, passwords (from `.env`) and migrations are applied by `python -m reach_pipeline migrate`
(`make migrate`) as the superuser (`DATABASE_URL_ADMIN`).

## Schema `meta` *(implemented, P4: `infra/db/migrations/0001_meta.sql`)*

### `meta.runs`

| Column | Type | Null | Description |
|---|---|---|---|
| `run_id` | `text` PK | no | `YYYYMMDDTHHMMSSZ` |
| `started_at` | `timestamptz` | no | Pipeline start |
| `finished_at` | `timestamptz` | yes | Set at publish |
| `status` | `text` | no | `running`, `published`, `failed` |
| `osm_snapshot` | `timestamptz` | yes | Timestamp of the OSM extract |
| `gtfs_valid_from` | `date` | yes | Feed validity start |
| `gtfs_valid_to` | `date` | yes | Feed validity end |
| `reference_weekday` | `date` | yes | Day used for transit departures |
| `config_hash` | `text` | no | SHA-256 of the merged config |

### `meta.data_sources`

| Column | Type | Null | Description |
|---|---|---|---|
| `run_id` | `text` FK → `runs` | no | |
| `source` | `text` | no | `osm`, `gtfs`, `zensus`, `elevation` |
| `url` | `text` | no | Download URL |
| `retrieved_at` | `timestamptz` | no | |
| `checksum` | `text` | no | SHA-256 of the downloaded file |
| `licence` | `text` | no | From config |

PK (`run_id`, `source`); rows are deleted with their run (`ON DELETE CASCADE`).

### `meta.schema_migrations`

| Column | Type | Null | Description |
|---|---|---|---|
| `version` | `text` PK | no | File name of an applied migration without `.sql`, e.g. `0001_meta` |
| `applied_at` | `timestamptz` | no | |

Created by `migrate` itself; `cleanup` deletes the `meta.runs` rows (and with them the
`meta.data_sources` rows) of the runs whose schema it drops.

## Schema `run_<id>` and views `current.*` *(implemented, P4: `infra/db/run_schema.sql`)*

`current.<name>` is a view (`SELECT *`) on `run_<id>.<name>` of the latest published run; `publish`
replaces all of them in one transaction.

| Table / view | Grain | Columns (type, null) | Key |
|---|---|---|---|
| `cells` | scored census cell | `cell_id` text, `population` integer, `district_id` text null, `geom` Polygon, `origin_geom` Point | `cell_id` |
| `districts` | district | `district_id` text, `name` text, `admin_level` smallint, `geom` MultiPolygon | `district_id` |
| `urban_boundary` | urban part | `part_id` integer, `name` text null, `geom` MultiPolygon | `part_id` |
| `facilities` | facility | `facility_id` text (`n123`/`w456`/`r789`), `category` text, `name` text null, `geom` Point | (`facility_id`, `category`) |
| `facility_points` | routing point of a facility | `facility_id` text, `point_id` integer, `kind` text (`node`, `representative`, `access`), `geom` Point | (`facility_id`, `point_id`) |
| `stops` | GTFS stop | `stop_id` text, `name` text, `weekday_departures` integer, `geom` Point | `stop_id` |
| `profiles` | profile | `profile_id` text, `costing` text, `costing_options` jsonb (options exactly as sent to Valhalla, incl. `walking_speed`/`cycling_speed`), `speed_kmh` double, `time_budget_min` double (facility budget) | `profile_id` |
| `access_counts` | cell × category × profile | `cell_id` text (FK `cells`), `category` text, `profile_id` text (FK `profiles`), `count` integer, `nearest_min` double null | (`cell_id`, `category`, `profile_id`) |
| `transit_supply` | cell × walking/wheelchair profile | `cell_id` text, `profile_id` text, `departures` integer, `stops_count` integer, `nearest_stop_min` double null | (`cell_id`, `profile_id`) |
| `thresholds` | category or transit class | `category` text (`transit` for transit classes), `k` integer null, `class` text null, `lower` integer null, `upper` integer null | unique (`category`, `class`) `NULLS NOT DISTINCT` (`class` is null on category rows, so no PK) |
| `scores` (view) | cell × category × profile | `access_counts` columns + `class` text (`lack`, `insufficient`, `sufficient`), `deficit` double | as `access_counts` |
| `transit_scores` (view) | cell × profile | `cell_id`, `profile_id`, `class` text (`lack`, `insufficient`, `medium`, `high`; bounds inclusive) | (`cell_id`, `profile_id`) |
| `district_scores` (mat. view) | district × category × profile | `district_id`, `category`, `profile_id` text, `share_lack`, `share_insufficient`, `share_sufficient` double (of the district's residents), `deficit_sum` double, `residents_lack` integer; cells without district left out; refreshed by `publish` | (`district_id`, `category`, `profile_id`), unique index |
| `recommendations` *(planned, P7)* | candidate × category × profile | `rank` integer, `population_gain` double, `geom` Polygon | (`category`, `profile_id`, `rank`) |
| `validation_report` | check | `check` text, `stage` text, `status` text (`ok`, `warn`, `fail`), `value` double null, `message` text; rows of report parts 1 (`validate`) and 2 (`validate_results`) | (`stage`, `check`) |

`cells.cell_id` is the Zensus `GITTER_ID_100m` (EPSG:3035 grid id, e.g. `CRS3035RES100mN2822200E4250500`; verified 2 Nov 2026);
the `cells` table holds only scored cells (C12): every populated cell whose centre lies inside the
city boundary (architecture O11). Facilities are counted once per facility id,
with the minimum time over their points.

## API responses *(implemented, P5: `api/src/reach_api/routes/`)*

All bodies are JSON; coordinates EPSG:4326 `[lon, lat]` with at most 6 decimals, built in
PostGIS (`ST_Transform`, `ST_AsGeoJSON(…, 6)`). Times from Valhalla in seconds (`time_s`),
precomputed times in minutes (`nearest_min`). Classes and deficits are the values of the
`current` views. Errors: `{"detail": …}` with 404 (unknown district or facility), 422 (unknown
profile or category, invalid body, point outside, no street near the point), 429 (rate limit,
`Retry-After`), 500 (a profile of the run is missing in the config), 502 (Valhalla down or a
matrix too large), 503 (database down or no published run). Concurrent requests for the same
uncached answer share one Valhalla computation and report `cached: true`.

**Read endpoints** (no rate limit; header `ETag: W/"<run_id>:<endpoint>:…"`,
`Cache-Control: no-cache`, `If-None-Match` → 304):

| Endpoint | Body |
|---|---|
| `GET /api/meta` | `run` (row of `meta.runs`), `data_sources` (rows of `meta.data_sources`: `source`, `url`, `retrieved_at`, `checksum`, `licence`), `validation` {`ok`, `warn`, `fail` counts, `issues`: non-ok rows of `validation_report`}, `profiles` [{`profile_id`, `costing`, `speed_kmh`, `time_budget_min`, `transit`}], `categories` [{`id`, `name` (config), `k`}], `transit_classes` [{`class`, `lower`, `upper`}] |
| `GET /api/districts` | GeoJSON FeatureCollection (`application/geo+json`) + `run_id`; feature `id` = `district_id`, properties `district_id`, `name`, `admin_level`, `residents`, `cells` (scored cells) |
| `GET /api/districts/{id}/scores?profile=` | `run_id`, `district_id`, `name`, `admin_level`, `scores` [{`category`, `profile_id`, `share_lack`, `share_insufficient`, `share_sufficient`, `deficit_sum`, `residents_lack`, `rank_deficit`, `rank_share_lack`, `districts_ranked`}]; ranks over all districts per category × profile (1 = highest), `profile` optional |
| `GET /api/cells?category=&profile=` | GeoJSON FeatureCollection + `run_id`, `category`, `profile_id`; feature `id` = `cell_id`, Polygon; properties `cell_id`, `population`, `district_id`, `count`, `nearest_min`, `class`, `deficit`. `category=transit` (profiles with transit only): `departures`, `stops_count`, `nearest_stop_min`, `class` instead of the count columns |
| `GET /api/recommendations?category=&profile=` | FeatureCollection + `run_id`, `available: false`, empty `features` until P7 |

**Live endpoints** (`POST`, JSON body; token bucket per client IP; `cached` true when served
from the in-process cache of the run). Points are snapped to the 100 m Zensus grid cell; `cell`
= {`cell_id`, `scored`, `population`, `district_id`, `origin` [lon, lat]} (`population` and
`district_id` null for unscored cells). `isochrone` = FeatureCollection of Polygons with
property `contour_min` (5, 10, 15), sorted ascending; display only.

| Endpoint | Request | Body |
|---|---|---|
| `POST /api/inspect` | {`lon`, `lat`, `profile`} | `run_id`, `profile_id`, `cell`, `precomputed` ({`categories` [{`category`, `count`, `nearest_min`, `class`, `deficit`}], `transit` {`departures`, `stops_count`, `nearest_stop_min`, `class`} or null} or null for unscored cells), `weakest_category` (worst class, then largest deficit; null if all sufficient or unscored), `isochrone`, `categories` [{`category`, `name`, `reachable` [{`facility_id`, `name`, `time_s`, `time_min`}] nearest first, `nearest_route` (Feature LineString, properties `time_s`, `length_m`) or null}], `cached` |
| `POST /api/catchment` | {`facility_id`, `profile`} or {`lon`, `lat`, `profile`} | `run_id`, `profile_id`, `target` ({`kind`: `facility`, `facility_id`, `name`, `categories`} or {`kind`: `cell`, …`cell`}), `residents`, `cells`, `cell_ids` (scored cells reaching the target within the budget), `residents_by_class` {category: {class: residents}} (facility categories only), `isochrone` (reverse: areas from which the target is reached), `cached` |
| `POST /api/expansion` | {`lon`, `lat`, `profile`} | FeatureCollection of LineStrings (property `duration` in seconds) + `run_id`, `profile_id`, `cell`, `budget_min`, `cached` |

## Files (`data/runs/<run_id>/<stage>/`)

GeoParquet/Parquet layers with the same columns as the tables above, plus:

### `manifest.json` *(implemented, P1: `reach_pipeline.manifest.Manifest`)*

| Field | Type | Description |
|---|---|---|
| `stage` | string | Stage name |
| `run_id` | string | `YYYYMMDDTHHMMSSZ` |
| `status` | `"ok"` \| `"failed"` | |
| `started_at`, `finished_at` | ISO 8601 UTC | |
| `runtime_s` | number | Wall time of the stage |
| `peak_rss_mb` | number | Peak RSS in MB of the process (or its largest child) up to the end of the stage; under `run` it includes earlier stages |
| `inputs` | list of {`path`, `sha256`} | Files read, with checksums |
| `outputs` | list of {`path`, `rows` (null if not tabular)} | Files written |
| `message` | string | Summary or error message |

### `acquire/data_sources.parquet` *(implemented, P2)*

One row per source (`osm`, `gtfs`, `zensus`): the columns of `meta.data_sources` (`run_id`,
`source`, `url`, `retrieved_at`, `checksum` = SHA-256, `licence`) plus `checked_at` (this run's
check), `path` (file in `data/raw/<run_id>/<source>/`), `etag`, `last_modified` (HTTP headers,
null if not sent), `md5` (of the file) and `reused` (true = unchanged, hard-linked from the
previous run; `retrieved_at` is then the time of the original download).

### `validate/` layers *(implemented, P2)*

GeoParquet, EPSG:25832, columns as in the run schema above:

| File | Columns | Note |
|---|---|---|
| `cells.parquet` | `cell_id`, `population`, `district_id`, `geometry` (cell polygon), `origin_geom` (cell centre) | scored cells only (C12) |
| `facilities.parquet` | `facility_id`, `category`, `name`, `geometry` | node or representative point; inside the routing area |
| `facility_points.parquet` | `facility_id`, `point_id`, `kind`, `geometry` | |
| `stops.parquet` | `stop_id`, `name`, `geometry` | `weekday_departures` is added by `count` (`count/stops.parquet`) |
| `districts.parquet` | `district_id` (`r<relation id>`), `name`, `admin_level`, `geometry` | levels from `districts.admin_levels` |
| `urban_boundary.parquet` | `part_id`, `name` (null), `geometry` | |
| `routing_area.parquet` | `geometry` | city boundary + routing buffer; file only, no table |

Plus `routing.osm.pbf` (the OSM extract clipped to the routing area, input of `tiles`) and the
osmium intermediates in `validate/osm/`.

### Validation report part 1: `validate/report_inputs.json` + `report_inputs.md` *(implemented, P2)*

| Key | Content |
|---|---|
| `run_id`, `stage`, `status` (`ok`/`fail`), `generated_at` | |
| `summary` | `city`, `osm_snapshot`, `urban_boundary_parts`, `urban_area_km2`, `city_area_km2`, `routing_area_km2`, `districts`, `cells_scored`, `residents_touching_city` (coverage base), `residents_scored`, `residents_excluded`, `scored_share`, `residents_outside_urban_boundary` (scored, informative), `excluded_by_district` {district name: residents}, `facilities` {category: count}, `facility_points`, `stops`, `gtfs_valid_from`, `gtfs_valid_to`, `reference_weekday`, `active_services` |
| `checks` | list of rows of `validation_report` (`check`, `stage`, `status`, `value`, `message`) |
| `stages` | `stage`, `runtime_s`, `peak_rss_mb` for `acquire` and `validate` |
| `steps` | `step`, `runtime_s`, `peak_rss_mb` (high-water mark so far) within `validate` |

The Markdown file renders the same content. Part 2: see `validate_results/` below.

### `tiles/` *(implemented, P3)*

| File | Content |
|---|---|
| `rebuild_needed` | Written by `tiles check` only if the tiles must be (re)built; shell variables read by `make refresh`: `PBF` (clipped PBF of the run), `SHA256` (fingerprint of PBF + `config/valhalla.json` + elevation flag), `ELEVATION` (`true`/`false`), `BBOX` (routing area in EPSG:4326, `min_lon,min_lat,max_lon,max_lat`) |
| `verify.json` | Written by `tiles verify`: `valhalla_version`, `tileset_last_modified`, golden route `route_length_m`, `route_time_s`, `straight_line_m`, `detour_factor`, `grade_edges`, `max_abs_weighted_grade`, `max_upward_grade`, `tiles_match_run` (tiles built from this run's inputs), `serves_tiles_of_this_config` |

Outside the run directory, `<data_dir>/valhalla/` holds `valhalla_tiles.tar` (served),
`valhalla_tiles.prev.tar` (rollback), `tiles_source.sha256` (fingerprint of the last build),
`elevation/` (cached elevation tiles) and `build/` (scratch space of `valhalla-build`).

### `count/` *(implemented, P3)*

Plain Parquet (no geometry), columns and types as in the run schema above:

| File | Grain | Columns |
|---|---|---|
| `access_counts.parquet` | cell × category × profile (complete grid) | `cell_id`, `category`, `profile_id`, `count` (int32), `nearest_min` (double, null if no facility of the category is reachable within the budget) |
| `transit_supply.parquet` | cell × profile with `transit: true` | `cell_id`, `profile_id`, `departures` (int32, sum over stops reachable within the transit budget), `stops_count` (int32), `nearest_stop_min` (double, null if none within the budget) |
| `stops.parquet` | GTFS stop (GeoParquet) | validate's `stops` + `weekday_departures` (int64: stop events of trips active on the reference weekday, without `pickup_type` 1) |
| `report_count.json` | run | `reference_weekday`, `cells`, `profiles` {profile: `blocks`, `requests`, `runtime_s`, `max_sources`, `targets_max`, `targets_median`, `pairs`, `facility_reach_m`, `transit_reach_m`}, `evidence` (`sample_blocks`, per profile `facilities` / `stops`: `pairs`, `reachable_pairs`, `nominal_reach_m`, `prefilter_reach_m`, `max_reachable_distance_m`, `required_factor`, `max_speed_ratio_by_band`, `beyond_nominal`, `beyond_prefilter`; `beyond_prefilter_examples`), `runtime_s`, `peak_rss_mb` |

`nearest_min` is only stored up to the budget: beyond it the straight-line prefilter does not
guarantee that the nearest facility was among the matrix targets.

### `score/` *(implemented, P4)*

`thresholds.parquet`: the `thresholds` table of the run (category rows with `k`; transit rows with
`category = 'transit'`, `class`, `lower`, `upper`), nullable integers.

### Validation report part 2: `validate_results/report_results.json` + `.md` *(implemented, P4)*

| Key | Content |
|---|---|
| `run_id`, `stage`, `status` (`ok`/`fail`), `generated_at`, `runtime_s`, `peak_rss_mb` | |
| `checks` | rows of `validation_report`: `access_counts_complete`, `transit_supply_complete`, `value_ranges`, `thresholds_cover_categories`, `class_totals`, `monotonic_<higher>_ge_<lower>` (value = share of violating cells), `sample_cells` |
| `summary` | `residents_scored`; `access` {profile: {category: `share_lack`, `share_insufficient`, `share_sufficient`, `residents_lack`, `deficit_sum`}}; `transit` {profile: {class: share of residents}} |
| `samples` | per `count.evidence.sample_points` point: nearest `cell_id`, `district_id`, `population`, `values` {`profile/category`: `count`, `class`, `deficit`} |

Any `fail` stops the pipeline before `publish`.

### `publish/manifest.json` *(implemented, P4)*

`outputs` name the loaded tables as `postgis:run_<id>.<table>` (plus `meta.data_sources`) with
their row counts.

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v0.1 | 2026-11-02 | First draft: `meta`, run schema, files, `manifest.json` | P1 scaffold (implementation plan §3) |
| v0.2 | 2026-11-02 | `data_sources.parquet`, `validate` layers and report part 1 | P2 acquire + validate |
| v0.3 | 2026-11-02 | `cells` = all populated cells inside the city boundary; routing area around the city; report coverage keys (`scored_share`, `excluded_by_district`, …) | Architecture v0.12, O11 |
| v0.4 | 2026-11-03 | `tiles/` and `count/` files (`access_counts`, `transit_supply`, `stops` with `weekday_departures`, reports); `nearest_min` only within the budget | P3 tiles + count |
| v0.5 | 2026-11-04 | Roles, `meta` and run schema implemented (`infra/db/`); `meta.schema_migrations`; `profiles.costing_options` = options as sent to Valhalla; FKs of `access_counts`/`transit_supply`; `district_scores` details; `score/`, report part 2 and `publish` manifest files | P4 score + publish + cleanup |
| v0.6 | 2026-11-05 | API responses (read and live endpoints, errors, ETag, snapping) | P5 API |
