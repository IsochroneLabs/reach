# api/AGENTS.md

Rules for agents working in `api/` (package `reach_api`, FastAPI). The root `AGENTS.md` applies;
this file wins where it is more specific.

- **Status:** P5 — read endpoints (`routes/read.py`) and live endpoints (`routes/live.py`) exist;
  response formats are fixed in `docs/data_contract.md` ("API responses"). W2 added
  `POST /api/isochrone` (forward or reverse, cached per direction). W3: `cell.status` in every
  live answer (`scored`, `unpopulated`, `outside_city`), clicks accepted in the whole city. W4:
  `reachable[].point`, the next missing facility per category (`next_facility`, `next_note`,
  one live matrix, `api.next_facility.*`) and `POST /api/route` to one facility.
- **Layout:** `main.py` (`create_app(deps)`, lifespan builds pool and client from the
  environment, error mapping), `settings.py` (env + `api` section of the config), `db.py` (all
  SQL, `Database` protocol), `valhalla.py` (async client), `deps.py` (shared state, run context,
  rate-limit dependency), `cache.py`, `ratelimit.py`.
- **Read-only from `current`.** The API connects as role `app_read` and reads only the views in
  schema `current` and `meta.runs`/`meta.data_sources` (arch. §8, rule 6). It never writes to the
  database and never reads a `run_<id>` schema directly. All SQL lives in `db.py`.
- **CRS and GeoJSON:** data is stored in EPSG:25832; transform to EPSG:4326 in SQL
  (`ST_Transform`, `ST_AsGeoJSON(…, 6)`) at the API boundary only; build GeoJSON bodies in
  PostGIS, not in Python. Never compute distances in degrees.
- **No derived values in Python:** classes, deficits and district shares come from the views
  (`scores`, `transit_scores`, `district_scores`); the API only sorts and ranks them.
- **Live endpoints** call Valhalla only for what is not precomputed (arch. §6.5 rules 8–12):
  snap the point to its 100 m grid cell, check city boundary (point or cell centre, union of
  `current.districts`) or scored cell before any
  call, one isochrone call for all contours; scored cells list reachable facilities from
  `current.reachable` (no matrix), catchments of recommended zones come from
  `current.recommendation_catchments` (no matrix), only grid cells without residents, other
  catchments and the next missing facility (categories below `k`, one matrix for all of them; a
  failing matrix leaves the rest of the answer intact) send a live matrix through the `live_matrix` client (`api.live_matrix`: timeout, concurrency; costing from
  `current.profiles`, prefilter as in `count`), cache per (run, cell, profile) as serialized
  JSON bytes (Python objects are ~10× larger), concurrent misses share one computation,
  rate-limit per client IP (async dependency: no threadpool). `X-Forwarded-For` is trusted
  only from `api.trusted_proxies` (Caddy); uvicorn runs with `--no-proxy-headers`.
- **Settings:** URLs and DSN from the environment (`DATABASE_URL_API`, `VALHALLA_URL`,
  `REACH_CONFIG`); every tunable value in the `api` section of `config/config.yaml`; no
  hard-coded URLs, credentials or limits.
- **Tests** live in `api/tests/`: `TestClient` on `create_app(deps)` with the fake database of
  `conftest.py`, Valhalla mocked with `respx` from `fixtures/valhalla/*.json` (real responses,
  recorded once). No network and no real database in unit tests; `test_db_queries.py` (marker
  `db`) runs the SQL against a disposable PostGIS as `app_read`. With `--import-mode=importlib`
  test modules cannot import `conftest`: share helpers as fixtures.
- **Local run:** `make up` builds `infra/api.Dockerfile` and starts the API with hot reload on
  `api/src` (through Caddy: `http://127.0.0.1:8080/api/…`; no host port). After a dependency
  change `make up` rebuilds the image.
