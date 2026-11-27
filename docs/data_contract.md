# Data contract — reach

> **Status:** v1.2.0 draft (27 Nov 2026). Binding for the tables, files and API responses exchanged
> between pipeline and API once a step implements them; every change needs confirmation
> (AGENTS.md) and a data-contract test. Parts carried over from the archive are marked *(ported,
> S0.4)*; result tables and API responses are fixed in S1.4 (pre-approved by Juju on 27 Nov 2026, review
> in the PR).

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

## Schema `run_<id>` and views `current.*` *(S1.4, implemented in S1.9: `infra/db/run_schema.sql`)*

`current.<name>` is a view on `run_<id>.<name>` of the latest published run; `publish` replaces all
of them in one transaction. Raw values only: the fit, rankings and reasons are derived by the API
(AGENTS.md rule 5). Checked by `pipeline/tests/test_db_contract.py`.

| Table | Columns |
|---|---|
| `cells` | `cell_id` PK `text` (Zensus id), `population` `integer` ≥ 0, `populated` `boolean` (false = address cell, arch. O13: routed, never ranked), `district_id` `text` (null = no district), `geom` `Polygon`, `origin_geom` `Point` |
| `districts` | `district_id` PK `text` (OSM id, e.g. `r2830772`), `name` `text`, `admin_level` `smallint`, `geom` `MultiPolygon` |
| `destination_types` | `destination_type` PK `text`, `label_en`, `label_de` `text`, `source` `text` (`osm`/`campus`/`labels`), `trip_window` `text`, `fine_time_min` `real`, `trips_per_week` `real`, `nearest_k` `smallint` (null = all) |
| `destinations` | `destination_id` PK `text` (`<type>:<osm_id>`, campus `<type>:<key>`), `destination_type` `text`, `name` `text` (`''` if unnamed), `osm_id` `text`, `geom` `Point` (first routing point; parks are routed from all their access points and keep the shortest time) |
| `destination_labels` | as `validate/destination_labels.parquet` below; `destination_id` PK, `osm_ids` `text`, `n_features` `integer`, `offered` `boolean`, `geom` `Point` |
| `campus_sites` | `site_id` PK `text` (key in `config/campus.yaml`), `name` `text`, `default_share` `real` (0 if not in `default_mix`), `geom` `Point`; destination id `campus_site:<site_id>` |
| `programmes` | `programme` PK `text`, `label_en`, `label_de` `text`, `sites` `text[]`, `shares` `double precision[]` NULL (per site, from Alma, N24; NULL = equal weights) |
| `addresses` | `address_id` PK `integer`, `label` `text` (`Street 5, 72074 Tübingen`), `street`, `housenumber`, `postcode`, `city` `text`, `residential` `boolean`, `cell_id` `text` (origin cell containing the point, null outside), `geom` `Point` |
| `stops` | `stop_id` PK `text`, `name` `text`, `geom` `Point` |
| `stop_departures` | `stop_id` `text`, `trip_window` `text`, `departures` `integer` (boardable departures in the `reliability_window_min` after the window time, before it for arrive-by; night trips of the previous service day count); PK (`stop_id`, `trip_window`) |
| `trip_windows` | `trip_window` PK `text`, `weekday` `text`, `time` `text` (`HH:MM`), `kind` `text` (`depart_at`/`arrive_by`), `direction` `text` (`to`/`back`), `reference_date` `date` |
| `travel_times` | see below |
| `validation_report` | `check` `text`, `stage` `text`, `status` `text` (`ok`/`warn`/`fail`), `value` `double precision`, `message` `text`; PK (`stage`, `check`) |

**`travel_times`**: one row per origin cell × destination × mode × trip window (meth. §4). The
window is the one of the destination's type (labels: of their type; `direction = back` routes
from the destination to the cell). The targets are those of `targets.py` (nearest k per type and
per offered label, all campus sites; transit `transit_candidate_factor` × k).

| Column | Type | Description |
|---|---|---|
| `cell_id` | `text` | origin cell |
| `destination_id` | `text` | a `destinations` or a `destination_labels` id |
| `mode` | `text` | `walk`, `bike`, `transit`, `bike_transit` |
| `trip_window` | `text` | |
| `time_s` | `integer` | door to door incl. the wait at home (M6); null = no route; transit never above walk (then `walk_only`) |
| `access_s`, `wait_s`, `in_vehicle_s`, `egress_s` | `integer` | transit legs (null for walk/bike); `wait_s` includes waits at transfers |
| `transfers` | `smallint` | |
| `first_stop`, `first_route` | `text` | name of the first boarding stop, short name of its route |
| `departure` | `text` | `HH:MM` the student leaves (night window: the departure that gets them home) |
| `walk_only` | `boolean` | transit answer was a walk (no vehicle faster) |

