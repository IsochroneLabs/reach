# T1 transit engine spike: report

> Plan step S1.1 · branch `exp/juju-transit-engine` (never merged) · 21 Nov 2026 · worked on behalf of
> Juju (`nicholas-tuebi`) by a coding agent. This is a **recommendation**, not a decision: nothing is
> recorded in `docs/` until the team says yes (AGENTS.md, "Ask first").

## 1. Result in short

**Recommendation: combination (d) — Valhalla stays for walk and bike; OpenTripPlanner 2.10
(official image, pinned) for `transit` and `bike_transit`, queried per cell × destination pair by
the `travel_times` stage, and serving the live transit route for U2.**

- **Valhalla is out for transit**: `sources_to_targets` does not support multimodal costing
  (3.9.1, 3.9.3 and master), multimodal `/route` has no arrive-by and only walk + transit (§3).
- **OTP did the whole city in 25 min** on the dev machine: all 193,897 candidate pairs, each in its
  own trip window, with legs for the reasons. Peak memory **1.35 GB** (server) and **0.9 GB**
  (graph build, 6 s). Arrive-by, night trips after 24:00 and bike + transit (bike parked) work
  out of the box and were checked against the GTFS feed.
- **r5py is faster for plain matrices** (2.6 M pairs in 58 s, 2.3 GB) but misses three of our needs
  without extra code: no arrive-by (emulation: 47 min for the campus pairs alone vs. 64 s in
  OTP), **no trips after midnight** (measured: night bus not found; needs a GTFS rewrite we
  would maintain), and legs only through `DetailedItineraries`, which did not finish 500 pairs in
  22 min (§4.2). It also cannot serve the live transit route (no server).
- **Fit into 8 GB under A4**: OTP batch 1.35 GB vs. Valhalla's 2.7–4 GB peak (notes N1); run
  sequentially, both fit next to PostGIS (≈ 0.5 GB) and the API (≈ 0.2 GB).

## 2. Setup

