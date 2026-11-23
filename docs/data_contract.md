# Data contract — reach

> **Status:** v1.0.1 draft (21 Nov 2026). Binding for the tables, files and API responses exchanged
> between pipeline and API once a step implements them; every change needs confirmation
> (AGENTS.md) and a data-contract test. Parts carried over from the archive are marked *(ported,
> S0.4)*; result tables and API responses are *(planned, S1.4)*.

## Conventions

- Geometries: PostGIS `geometry(<type>, 25832)`; GeoParquet with CRS EPSG:25832. The API
  transforms to EPSG:4326 at query time.
- Travel times stored as whole seconds (`integer`); the API returns minutes where it displays
  them. Distances in metres, timestamps `timestamptz` in UTC.
- Keys from the config: `mode` = key under `routing_profiles`, `destination_type` = key under
  `destination_types`, `trip_window` = key under `trip_windows` (`config/config.yaml`).
- `cell_id` = Zensus `GITTER_ID_100m` (EPSG:3035 grid id, e.g. `CRS3035RES100mN2822200E4250500`).
- Derived values (fit, rankings, reasons) are never stored; the API computes them (O4).

## Roles *(ported, S0.4: `infra/db/roles.sql`)*

| Role | Rights |
|---|---|
| `pipeline_write` | `publish`/`cleanup`: creates and drops `run_<id>` schemas, owns the `current` views, writes `meta.runs` and `meta.data_sources` |
| `app_read` | API: `SELECT` on `current.*`, `meta.runs`, `meta.data_sources` |
| `supervisor_read` | `SELECT` on `current.*`, `meta.*` and every `run_<id>` schema — **[VERIFY]** whether the course requires it (A5) |

Roles, passwords (from `.env`) and migrations are applied by `make migrate` as the superuser
(`DATABASE_URL_ADMIN`).

## Schema `meta` *(ported, S0.4: `infra/db/migrations/0001_meta.sql`)*

### `meta.runs`

| Column | Type | Null | Description |
|---|---|---|---|
| `run_id` | `text` PK | no | `YYYYMMDDTHHMMSSZ` |
| `started_at` | `timestamptz` | no | Pipeline start |
| `finished_at` | `timestamptz` | yes | Set at publish |
| `status` | `text` | no | `running`, `published`, `failed` |
| `osm_snapshot` | `timestamptz` | yes | Timestamp of the OSM extract |
| `gtfs_valid_from`, `gtfs_valid_to` | `date` | yes | Feed validity |
| `reference_weekday` | `date` | yes | Archive column; until S1.4 replaces it with the reference dates of the trip windows (migration), `publish` writes the earliest of them |
| `config_hash` | `text` | no | SHA-256 of the merged pipeline config (all sections except `api`) |

### `meta.data_sources`

| Column | Type | Null | Description |
|---|---|---|---|
| `run_id` | `text` FK → `runs` | no | |
| `source` | `text` | no | `osm`, `gtfs`, `zensus`, `zensus_rent`, `elevation` |
| `url` | `text` | no | Download URL |
| `retrieved_at` | `timestamptz` | no | |
| `checksum` | `text` | no | SHA-256 of the downloaded file |
| `licence` | `text` | no | From config |

PK (`run_id`, `source`); rows are deleted with their run (`ON DELETE CASCADE`).

### `meta.schema_migrations`

| Column | Type | Null | Description |
|---|---|---|---|
| `version` | `text` PK | no | File name of an applied migration without `.sql` |
| `applied_at` | `timestamptz` | no | |

## Schema `run_<id>` and views `current.*` *(subset ported, S0.4; rest planned, S1.4)*

`current.<name>` is a view on `run_<id>.<name>` of the latest published run; `publish` replaces all
of them in one transaction (`infra/db/run_schema.sql`).

**Ported in S0.4** (checked by `pipeline/tests/test_db_contract.py`; columns may still grow in
S1.4):

| Table | Columns |
|---|---|
| `cells` | `cell_id` PK `text`, `population` `integer` ≥ 0, `district_id` `text` (null = no district), `geom` `Polygon`, `origin_geom` `Point` |
| `districts` | `district_id` PK `text` (OSM id, e.g. `r2830772`), `name` `text`, `admin_level` `smallint`, `geom` `MultiPolygon` |
| `stops` | `stop_id` PK `text`, `name` `text`, `geom` `Point` |
| `validation_report` | `check` `text`, `stage` `text`, `status` `text` (`ok`/`warn`/`fail`), `value` `double precision`, `message` `text`; PK (`stage`, `check`) |