PK (`cell_id`, `destination_id`, `mode`, `trip_window`); index on `destination_id`.

## API responses *(S1.4, implemented in S1.10)*

Errors: `{"detail": …}` with 404, 422, 429 (`Retry-After`), 502/503/504. Coordinates
`[lon, lat]` in EPSG:4326. Minutes are rounded to whole minutes. POST bodies are never logged
(rule 9); the address query is a POST for the same reason. Shapes match `web/src/api/types.ts`.

| Endpoint | Response |
|---|---|
| `GET /api/health` | `{status, version, build_sha}` |
| `GET /api/meta` | `{run_id, sources: [{source, date, valid_to?}], trip_windows: [TripWindow], bounds: [[w, s], [e, n]], modes}` |
| `GET /api/destination-types` | `[{destination_type, label: {en, de}, trip_window, fine_time_min, trips_per_week, labels?: [{label, kind, name: {en, de}, destinations}]}]`; `labels` lists offered labels (grocery brands and groups, sport and hobby categories) |
| `GET /api/label-destinations` | `[{destination_id, destination_type, labels: [label], name, point}]` |
| `GET /api/campus-sites` | `[{site_id, name, programmes: [programme], point, default_share}]` |
| `GET /api/programmes` | `[{programme, label: {en, de}, sites, shares?}]` (`shares` per site when Alma gave them) |
| `GET /api/personas` | `[{persona, label: {en, de}, profile: FitRequest}]` from `config/personas.yaml` |
| `POST /api/addresses/search` `{q}` | `[{label, cell_id, point}]`, at most `api.address_search.limit`, origin cells only |
| `POST /api/fit` `FitRequest` | `{run_id, areas: [Area], cells: {cell_id: [fit, weekly_min, populated]}}` |
| `POST /api/cell/{cell_id}` `FitRequest` | `{cell_id, district, point, populated, trips: [Trip], fit, weekly_min, reasons: [Reason], fit_parts: [FitPart]}` |
| `POST /api/place` `{point: [lon, lat], profile: FitRequest}` | same shape as `/api/cell/{id}` with `point` = the given point (F4.5) |

**Point routing (F4.5):** the nearest k destinations per chosen type and label and all campus
sites, selected in `current` with `ORDER BY geom <-> point` in EPSG:25832; walk and bike as one
Valhalla `sources_to_targets` matrix per mode, transit and bike + transit as one OpenTripPlanner
query per target and trip window (bounded concurrency, transit capped by walking). The fit is
derived from these times with the same code as `/api/cell`; nothing is cached (O25). 404 when the
point is outside the published cells, 422 for an empty profile or no route, 503 when an engine is
unavailable. `/api/cell/{id}` keeps the cell values (fast) for the map and the Check list.

**FitRequest** (the student profile): `programme` (null = `default_mix`), `campus_days`
(`site_id` → days per week, optional), `modes` (≥ 1), `destinations` (key = destination type or
`sport:<category>` / `hobby:<category>` → `{importance 0–3, fine_time_min?, trips_per_week?}`),
`labels.grocery` (favourite brands/groups, empty = any), `area_level` (`district`).

**Fit** (meth. §6): per term the best mode the student selected; *s* = 1 / (1 + (T / (a·t))^p)
with `api.fit.a`, `api.fit.p`; fit = 100 · Σ w·s / Σ w (null if Σ w = 0); campus term = mean of
the site times weighted by `campus_days`, else equally over the programme's sites, else
`default_mix`; grocery with favourites = the nearest of those labels; categories = their label
destinations; weekly time = Σ trips_per_week · 2 · T over the non-category terms. **Area**:
`{area_id, name, fit (median of populated cells), best_cell_id, best_cell_fit, weekly_min
(median), reasons}`, sorted by fit. **Reason**: `{kind (strength/weakness/reliability),
destination_type, name, minutes, mode, trip_window, value?}`: up to 2 strengths with *s* ≥ 0.75,
1 weakness with *s* < 0.6, for night windows by transit the departure home; 2–4 reasons.
**Trip**: `{destination_type, destination_id, name, mode, trip_window, minutes, legs?:
{access_min, wait_min, in_vehicle_min, egress_min, transfers, first_stop, first_route, walk_only,
last_departure}}`. **FitPart**: `{destination_type, minutes, mode, score, weight, share}`.

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
`gtfs_trip_windows`, `holiday_calendar`, `destination_labels`). `tiles/`: `rebuild_needed` (shell
variables for the build, written by `tiles check`) and `verify.json`.

### `validate/destination_labels.parquet` *(F2.2, draft)*

GeoParquet, EPSG:25832, one row per destination **and label** (methodology §3.1: clustering is per
label, so a sports centre with climbing and fitness is one row in each category). Written when
`destination_labels` is configured; S1.6 links it to `destinations`, F2.4 publishes it.

