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

## Listings *(PROPOSED, F4.1: not binding until the team confirms it)*

Daily listings job (architecture O24, §6.5, §7). Source: WG-Gesucht, public offers for Tübingen.
The job writes snapshot schemas `lst_<snapshot_id>` (`snapshot_id` = `YYYYMMDDTHHMMSSZ`);
`publish_listings` replaces the views `listings.*` on the latest snapshot in one transaction and
keeps the last `listings.keep_snapshots` snapshots. Roles: `pipeline_write` owns `lst_<id>` and
the `listings` views; `app_read` gets `SELECT` on `listings.*`. With `listings.enabled: false`
(config) the job does not run and the API answers listing requests with an empty list.

**Personal data** (column *PD*): listings are written by private people. Never stored: names or
initials of the author or flatmates, profile pictures, "member since", phone numbers, e-mail
addresses, messenger handles, links to social profiles, required documents. Reduced as marked
below. Raw HTML pages are parsed in memory during the run and deleted with the run directory;
they are not kept on the server.

### `lst_<id>.listings` (one row per listing in the snapshot)

| Column | Type | PD | Description and reduction |
|---|---|---|---|
| `listing_id` PK | `text` | | `wg_gesucht:<ad number>` |
| `source` | `text` | | `wg_gesucht` |
| `source_url` | `text` | | Canonical ad URL; the app links to it |
| `kind` | `text` | | `wg_room`, `studio` (1-room flat), `flat` |
| `title` | `text` | may | As published, contact data stripped (same rules as the excerpt), at most 120 characters |
| `rent_total_eur` | `integer` | | "Gesamtmiete" (warm, incl. utilities and other costs) |
| `rent_cold_eur` | `integer` | | "Miete" (cold) |
| `utilities_eur` | `integer` | | "Nebenkosten" |
| `other_costs_eur` | `integer` | | "Sonstige Kosten" |
| `deposit_eur` | `integer` | | "Kaution" |
| `transfer_fee_eur` | `integer` | | "Ablösevereinbarung" |
| `size_m2` | `real` | | Room size (`wg_room`) or flat size |
| `flat_size_m2` | `real` | | "Wohnungsgröße" of a WG |
| `rooms` | `real` | | Rooms of a `studio` (1) or `flat` |
| `household_size` | `smallint` | | "3er WG" = 3, incl. the free room |
| `flatmates_women`, `flatmates_men`, `flatmates_diverse` | `smallint` | yes | Counts only, as published |
| `flatmates_age_min`, `flatmates_age_max` | `smallint` | yes | Range as published ("Bewohneralter"); never per person |
| `looking_for_gender` | `text` | | `any`, `woman`, `man`, `diverse` |
| `looking_for_age_min`, `looking_for_age_max` | `smallint` | | As published |
| `wg_types` | `text[]` | | As published ("Studenten-WG", "Zweck-WG", …) |
| `languages` | `text[]` | | As published |
| `smoking` | `text` | | As published ("Rauchen nicht erwünscht", …) |
| `available_from` | `date` | | "frei ab"; "ab sofort" → `fetched_at` date |
| `available_to` | `date` | | "frei bis"; null = unlimited |
| `furnished` | `text` | | `none`, `partly`, `full`; null = not stated |
| `features` | `text[]` | | Normalised keys (see *Parser output*) |
| `district` | `text` | | District as published ("Tübingen Innenstadt" → `Innenstadt`) |
| `postcode` | `text` | | As published |
| `address_text` | `text` | yes | Street and house number as published; only used for geocoding and shown with the listing |
| `geocode_precision` | `text` | | `house`, `street`, `district` (methodology §8.1) |
| `geom` | `geometry(Point, 25832)` | | Geocoded point (`current.addresses`, step F4.5); for `district` the district's representative point |
| `source_point` | `geometry(Point, 25832)` | | Map marker of the ad page, informative only (V12 compares it with `geom`) |
| `image_urls` | `text[]` | yes | Links to the source images, never copied or proxied; loaded only when the student opens the listing |
| `description_excerpt` | `text` | may | First `listings.description_max_chars` characters of the free text, phone numbers, e-mail addresses, URLs and messenger handles replaced by `[…]` |
| `online_since` | `timestamptz` | | From "Online: 10 Stunden" or a date relative to `fetched_at`; hour or day precision |
| `first_seen`, `last_seen` | `timestamptz` | | First and last snapshot that contained the listing |
| `fetched_at` | `timestamptz` | | Time the detail page was fetched |
| `parse_warnings` | `text[]` | | Fields that could not be read (`unknown:<field>`) |

