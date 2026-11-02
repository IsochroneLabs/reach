# Data contract — reach

> **Status:** draft v0.1 (2 Nov 2026), from `implementation_plan.md` §3. Binding for the tables
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
| `thresholds` | category or transit class | `category` text (`transit` for transit classes), `k` integer null, `class` text null, `lower` integer null, `upper` integer null | (`category`, `class`) |
| `scores` (view) | cell × category × profile | `access_counts` columns + `class` text (`lack`, `insufficient`, `sufficient`), `deficit` double | as `access_counts` |
| `transit_scores` (view) | cell × profile | `cell_id`, `profile_id`, `class` text (`lack`, `insufficient`, `medium`, `high`) | (`cell_id`, `profile_id`) |
| `district_scores` (mat. view) | district × category × profile | `share_lack`, `share_insufficient`, `share_sufficient` double, `deficit_sum` double, `residents_lack` integer | (`district_id`, `category`, `profile_id`) |
| `recommendations` *(P7)* | candidate × category × profile | `rank` integer, `population_gain` double, `geom` Polygon | (`category`, `profile_id`, `rank`) |
| `validation_report` | check | `check` text, `stage` text, `status` text (`ok`, `warn`, `fail`), `value` double null, `message` text | (`stage`, `check`) |

`cells.cell_id` is the Zensus `GITTER_ID_100m` (EPSG:3035 grid id, column name verified in P2);
the `cells` table holds only scored cells (C12). Facilities are counted once per facility id,
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
| `peak_rss_mb` | number | Max RSS of the process or its largest child, MB |
| `inputs` | list of {`path`, `sha256`} | Files read, with checksums |
| `outputs` | list of {`path`, `rows` (null if not tabular)} | Files written |
| `message` | string | Summary or error message |

Validation reports (`report_inputs.json` + Markdown, part 2 in `validate_results`) are specified
in P2/P4.

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v0.1 | 2026-11-02 | First draft: `meta`, run schema, files, `manifest.json` | P1 scaffold (implementation plan §3) |
