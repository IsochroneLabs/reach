# api/AGENTS.md

Rules for agents working in `api/` (package `reach_api`, FastAPI). The root `AGENTS.md` applies;
this file wins where it is more specific.

- **Status:** S0.4 skeleton — `GET /api/health` (status, version, build SHA; never touches the
  database), CORS allowlist, error mapping. Reference data, address search, fit, cell detail and
  point routing (F4.5, `POST /api/place` and `/api/route`) built; responses are fixed in `docs/data_contract.md`.
- **Layout:** `main.py` (`create_app(deps)`; the lifespan builds pool, Valhalla and OTP clients from
  the environment; error mapping), `settings.py` (environment + `api` and the few engine values of
  the config), `db.py` (all SQL, `Database` protocol), `valhalla.py` (async client for routes and
  the matrix), `otp.py` (async OpenTripPlanner client for the live transit times), `place.py`
  (point routing and the fit from one point), `deps.py` (shared state, rate-limit dependency),
  `cache.py`, `ratelimit.py`.
- **Read-only from `current`.** The API connects as role `app_read` and reads only the views in
  schema `current` and `meta.runs` / `meta.data_sources` (arch. §8, AGENTS.md rule 6). It never
  writes and never reads a `run_<id>` schema directly. All SQL lives in `db.py`.
- **CRS and GeoJSON:** data is stored in EPSG:25832; transform to EPSG:4326 in SQL
  (`ST_Transform`) at the API boundary only. Never compute distances in degrees.
- **The fit is derived here, at read time** (AGENTS.md rule 5), from raw travel times; the
  formula is fixed in `docs/methodology.md` §6 before it is coded (S1.3).
- **Privacy (AGENTS.md rule 9):** no request bodies in logs; caches key only on the run and the
  weight vector (`Deps.fit_cache`); no tracking.
- **Rate limit:** token bucket per client IP (`rate_limited`, async dependency). `X-Forwarded-For`
  is trusted only from `api.trusted_proxies`; uvicorn runs with `--no-proxy-headers`.
- **Settings:** URLs and DSN from the environment (`DATABASE_URL_API`, `VALHALLA_URL`, `OTP_URL`,
  `REACH_CONFIG`, `BUILD_SHA`); every tunable value in the `api` section of
  `config/config.yaml`; the point route also reads `otp`, `routing_profiles`,
  `destination_labels.nearest_k_label` and `timezone`; no hard-coded URLs, credentials or limits.
- **Tests** live in `api/tests/`: `TestClient` on `create_app(deps)` with the fake database of
  `conftest.py`; Valhalla mocked with `respx` from `fixtures/valhalla/*.json` (real responses,
  recorded once). No network and no real database in unit tests.
- **Local run:** `make up` builds `infra/api.Dockerfile` and starts the API with hot reload on
  `api/src` at `http://127.0.0.1:${API_PORT}/api/health`. After a dependency change `make up`
  rebuilds the image.
