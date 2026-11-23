# Data contract — reach

> **Status:** v1.1 draft (23 Nov 2026). Binding for the tables, files and API responses exchanged
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

### Result tables — proposal of S1.4 (23 Nov 2026), waiting for the team's yes

Nothing below is built before the yes; `infra/db/run_schema.sql` and the data-contract tests follow
in S1.9. Size estimate for the city (≈ 1,700 populated + ≈ 530 address cells): `travel_times`
≈ 0.25 M rows, `transit_times` ≈ 0.2 M rows per transit mode (spike PR #79: 193,897 pairs).

| Table | Grain / key | Columns |
|---|---|---|
| `cells` (extended) | PK `cell_id` | as above, plus `origin_kind` `text` (`populated`/`address`, A1); `population` 0 for address cells |
| `trip_windows` | PK `trip_window` | `reference_date` `date`, `time` `text` (`HH:MM`, local), `kind` `text` (`arrive_by`/`depart_at`), `direction` `text` (`to`/`back`) |
| `destination_types` | PK `destination_type` | `label_en`, `label_de` `text`, `trip_window` `text` → `trip_windows`, `nearest_k` `smallint` (null = all), `fine_time_min` `real`, `trips_per_week` `real` (onboarding defaults of this run's config) |
| `destinations` | PK `destination_id` (`<destination_type>/<osm id>`, e.g. `climbing/w123456`, or `campus_site/<site key>`) | `destination_type` `text`, `name` `text` (null if untagged), `osm_id` `text`, `tags` `jsonb` (informative: `opening_hours`, `website`, `operator`), `geom` `Point` (routing point; parks: one row per access point, same `osm_id`) |
| `campus_sites` | PK `site_id` (key in `config/campus.yaml`) | `name` `text`, `programmes` `text[]`, `destination_id` `text` → `destinations`, `geom` `Point` |
| `addresses` | PK `address_id` (OSM id) | `street`, `housenumber`, `postcode`, `city` `text`, `cell_id` `text` → `cells`, `geom` `Point`; trigram index on `street || ' ' || housenumber` for `GET /api/addresses` (needs `pg_trgm` in a migration) |
| `stops` | PK `stop_id` | as above |
| `stop_departures` | PK (`stop_id`, `trip_window`) | `departures_per_hour` `real` (in the hour after the window time), `first_departure`, `last_departure` `timestamptz` (service day of the reference date, beyond midnight correct) |
| `travel_times` | PK (`cell_id`, `destination_id`, `mode`) — walk and bike, independent of the window | `time_s` `integer`, `distance_m` `integer` |
| `transit_times` | PK (`cell_id`, `destination_id`, `mode`, `trip_window`) — `transit`, `bike_transit` | `time_s` `integer` (methodology §4, M6: includes the wait at home), `departure`, `arrival` `timestamptz`, `access_s`, `wait_s`, `in_vehicle_s`, `egress_s` `integer`, `transfers` `smallint`, `first_stop_id` `text` → `stops`, `first_route` `text`, `walk_only` `boolean` (true = no bus beats walking, legs null) |
| `validation_report` | PK (`stage`, `check`) | as above; part 2 (`validate_results`) adds its checks |

Rules: a missing row means "not computed" (outside the candidates); an unreachable pair is stored
with `time_s` null and is never confused with 0. Only the `2k` straight-line candidates per type
are routed; the API picks the minimum. Rent (`rent_eur_m2`) is added only if a legal source is
found (methodology §8).

## API responses — proposal of S1.4 (23 Nov 2026), waiting for the team's yes

Errors: `{"detail": …}` with 404, 422, 429 (`Retry-After`), 502/503/504. Coordinates
`[lon, lat]` in EPSG:4326. Every response carries `run_id` and the `ETag` of the run. Reasons are
**structured**; the web app turns them into DE/EN text, so wording never lives in the API.

| Endpoint | Request | Response (main fields) |
|---|---|---|
| `GET /api/destination-types` | – | `[{destination_type, label: {en, de}, trip_window, fine_time_min, trips_per_week}]` |
| `GET /api/campus-sites` | – | `[{site_id, name, programmes, point}]` |
| `GET /api/addresses?q=` | `q` ≥ 3 characters | up to 10 `[{label, cell_id, point}]` |
| `POST /api/fit` | student profile: `{programme, campus_days?: {site_id: days}, modes: [mode], destinations: {destination_type: {importance, fine_time_min?, trips_per_week?}}, area_level?: "district" \| "teilort"}` | `{run_id, areas: [{area_id, name, fit, best_cell_id, best_cell_fit, weekly_min, reasons}], cells: {cell_id: [fit, weekly_min]}}` sorted by `fit` |
| `GET /api/cell/{cell_id}` · `POST /api/cell/{cell_id}` | GET: no profile; POST: the same student profile as the body (never in a query string, because access logs keep query strings; rule 9) | `{cell_id, district, point, trips: [{destination_type, destination_id, name, mode, trip_window, minutes, legs?}], fit?, reasons?}` |
| live route (U2) | `POST /api/route` `{from: point, destination_id, mode, trip_window?}` | `{minutes, geometry (GeoJSON LineString), legs?}` — Valhalla for walk/bike, OTP for transit |

A **reason** is `{kind: "strength" | "weakness" | "reliability", destination_type, name, minutes,
mode, trip_window, value?}` (e.g. `reliability` with the last departure home). The fit formula is
methodology §6 (still [OPEN]); the API computes it from `travel_times` and `transit_times` at
request time and never stores it (O4).

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
| v1.1 draft | 2026-11-23 | S1.4 proposal (not yet confirmed): result tables with columns (walk/bike `travel_times` and transit `transit_times` split, legs per M6), API request/response shapes with structured reasons | Plan S1.4; T1 = OTP (O17) fixed the transit fields |
| v1.0 draft | 2026-11-21 | New contract for the rebuild: conventions, roles, `meta` and manifest carried over from the archive (v0.17); result tables and API responses planned for S1.4 | Rebuild brief of 21 Nov 2026 |
| v1.0.1 draft | 2026-11-21 | S0.4: run-schema subset (`cells`, `districts`, `stops`, `validation_report`) and the `validate/` and `tiles/` files documented as ported; `meta.runs.reference_weekday` holds the earliest trip-window date until S1.4 | Port of the foundation (plan S0.4) |