**Retention:** a listing missing from the search pages is kept with its `last_seen` for
`listings.retention_days` days and then left out of the next snapshot; older snapshots are
dropped by `publish_listings`. Nothing about a removed listing survives the last kept snapshot.

### `lst_<id>.listing_travel_times`

One row per listing × destination × mode × trip window, raw seconds (O4); same columns and rules
as `travel_times` (S1.4) with `listing_id` instead of `cell_id`, plus `approximate` `boolean`
(true for `street` precision). Destinations: the nearest k per destination type and per offered
label and all campus sites (architecture §6.5). Listings with `district` precision have no rows;
the API uses the district's cell values and says so.

### `lst_<id>.listing_report`

V12 checks, same columns as `validation_report` (`stage` = `listings_validate`): parse share,
geocode precision shares, distance `geom` ↔ `source_point`, freshness.

### Parser output *(F4.2)*

One field spec for both parsers (Python `reach_pipeline.listings.parse` for the job,
TypeScript `web/src/listings/extract.ts` for the import in the browser, F4.3). JSON object with
the columns of `listings` except `geom`, `geocode_precision`, `first_seen`, `last_seen`, plus:

| Field | Type | Description |
|---|---|---|
| `source_lat`, `source_lon` | number \| null | Map marker of the page (EPSG:4326) |
| `online_text` | string \| null | Raw "Online:" value; `online_since` needs `fetched_at` |
| `warnings` | string[] | `unknown:<field>` for every field that is missing or unreadable |
| `errors` | string[] | `no_address` (no street and no district), `not_an_ad` (page structure not recognised) |

A page with errors yields a partial result, never an exception. Feature keys: `washing_machine`,
`dishwasher`, `balcony`, `terrace`, `garden`, `cellar`, `bike_cellar`, `lift`, `internet`,
`own_kitchen`, `own_bathroom`, `parking`, `pets_allowed`, `barrier_free`; unknown entries are
kept as `other:<text>`.

**Variant C (import in the browser, F4.3):** the same object stays in the URL hash and
`localStorage`; only the address text reaches the server (POST address search) and, after
geocoding, the point (`POST /api/place`). Nothing of it is stored on the server.

### Files (`data/listings/<snapshot_id>/<stage>/`)

`listings_acquire/`: `pages.parquet` (`listing_id`, `kind`, `url`, `search_hash`, `status`,
`fetched_at`; the HTML stays in memory, see above) and a manifest. `listings_validate/`:
`listings.parquet` (GeoParquet, EPSG:25832, columns of `listings`) and `report.json` + `.md`.
`listings_travel_times/`: `listing_travel_times.parquet`. All with `manifest.json` as above.

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| proposed (F4.1) | 2026-11-27 | Listings: schema `lst_<id>` (`listings`, `listing_travel_times`, `listing_report`), views `listings.*`, retention, personal-data reductions, parser output, variant C, files | Extension plan F4.1, architecture O24/O25; version bump once the team confirms |
| v1.0.1 draft | 2026-11-21 | S0.4: run-schema subset (`cells`, `districts`, `stops`, `validation_report`) and the `validate/` and `tiles/` files documented as ported; `meta.runs.reference_weekday` holds the earliest trip-window date until S1.4 | Port of the foundation (plan S0.4) |
| v1.0 draft | 2026-11-21 | New contract for the rebuild: conventions, roles, `meta` and manifest carried over from the archive (v0.17); result tables and API responses planned for S1.4 | Rebuild brief of 21 Nov 2026 |
