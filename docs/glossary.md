# Glossary

Project vocabulary used in code, docs, issues and prompts. People and roles ("you", "your human",
"the team") are defined in [`AGENTS.md`](../AGENTS.md). Use these terms consistently; a term that
is not here is either plain English or needs an entry first.

## Product

| Term | Meaning |
|---|---|
| **student** | The only user: a student moving to Tübingen who does not know the city yet (first semester, master's, exchange). |
| **student profile** | The user's preferences (programme, modes, destinations, importance, trips per week, fine times). Starts as the default profile and is edited in the profile panel. Lives only in the browser (URL and `localStorage`), never stored on the server. |
| **default profile** | The profile the app opens with before the user changes anything; without a programme it uses the default campus mix (`docs/product.md`). |
| **profile panel** | The panel next to the map (bottom sheet on mobile) where the student edits the profile; replaces the onboarding questionnaire of product v1.0. |
| **persona** | A predefined student profile for demos and tests, offered as "example profiles" in the profile panel (`config/personas.yaml`). |
| **place** | A point the user checks (address or pin, *Check*); answered with the values of its cell. |
| **area** | Readable unit for ranking and reasons: an official district of the core town or a Teilort (OSM admin levels 11 and 9). The map colours the cells inside it. |
| **Find** | Mode: the map of cell fits and the best areas with reasons for the student profile (was U1). |
| **Check** | Mode: fit, trips and rank of one place, or up to three places side by side (was U2 + U3). |
| **listing rent** | Rent the student types in for a place in *Check*; kept in the browser, shown and compared, never part of the fit. |
| **U1 / U2 / U3** | Use cases of product v1.0, replaced by *Find* (U1) and *Check* (U2 + U3) in v1.1. Still used in older docs. |
| **reason** | One of the 2–4 plain-language facts that drive a result, e.g. "Morgenstelle 12 min by bus at 8:00". |

## Model

| Term | Meaning |
|---|---|
| **cell** | One Zensus 2022 100 m grid cell; `cell_id` = original EPSG:3035 grid id (`CRS3035RES100mN…E…`). |
| **origin** | Routing start point of a cell (the cell centroid). |
| **origin kind** | Why a cell is routed: `populated` (residents in the Zensus grid) or `address` (no residents, but an OSM residential address); rankings use populated cells only. |
| **destination** | A place the student travels to (a campus site, a Mensa, a supermarket, a climbing gym, …). |
| **destination type** | Group of destinations with one meaning for the student: `campus_site`, `mensa`, `grocery`, `climbing`, … (`config/config.yaml`, `docs/osm_tagging.md`). |
| **campus site** | University location from the manual table `config/campus.yaml`; a programme maps to one or more sites. |
| **mode** | How the student travels: `walk`, `bike`, `transit`, optionally `bike_transit` (bike to a stop, park, ride, walk). No car. |
| **routing profile** | A mode with its settings (speed, costing options, engine), e.g. `walk` = Valhalla `pedestrian` at 5.0 km/h. |
| **trip window** | When a trip happens: weekday, reference date, time and direction (e.g. arrive at campus by 8:10 on a Tuesday; return home after 0:30 on a Friday night). Defined in `config/config.yaml`. |
| **reference date** | The calendar date a trip window is evaluated on: a regular day inside the GTFS validity that is no public or school holiday. |
| **travel time** | Door-to-door time of one trip in one mode and trip window; for transit: walk to the stop + wait + ride + transfers + walk to the destination. Stored raw. |
| **transit legs** | The parts of a transit travel time (access walk, wait, in-vehicle, transfers, egress walk); used for reasons. |
| **departures** | Scheduled departures per hour at a stop in a trip window (GTFS); basis of "is the bus reliable at that time". Schedule only, no delay data. |
| **nearest k** | The pipeline stores travel times to the `k` nearest destinations per destination type (all campus sites always). |
| **fit** | How well a place matches a student profile, 0–100, computed by the API at request time from stored travel times (`docs/methodology.md`, formula **[OPEN]**). |
| **fine time** | The travel time a student says feels fine for a destination type; the fit decays smoothly around it (no hard cut-off). |
| **importance** | How much a destination type matters to the student (weight in the fit). |
| **weekly travel time** | Estimated minutes per week: trips per week × travel time per trip, summed over destination types. Second, intuitive measure next to the fit. |
| **rent** | Zensus 2022 average net cold rent per m² on the 100 m grid (rented flats in residential buildings, no student halls); shown only where published, always labelled. |

## Data and pipeline

| Term | Meaning |
|---|---|
| **city boundary** | Administrative boundary of Tübingen (OSM `admin_level` 8, AGS `08416041`). |
| **routing area** | City boundary plus the routing buffer; the OSM extract, destinations and stops are clipped to it. |
| **routing buffer** | Distance around the city boundary (4 km) so trips can leave the city. |
| **district** | Reporting unit from OSM `boundary=administrative` at levels 9 (Teilorte) and 11 (core-town districts); the **area** of the app. |
| **address** | OSM feature with `addr:street` and `addr:housenumber` from the clipped extract; searched in PostGIS for *Check* (no geocoding service). |
| **run / `run_id`** | One complete pipeline execution on one data snapshot (`YYYYMMDDTHHMMSSZ`); published as DB schema `run_<id>`. |
| **stage** | One pipeline step (acquire, validate, tiles, travel times, validate results, publish, cleanup). |
| **manifest** | File written by each stage: inputs with checksums, outputs with row counts, runtime, peak memory, status. |
| **provenance** | Per source and run: URL, retrieval time, SHA-256, licence. |
| **refresh** | `make refresh`: full data update on the host (acquire → validate → tiles → … → publish → cleanup), steps run one after the other. |
| **published run** | A run whose schema was loaded and switched to `current` by `publish` after validation passed. |
| **`current`** | DB views pointing to the latest published run; the only schema the API reads. |
| **data contract** | Binding table, file and API schemas between pipeline and API (`docs/data_contract.md`). |
| **validation report (part 1 / part 2)** | Checks of the inputs (`validate`) and of the results (`validate_results`) in every run; a failed check stops the run before `publish`. |
| **test clip** | Small OSM/GTFS/Zensus extract used for integration tests (`config/test_clip.yaml`). |
| **migration** | Numbered SQL file in `infra/db/migrations/`, applied once by `make migrate`. |
| **matrix** | Valhalla `sources_to_targets`: travel times between many points; used for walk and bike. |
| **transit engine** | The service that computes transit and bike + transit travel times and the live transit route: OpenTripPlanner (architecture O17). Matrices stay Valhalla only. |

## Delivery

| Term | Meaning |
|---|---|
| **preview** | Frontend deployment of a pull request or of `dev` on Cloudflare; URL in the CI run summary. |
| **production** | The public app: frontend on Cloudflare, backend on the server; changed only by `deploy.yml` after a release PR into `main`. |
| **release** | PR `dev` → `main` with a CHANGELOG section and version bump; its merge triggers `deploy.yml`. |
| **smoke test** | Checks after a deploy on the public URLs: frontend loads, API health, one fit request (persona), one cell request. |
| **rollback** | Redeploy of the previous SHA (backend and frontend) when the smoke test fails. |

## Numbering

| Term | Meaning |
|---|---|
| **S-numbers (S0.1, …)** | Steps of `docs/implementation_plan.md`. |
| **O-numbers** | Settled architecture decisions (`docs/architecture.md`). |
| **D1–D5** | Open architecture decisions: server, backend access, domain, frontend–API wiring, basemap. T1 (transit engine) was settled as O17 on 23 Nov 2026. |
| **M-numbers** | Open methodology questions (`docs/methodology.md`). |
| **V-numbers (V1, …)** | Validation checks and experiments (`docs/methodology.md`), reported in `docs/validation.md` (*planned, S1.11*). |
| **N-numbers** | Open points and findings (`docs/notes.md`). |
| **A-numbers** | Assumptions recorded in `docs/implementation_plan.md`. |
| **[OPEN] / [VERIFY]** | Not decided yet / stated but still to be checked. |