Proposed tables (columns are fixed in S1.4):

| Table | Grain | Content |
|---|---|---|
| `cells` | origin cell | `cell_id`, `origin_kind` (`populated`/`address`), `population`, `district_id`, `rent_eur_m2` + flag (optional), `geom`, `origin_geom` |
| `districts` | area | `district_id`, `name`, `admin_level`, `geom` |
| `destination_types` | type | key, labels (DE/EN), defaults from config |
| `destinations` | destination | `destination_id`, `destination_type`, `name`, `geom`, informative tags |
| `campus_sites` | campus site | `site_id`, name, programmes, `geom` |
| `addresses` | address | street, house number, postcode, `cell_id`, `geom` (search index) |
| `stops` | GTFS stop | `stop_id`, `name`, `geom` |
| `stop_departures` | stop × trip window | departures per hour, first/last departure |
| `trip_windows` | trip window | key, reference date, time, direction |
| `travel_times` | cell × destination × mode × trip window | `time_s`; for transit the legs (access, wait, in-vehicle, transfers, egress) and the first stop |
| `validation_report` | check | `check`, `stage`, `status` (`ok`/`warn`/`fail`), `value`, `message` |

## API responses *(planned, S1.4/S1.10)*

Errors: `{"detail": …}` with 404, 422, 429 (`Retry-After`), 502/503/504. Coordinates
`[lon, lat]` in EPSG:4326. Bodies of `POST /api/fit` and the cell, place and route endpoints are
fixed in S1.4.

## Files (`data/runs/<run_id>/<stage>/`)

### `manifest.json` *(ported, S0.4: `reach_pipeline.manifest.Manifest`)*

| Field | Type | Description |
|---|---|---|
| `stage` | string | Stage name |
| `run_id` | string | `YYYYMMDDTHHMMSSZ` |
| `status` | `"ok"` \| `"failed"` | |
| `started_at`, `finished_at` | ISO 8601 UTC | |
| `runtime_s` | number | Wall time |
| `peak_rss_mb` | number | Peak RSS of the process (or its largest child) |
| `inputs` | list of {`path`, `sha256`} | Files read; first entry `config:<section>,…` = digest of the config sections the stage uses |
| `outputs` | list of {`path`, `rows`} | Files written (`rows` null if not tabular) |
| `message` | string | Summary or error |

### `acquire/data_sources.parquet` *(ported, S0.4)*

One row per source: the columns of `meta.data_sources` plus `checked_at`, `path` (file in
`data/raw/<run_id>/<source>/`), `etag`, `last_modified`, `md5` and `reused` (unchanged and
hard-linked from the previous run).

### `validate/` and `tiles/` *(ported, S0.4)*

`validate/`: `cells`, `districts`, `stops` and `routing_area` as GeoParquet (EPSG:25832, columns as
in the tables above), `routing.osm.pbf` (input of the tile build) and report part 1
(`report_inputs.json` + `.md`: summary incl. the reference date per trip window, checks `crs`,
`non_empty`, `district_coverage`, `population_total`, `origin_coverage`, `cells_inside_boundary`,
`gtfs_trip_windows`, `holiday_calendar`). `tiles/`: `rebuild_needed` (shell variables for the
build, written by `tiles check`) and `verify.json`.

### Other stage files *(planned, S1.6–S1.9)*

Destinations, campus sites, addresses, transit build, `travel_times/` and report part 2 are
specified with their steps.

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v1.0.1 draft | 2026-11-21 | S0.4: run-schema subset (`cells`, `districts`, `stops`, `validation_report`) and the `validate/` and `tiles/` files documented as ported; `meta.runs.reference_weekday` holds the earliest trip-window date until S1.4 | Port of the foundation (plan S0.4) |
| v1.0 draft | 2026-11-21 | New contract for the rebuild: conventions, roles, `meta` and manifest carried over from the archive (v0.17); result tables and API responses planned for S1.4 | Rebuild brief of 21 Nov 2026 |