| Item | Value |
|---|---|
| Machine | Apple M4 Pro (8 performance + 4 efficiency cores), 24 GB RAM, macOS 27.2.1 |
| Docker | Docker Desktop 29.9.2, Linux VM with **7.7 GiB RAM and 12 CPUs**; every engine container limited to `--memory 4g` |
| OSM | Geofabrik Regierungsbezirk Tübingen, timestamp 2026-11-20T21:21:21Z (MD5 checked), clipped with `osmium extract -s smart` |
| GTFS | NVBW naldo, `feed_version` 20261011, valid 2026-07-12 – **2026-12-12**, clipped to the area (stops inside, trips with ≥ 2 stops inside) |
| Zensus | 2022 population, 100 m grid (same SHA-256 as the archive copy) |
| Routing area | bbox of the city boundary (AGS 08416041) + 4 km: `[8.9103, 48.4144, 9.1853, 48.63]` → OSM 12.6 MB, 1,100 stops, 18,284 trips |
| Test clip | central Tübingen `[9.03, 48.505, 9.09, 48.545]` → OSM 3.3 MB, 375 stops; 1,321 origins, 489 destinations |
| Origins (A1) | **1,699 populated cells** (90,355 residents; same count as the archive) **+ 534 address cells** (any OSM address; a residential filter will lower this) = 2,233 |
| Destinations | 1,181 (OSM types of `config.yaml` with the archive's matching, parks by centroid, campus points corrected to the OSM buildings) |
| Candidate pairs | per origin and type the `2k` nearest by straight line within 6 km (all campus sites): **193,897** pairs, 86.8 per origin; every pair in the trip window of its type, `night_return` reversed |
| Reference dates | first matching weekday after the run date: Tue **2026-11-24** (morning, midday, evening), Sat **2026-11-28** 00:30 (= Friday night) and 10:00 |
| Engines | `opentripplanner/opentripplanner:2.10.0` (arm64 digest `sha256:ba53c6df…`); r5py 1.1.7 (R5 `v7.5.1-r5py`) on `eclipse-temurin:21-jre-noble` |

Memory: `cgroup memory.peak` of the container where available (exact), otherwise `docker stats`
sampled every second (a lower bound). Commands: `scripts/*.sh`; raw outputs in `results/`.

## 3. Candidates and sources

| Candidate | Finding | Source |
|---|---|---|
| (a) Valhalla multimodal | `sources_to_targets`: "**multimodal costing is not supported** for the time-distance matrix service at this time" — same text at tags 3.9.1, 3.9.3 (17 Nov 2026) and `master` | [matrix.md @3.9.1](https://github.com/valhalla/valhalla/blob/3.9.1/docs/docs/api/matrix.md), [@master](https://github.com/valhalla/valhalla/blob/master/docs/docs/api/matrix.md) |
| | `/route` with `multimodal`: "Currently supports pedestrian and transit"; arrive-by: "Specified arrival time. **Not yet implemented for multimodal**" | [route api-reference @3.9.1](https://github.com/valhalla/valhalla/blob/3.9.1/docs/docs/api/route/api-reference.md) |
| | ⇒ per-pair `/route` would give depart-at only, no bike access, and still needs transit tiles in the same Valhalla; not pursued | |
| (b) r5py / R5 | Matrix in one call with `departure_time_window` and percentiles; access modes incl. `BICYCLE`; needs JDK 21; default JVM heap 80 % of RAM | [r5py docs v1.1.7](https://github.com/r5py/r5py/tree/v1.1.7/docs), `RegionalTask` |
| | **No routing through midnight**: "For analysis purposes we rarely need to compute overnight trips, so we didn't implement this" (open since 2017; confirmed by the maintainer in 2025). r5py closed its issue with a documentation workaround (rewrite GTFS) | [conveyal/r5#286](https://github.com/conveyal/r5/issues/286), [#973](https://github.com/conveyal/r5/issues/973), [r5py#508](https://github.com/r5py/r5py/issues/508) / PR #530 |
| | No arrive-by query (departure-based RAPTOR); arrive-by must be emulated | `RegionalTask` parameters (no arrival option) |
| (c) OpenTripPlanner 2.x | Journey planner with GraphQL `planConnection`: `latestArrival` (arrive-by), access modes `WALK`, `BICYCLE`, `BICYCLE_PARKING` (needs `staticBikeParkAndRide`); no matrix API ("As of version 2, OTP has chosen to focus entirely on passenger information rather than analytics") | OTP 2.10 [schema.graphqls](https://github.com/opentripplanner/OpenTripPlanner/blob/v2.10.0/application/src/main/resources/org/opentripplanner/apis/gtfs/schema.graphqls), [Analysis.md](https://github.com/opentripplanner/OpenTripPlanner/blob/v2.10.0/doc/user/Analysis.md), [RoutingModes.md](https://github.com/opentripplanner/OpenTripPlanner/blob/v2.10.0/doc/user/RoutingModes.md) |
| | Memory "from less than one GB to more than 100 GB" depending on area | [System-Requirements.md](https://github.com/opentripplanner/OpenTripPlanner/blob/v2.10.0/doc/user/System-Requirements.md) |
| Versions | Valhalla 3.9.3 (2026-11-17), r5py 1.1.7 (2026-06-29), R5 7.6 (2026-08-01), OTP 2.10.0 (2026-09-09; 2.11 snapshots on Docker Hub, not released) | GitHub releases API, 21 Nov 2026 |
| Licences | Valhalla MIT; r5py GPL-3.0-or-later **or** MIT; R5 MIT; OTP **LGPL-3.0** (we run it unmodified as a separate service, no linking) | repository `LICENSE`/`COPYING` files |

## 4. Measurements (dev machine, §2)

### 4.1 Graph build and server

| Run | Wall time | Peak memory | Notes |
|---|---|---|---|
| OTP build, test clip | 4 s (build 3.8 s) | 861 MiB (sampled) | `--build --save`, `-Xmx3g`, graph 8.1 MB |
| OTP build, routing area | 7 s (build 5.9 s) | 910 MiB (sampled) | 1,081 stops, 734 patterns, graph 19.8 MB |
| OTP server start | ready after 2 s | 578 MiB idle | `--load --serve`, `-Xmx2g` |
| OTP server during the full run | – | **1,347 MiB** (cgroup) | stays allocated afterwards (JVM heap) |
| r5py network build | 3.4 s (clip), 5.3 s (area) | part of the runs below | built per process (r5py caches on disk only within a container) |

### 4.2 Travel times

| Run | Pairs | Wall / compute | Peak memory | Result |
|---|---|---|---|---|
| OTP, sample of 2,000 pairs, 1 / 2 / 4 / 8 threads | 2,000 | 68.5 / 31.9 / 16.4 / 10.3 s | – | 29 / 63 / 122 / 194 pairs/s; median 34–43 ms per request |
| **OTP, whole city, all windows, 4 threads** | **193,897** | **24.9 min** | **1,347 MiB** | 99.8 % with a result; per window: morning 64 s (arrive-by), midday 401 s, evening 857 s, night 72 s, weekend 100 s |
| OTP, `BICYCLE_PARKING` access, 2,000 pairs | 2,000 | 35.1 s (57 pairs/s) | – | 1,261 itineraries bike → park → ride; 910 faster than walk access (median gain 2.9 min) |
| r5py, test clip, evening (18:00, 10-min window) | 645,969 | 18.2 s (+3.4 s network) | 1,481 MiB (cgroup) | 98.4 % reachable |
| **r5py, whole city, evening** | **2,637,173** (all cells × all destinations) | **58.2 s** (+5.3 s) | **2,290 MiB** (cgroup) | 92.6 % reachable within 90 min |
| r5py, whole city, `BICYCLE` access | 2,637,173 | 266.9 s | 2,104 MiB | |
| r5py, campus arrive-by 08:10 (emulated: one matrix per minute 07:10–08:09) | 8,932 | **2,824 s (47 min)** | 2,276 MiB | runs use ~1 core each |
| r5py, `DetailedItineraries` (legs) | 500 | **> 22 min, not finished** (stopped at the time-box, 1,328 s) | 2,292 MiB (cgroup) | > 2.6 s per pair ⇒ > 5 days for 193,897 pairs on one process |

### 4.3 Correctness checks

| Check | OTP | r5py |
|---|---|---|
| Night: Gartenstraße 4 → Waldhäuser-Ost, Sat 00:58 (GTFS: N93 at Neckarbrücke 25:01 on the Friday service day, `results/gtfs_n93.txt`) | **16 min** with N93 01:01 (`results/otp_night_check.txt`) | **37 min = walking**: bus not found. Same at Wed 00:58. Control Tue 22:58: 20 min (bus found) |
| Same, with the GTFS rewrite (`sql/gtfs_shift_midnight.sql`: 506 trips, 5,161 stop times copied to the next day) | – | **17 min** (bus found) |
| Campus arrive-by 08:10, 8,341 pairs: minutes before 08:10 the student leaves home | median 28.3 min | median 28.0 min; difference median 0.45 min, 87 % within 5 min, P90 6.7 min |
| Evening 18:00, 105,030 pairs, arrival − 18:00 | 44 % of pairs walk only (no transit gain) | difference median −1.2 min, 77 % within 5 min, P90 6.8 min (R5 = median over 18:00–18:09; OTP = one best departure) |

Both engines agree within a few minutes where both can answer; the differences come from the
window definition (single departure vs. median over a window, M6) and the walk network.

## 5. Criteria

| Criterion | (a) Valhalla multimodal | (b) r5py / R5 | (c) OTP 2.10 |
|---|---|---|---|
| Cell × destination matrix | ✗ not supported (§3) | ✓ one call, all pairs (58 s city) | ✗ per pair; batched with 4 threads: 193,897 pairs in 25 min |
| Arrive-by (lecture 08:15, arrive by 08:10) | ✗ not implemented | ⚠ emulation only, 47 min for campus | ✓ `latestArrival`, 64 s for campus |
| Night after midnight (GTFS > 24:00) | – | ✗ not supported; ✓ only with own GTFS rewrite (measured) | ✓ measured (N93 found) |
| Weekend to the main station | – | ✓ | ✓ 17,853 pairs in 100 s |
| Bike as access, bike parked | ✗ walk + transit only | ⚠ `BICYCLE` access (bike to the stop; parking not modelled) | ✓ `BICYCLE_PARKING` with OSM bike parking |
| Legs for reasons (wait, ride, transfers, first stop) | – | ✗ `DetailedItineraries` > 2.6 s per pair (500 pairs not done in 22 min) | ✓ in every answer |
| Live transit route for U2 (arch. §3, §9) | – | ✗ library, no server | ✓ same service |
| Runtime city (dev machine) | – | 1 min per window (+47 min arrive-by emulation, + legs) | 25 min for all windows incl. legs |
| Peak memory | – | 2.3 GB per run (JVM, default 80 % of the limit) | 0.9 GB build, 1.35 GB serving |
| Fits 8 GB under A4 | – | ✓ sequentially | ✓ sequentially; also idle next to everything (0.6–1.35 GB) |
| Docker image | – | no official image; own image 2.7 GB (Python + JDK 21 + jar) | official `opentripplanner/opentripplanner:2.10.0`, 291 MB compressed / 880 MB, pinnable by digest |
| CI fit | – | heavy image; R5 jar download | graph of the test clip in 4 s; image pull 27 s |
| Licence | MIT | GPL-3.0+ or MIT (R5: MIT) | LGPL-3.0 (unmodified service) |
| Extra code we maintain | – | GTFS midnight rewrite, arrive-by loop, legs path | HTTP batch client (≈ 100 lines in the spike) |

## 6. Plausibility pairs (V1 style, filled by hand)

Addresses and cells: `config/plausibility_pairs.csv`. Engine: OTP 2.10, routing area, from the
exact address and from the home cell's centroid (as the pipeline routes). The reference columns
are filled by Juju from the naldo/DB journey planner at the same window; **no code queries a
journey planner**.

| Pair | Window | From → to | OTP (address) | OTP (cell centroid) | Reference (journey planner) |
|---|---|---|---|---|---|
| P1 | Tue 24.11., arrive by 08:10 | Ahornweg 10 (Waldhäuser-Ost) → Hörsaalzentrum Morgenstelle | 18.6 min: walk 07:42 · bus E 07:47–07:55 · walk → 08:00 | 25.7 min: bus 6 07:44 · bus 18 07:58–08:05 → 08:08 | *open* |
| P2 | Tue 24.11., arrive by 08:10 | Sieben-Höfe-Straße 100 (Derendingen) → Neue Aula | 29.2 min: walk · RB 66 07:44–07:48 · bus 5 07:56–08:01 → 08:03 | 30.0 min (same) | *open* |
| P3 | Tue 24.11., arrive by 08:10 | Aixer Straße 20 (Französisches Viertel) → Sand 14 | 30.1 min: bus 7611 07:43–07:46 · bus 2 07:53–08:02 → 08:07 | 30.0 min (same) | *open* |
| P4 | Sat 28.11., depart 00:30 | Gartenstraße 4 (Neckarmüller) → Ahornweg 10 | 40.5 min walking (N93 at 01:01 arrives 01:15, later than walking) | 39.0 min walking | *open* |
| P5 | Sat 28.11., depart 10:00 | Lustnauer Straße 12 (Pfrondorf) → Tübingen Hbf | 23.0 min: bus 7 10:02–10:21 → 10:25 | 23.6 min (same) | *open* |

P1 shows that a 50 m shift to the cell centroid can switch the stop and line (18.6 vs. 25.7 min);
V1 should compare from the centroid and report this effect.

## 7. Mapping to `travel_times` (data contract, planned S1.4)

One OTP answer per pair and window maps to one row of `travel_times` (cell × destination × mode ×
trip window): `time_s` and the legs `access_walk_s`, `wait_s` (`waitingTime`), `in_vehicle_s`,
`transfers` (`numberOfTransfers`), `egress_walk_s`, `first_stop`, `first_route`, `departure`
(from `legs[]`). Two definitions must be fixed with T1 (M6):

- **depart_at windows**: OTP's `duration` starts when the student leaves home *for the chosen
  bus*, so the wait at home is excluded; *arrival − window time* includes it. The spike stored
  both; R5's numbers correspond to the latter.
- **arrive_by** (`morning_lecture`): store *08:10 − departure from home*.

Walk-only answers (44 % of the evening pairs) are kept as transit = walk, as methodology §4
requires. `stop_departures` (departures per hour at the first stop) comes from the GTFS feed, not
from the engine.

## 8. Recommendation

1. **Engine:** OTP 2.10.0, official image pinned by digest, for `transit` and `bike_transit`
   (`BICYCLE_PARKING`); Valhalla unchanged for `walk` and `bike` (`costmatrix`).
2. **Refresh (A4):** `make refresh` builds the OTP graph after `tiles` (one-shot `--build --save`
   from the clipped OSM extract and the clipped GTFS feed), then `travel_times` runs Valhalla
   matrices, then OTP pairs with bounded concurrency (4), each pair in its trip window.
3. **Always-on:** an OTP server with the graph serves the live transit route of U2 (internal
   network only, rule 10). Restart it after `travel_times` (like Valhalla, N1) so it idles at
   ≈ 0.6 GB instead of keeping 1.35 GB.
4. **Inputs:** clip GTFS to the routing area before the build (spike: 1,100 stops instead of the
   whole naldo feed with 581 MB `shapes.txt`).

## 9. Fallback

If OTP does not fit on the server or fails validation: **departures at nearby stops, labelled
approximate** — from GTFS only: walk time to the nearest stops (Valhalla), departures per hour in
the window, and the scheduled in-vehicle time of direct lines to the stop nearest the
destination; no transfers. The app labels these times "approximate (schedule, no transfers)".

## 10. What changes if the team accepts

| Where | Change |
|---|---|
| `docs/architecture.md` | T1 → new **O17** (OTP 2.10 for transit and bike + transit, per-pair batch, live route); §3 component table (OTP always on, restart after `travel_times`); §6.1 profiles `transit` / `bike_transit` settled; §6.3 per-pair transit with candidates `2k` by straight line; §7 stage "transit build" = OTP graph build; §12 memory budget (OTP 0.9 GB build, 1.35 GB batch, 0.6 GB idle); version + change log |
| `AGENTS.md` rule 1 | "Valhalla for walk and bike (…); **OpenTripPlanner (official image, tag pinned) for transit and bike + transit**, queried per pair; no other transit engine." Stack line: "transit engine **pending (T1)**" → OTP |
| `docs/methodology.md` | M5 (bike + transit: `BICYCLE_PARKING`) and M6 (time inside a window: definition of §7) decided; separate yes |
| `docs/glossary.md` | **transit engine** = OTP; **matrix** stays Valhalla only |
| `config/config.yaml` | `routing_profiles.transit` / `bike_transit` (engine `otp`, speeds, access modes), `otp` section (concurrency, timeout), GTFS `members` + `routes.txt`, `agency.txt`, `transfers.txt` |
| `.env.example`, `compose*.yaml`, `infra/` | `OTP_URL`, OTP service (internal only), graph volume — S1.7 |

## 11. Open risks

1. **The naldo feed ends on 12 Dec 2026** (`feed_info.txt`, version 11 Oct). Without a new feed
   for the 2027 timetable, every window after 12 Dec fails V3, including the planned v0.2.0 on
   14 Dec. Check when NVBW publishes it; otherwise the reference dates must stay before 13 Dec.
2. **Server CPU**: 25 min on the M4 Pro; a 2–4 vCPU server is likely 2–3× slower (≈ 1 h per
   refresh). Estimate, not measured; S1.11 measures it.
3. **Pair count**: 193,897 assumes the `2k` straight-line candidates and one window per type
   (review findings 2, 3, 18). Back trips for the weekly travel time or all windows for U2 would
   multiply it (up to × 5).
4. **Address cells**: 534 with any address; the A1 filter "residential" is not applied yet.
5. **OTP config not tuned**: walk/bike speeds and `germany` tag mapping set; no elevation in the
   OTP graph (bike access legs are short; Valhalla keeps the hills for bike-only).
6. **Geofabrik URL** in `config/config.yaml` redirects to a 404 (layout change); the working URL
   is in `README.md` of this folder. Affects `acquire` (S0.4).

## 12. Re-run

```bash
exp/transit-spike/scripts/prepare_inputs.sh routing        # and test_clip
duckdb < exp/transit-spike/sql/origins.sql
python3 -I exp/transit-spike/scripts/gen_pairs.py data/spike/work/dest.geojsonseq data/spike/work/origins.csv data/spike/work
docker run --rm --memory 4g -e JAVA_TOOL_OPTIONS=-Xmx3g -v "$PWD/data/spike/otp/routing:/var/opentripplanner" \
  opentripplanner/opentripplanner:2.10.0 --build --save
docker run -d --name otp-serve --memory 4g -e JAVA_TOOL_OPTIONS=-Xmx2g -p 127.0.0.1:18080:8080 \
  -v "$PWD/data/spike/otp/routing:/var/opentripplanner" opentripplanner/opentripplanner:2.10.0 --load --serve
exp/transit-spike/scripts/otp_full.sh
docker build -t reach-spike-r5py:1.1.7 exp/transit-spike/r5py
exp/transit-spike/scripts/r5py_runs.sh routing evening      # campus_arrive, night, bike, legs
```
