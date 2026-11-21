# T1 transit engine spike (S1.1) — throwaway

Branch `exp/juju-transit-engine`, **never merged**. Everything here is spike code: no
dependencies in the uv workspace, no project config changed. Results and the recommendation live in
[`REPORT.md`](REPORT.md) (written at the end of the spike).

## Layout

| Path | What |
|---|---|
| `config/areas.json` | Spike areas: routing bbox (city + 4 km) and the test clip (central Tübingen) |
| `config/plausibility_pairs.csv` | 5 cell × destination pairs with addresses; reference columns are filled by hand from the naldo/DB journey planner (never queried from code) |
| `sql/` | DuckDB scripts: GTFS service/night checks, GTFS clip, origins (A1), plausibility pairs |
| `scripts/` | `prepare_inputs.sh` (clip OSM + GTFS), `gtfs_checks.sh`, `otp_batch.py` (local OTP only), `memwatch.sh`, helpers |
| `otp/` | OpenTripPlanner build and router config |
| `r5py/` | Dockerfile (r5py 1.1.7 on JDK 21) and `r5py_matrix.py` |
| `results/` | Small text/CSV/JSON outputs that the report cites (no raw data) |

## Data (git-ignored, under `data/spike/`)

Downloaded on 21 Nov 2026 from the sources in `config/config.yaml`:

- OSM: Geofabrik Regierungsbezirk Tübingen, timestamp 2026-11-20T21:21:21Z, MD5 verified. The
  URL in `config/config.yaml` redirects to a 404 since Geofabrik's layout change; the working URL
  is `https://download.geofabrik.de/europe/germany/baden-wuerttemberg/tuebingen-regbez/tuebingen-regbez-latest.osm.pbf`.
- GTFS: NVBW naldo, `feed_version` 20261011, valid 2026-07-12 to **2026-12-12**.
- Zensus 2022 population, 100 m grid (same SHA-256 as the archive copy).

## Tools

Host: `osmium` (Homebrew), `duckdb` CLI 1.5.2 (+ `spatial` extension), Python 3 stdlib only.
Engines run only in Docker: `opentripplanner/opentripplanner:2.10.0` and the local r5py image.

## Re-run

```bash
exp/transit-spike/scripts/prepare_inputs.sh test_clip   # and: routing
exp/transit-spike/scripts/gtfs_checks.sh
duckdb < exp/transit-spike/sql/origins.sql
```

Engine runs and their exact commands are recorded in `REPORT.md`.
