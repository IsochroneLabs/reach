# Data contract — reach

> **Status:** draft v0.3 (2 Nov 2026), from `implementation_plan.md` §3. Binding for the tables
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

## Schema `meta` *(planned, P4)*

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

PK (`run_id`, `source`).

## Schema `run_<id>` and views `current.*` *(planned, P4)*

`current.<name>` is a view on `run_<id>.<name>` of the latest published run.

| Table / view | Grain | Columns (type, null) | Key |
|---|---|---|---|
| `cells` | scored census cell | `cell_id` text, `population` integer, `district_id` text null, `geom` Polygon, `origin_geom` Point | `cell_id` |
| `districts` | district | `district_id` text, `name` text, `admin_level` smallint, `geom` MultiPolygon | `district_id` |
| `urban_boundary` | urban part | `part_id` integer, `name` text null, `geom` MultiPolygon | `part_id` |
| `facilities` | facility | `facility_id` text (`n123`/`w456`/`r789`), `category` text, `name` text null, `geom` Point | (`facility_id`, `category`) |
| `facility_points` | routing point of a facility | `facility_id` text, `point_id` integer, `kind` text (`node`, `representative`, `access`), `geom` Point | (`facility_id`, `point_id`) |
| `stops` | GTFS stop | `stop_id` text, `name` text, `weekday_departures` integer, `geom` Point | `stop_id` |
| `profiles` | profile | `profile_id` text, `costing` text, `costing_options` jsonb, `speed_kmh` double, `time_budget_min` double | `profile_id` |
| `access_counts` | cell × category × profile | `cell_id` text, `category` text, `profile_id` text, `count` integer, `nearest_min` double null | (`cell_id`, `category`, `profile_id`) |
| `transit_supply` | cell × walking/wheelchair profile | `cell_id` text, `profile_id` text, `departures` integer, `stops_count` integer, `nearest_stop_min` double null | (`cell_id`, `profile_id`) |
| `thresholds` | category or transit class | `category` text (`transit` for transit classes), `k` integer null, `class` text null, `lower` integer null, `upper` integer null | unique (`category`, `class`) `NULLS NOT DISTINCT` (`class` is null on category rows, so no PK) |
| `scores` (view) | cell × category × profile | `access_counts` columns + `class` text (`lack`, `insufficient`, `sufficient`), `deficit` double | as `access_counts` |
| `transit_scores` (view) | cell × profile | `cell_id`, `profile_id`, `class` text (`lack`, `insufficient`, `medium`, `high`) | (`cell_id`, `profile_id`) |
| `district_scores` (mat. view) | district × category × profile | `share_lack`, `share_insufficient`, `share_sufficient` double, `deficit_sum` double, `residents_lack` integer | (`district_id`, `category`, `profile_id`) |
| `recommendations` *(P7)* | candidate × category × profile | `rank` integer, `population_gain` double, `geom` Polygon | (`category`, `profile_id`, `rank`) |
| `validation_report` | check | `check` text, `stage` text, `status` text (`ok`, `warn`, `fail`), `value` double null, `message` text | (`stage`, `check`) |

`cells.cell_id` is the Zensus `GITTER_ID_100m` (EPSG:3035 grid id, e.g. `CRS3035RES100mN2822200E4250500`; verified 2 Nov 2026);
the `cells` table holds only scored cells (C12): every populated cell whose centre lies inside the
city boundary (architecture O11). Facilities are counted once per facility id,
with the minimum time over their points.

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
| `stops.parquet` | `stop_id`, `name`, `geometry` | `weekday_departures` is added in P3 (`count`) |
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

The Markdown file renders the same content. Part 2 (`validate_results`) follows in P4.

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v0.1 | 2026-11-02 | First draft: `meta`, run schema, files, `manifest.json` | P1 scaffold (implementation plan §3) |
| v0.2 | 2026-11-02 | `data_sources.parquet`, `validate` layers and report part 1 | P2 acquire + validate |
| v0.3 | 2026-11-02 | `cells` = all populated cells inside the city boundary; routing area around the city; report coverage keys (`scored_share`, `excluded_by_district`, …) | Architecture v0.12, O11 |
