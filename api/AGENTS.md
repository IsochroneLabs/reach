# api/AGENTS.md

Rules for agents working in `api/` (package `reach_api`, FastAPI). The root `AGENTS.md` applies;
this file wins where it is more specific.

- **Status:** placeholder until P5; only `GET /api/health` exists (`src/reach_api/main.py`).
- **Read-only from `current`.** The API connects as role `app_read` and reads only the views in
  schema `current` (arch. §8, rule 6). It never writes to the database and never reads a
  `run_<id>` schema directly.
- **CRS:** data is stored in EPSG:25832; transform to EPSG:4326 in SQL (`ST_Transform`) at the
  API boundary only. Never compute distances in degrees.
- **Live endpoints** call Valhalla only for what is not precomputed (arch. §6.5 rules 8–12):
  validate the point against the urban boundary first, one isochrone call for all contours,
  cache per (cell, profile), rate-limit per client IP.
- **Settings** come from environment variables (`.env.example`: `DATABASE_URL_API`,
  `VALHALLA_URL`); no hard-coded URLs or credentials.
- **Tests** live in `api/tests/`: `fastapi.testclient.TestClient`, a fake DB layer, and Valhalla
  mocked with `respx` from recorded responses. No network, no real database in unit tests.
- **Local run:** `make up` starts the API in Docker with hot reload on `api/src`
  (`http://127.0.0.1:8080/api/health` through Caddy).