| Column | Type | Description |
|---|---|---|
| `destination_id` | string | `<destination_type>:<label>:<osm_id>` of the largest feature of the cluster; unique |
| `destination_type` | string | `grocery`, `sport`, `hobby`, `place_of_worship` |
| `label_kind` | string | `brand` or `group` (grocery), `category` (sport, hobby), `religion` |
| `label` | string | key in `config.destination_labels` (religion: the OSM value, `unknown` if missing) |
| `name` | string | name of the largest named feature, `""` if none |
| `n_features` | integer | OSM objects merged into this destination |
| `osm_ids` | string | `;`-separated `n…`/`w…`/`r…` ids, sorted |
| `offered` | boolean | label has ≥ `min_destinations` destinations (brands: ≥ `brand_min_stores`) |
| `geometry` | Point | inside the largest feature of the cluster |

Report part 1 lists destinations and features per label (`summary.destination_labels`); check
`destination_labels` (V10) fails without any supermarket and warns with the configured labels that
are not offered.

### `validate/` files of S1.6

GeoParquet (EPSG:25832) unless noted: `destinations` (columns of the table plus `point_id`,
unique: parks have one row per access point), `addresses` (columns of the table without
`cell_id`), `stop_departures` (Parquet), and `cells` with `populated`. Report part 1 adds the
checks `destinations` (fails if a type has none), `campus_match` (warns if a campus point lies
farther than `match_radius_m` from a university feature), `addresses`, `stop_departures` and the
summary entries `destinations`, `campus_match_m`, `addresses`, `address_cells`.

### `transit/` *(S1.7)*

`gtfs/` (the feed clipped to the stops in the routing area), `osm.pbf` (link to
`validate/routing.osm.pbf`), `build-config.json`, `router-config.json` and `graph.obj`, built by
the one-shot OTP container.

### `travel_times/` *(S1.8)*

`travel_times.parquet` (columns of the table), `pairs.parquet` (the targets: `cell_id`,
`destination_id`, `distance_m`, `groups`), `report.json` (pairs, rows per mode, unreachable
share, runtime and peak memory per mode).

### `validate_results/` *(S1.9)*

`report_results.json` + `.md` (report part 2, V2/V3 checks).

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

### API *(F4.6)*

`GET /api/listings` → array of the current snapshot: the contract columns except the internal ones,
plus `point` (EPSG:4326) and `approximate` (true until F4.5 point routing). `POST /api/listings/fit`
takes the profile body of `/api/fit` and returns the same array plus `fit` and `weekly_min` of the
listing's cell, best fit first. Both read `listings.listings` only; image URLs are returned as
links, never proxied.

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
| proposed (F4.5) | 2026-11-27 | `POST /api/place` (point → nearest targets, walk/bike matrix, transit per window, fit from point times, no cache) | F4.5, architecture O25, V11 |
| proposed (F4.6) | 2026-11-27 | API of the current listings (`GET /api/listings`, `POST /api/listings/fit`, fit from the cell until F4.5) | F4.6 built on the F4.1 proposal |
| proposed (F4.1) | 2026-11-27 | Listings: schema `lst_<id>` (`listings`, `listing_travel_times`, `listing_report`), views `listings.*`, retention, personal-data reductions, parser output, variant C, files | Extension plan F4.1, architecture O24/O25; version bump once the team confirms |
| v1.1.0 draft | 2026-11-27 | S1.4: all run-schema tables (`cells.populated`, destinations, labels, campus sites, programmes, addresses, stop departures, trip windows, travel times with transit legs) and all API responses after `web/src/api/types.ts`; `validate/` files of S1.6, `transit/`, `travel_times/`, `validate_results/` | Phase 1 core built by Juju's session (decision of 27 Nov 2026: "nothing depends on Rico"); the web client already uses these shapes on fixtures |
| v1.2.0 draft | 2026-11-27 | `programmes.shares` (site shares from the Alma reference week) and `shares?` in `GET /api/programmes` | F3.3/F3.4: the campus time of a programme is weighted by its session hours per site (notes N24) |
| v1.0.2 draft | 2026-11-27 | `validate/destination_labels.parquet` and check `destination_labels` (V10) | F2.2 (extension plan) |
| v1.0.1 draft | 2026-11-21 | S0.4: run-schema subset (`cells`, `districts`, `stops`, `validation_report`) and the `validate/` and `tiles/` files documented as ported; `meta.runs.reference_weekday` holds the earliest trip-window date until S1.4 | Port of the foundation (plan S0.4) |
| v1.0 draft | 2026-11-21 | New contract for the rebuild: conventions, roles, `meta` and manifest carried over from the archive (v0.17); result tables and API responses planned for S1.4 | Rebuild brief of 21 Nov 2026 |
