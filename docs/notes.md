# Notes — open points and future work

Points that are deliberately **not** part of the current architecture
([`architecture.md`](architecture.md)) but should be revisited. Each entry says why it matters,
what to do, and how to decide. Move an entry into `architecture.md` once it is decided.

---

## N1. Origin point per census cell — validate and possibly replace the cell centroid

**Status:** open (V6 measured 6 Nov 2026, decision pending) · **Added:** 2 Nov 2026 · **Related:** `architecture.md` §5.2, decision O5

**Current choice:** every populated Zensus 100 m cell starts its routing at the **cell centroid**.

**Why revisit:** the centroid is a geometric point, not where people live. In partly built cells
(edge of town, slopes, cells split by the Neckar, rail lines or main roads) it can lie up to
~70 m away from the houses, which is about 1 minute at 3.39 km/h. Facilities close to the
15-minute limit may then be counted wrongly, and Valhalla may snap the centroid to an edge that
residents do not use (forest track, road without sidewalk).

**Possible improvement: building-based origin**

1. Take OSM building footprints (`building=*`) inside the cell.
2. Keep residential buildings: `residential`, `house`, `apartments`, `detached`,
   `semidetached_house`, `terrace`; `building=yes` only inside `landuse=residential`; exclude
   `garage`, `shed`, `industrial`, `commercial`, `school`, `church`, etc.
3. Weight each building, options:
   - footprint area (robust, always available),
   - footprint area × `building:levels` (closest to floor area; levels often missing → default),
   - address points (`addr:housenumber`) or entrances (`entrance=*`) where mapped.
4. Compute the weighted centroid per cell, then use the **building closest to it** (medoid), so
   the origin always lies on a real residential building, not between two clusters.
5. Fallback to the cell centroid if the cell has no residential building.

**Snap check with Valhalla `/locate`** (to be added to the pipeline together with N1)

- Call `/locate` in batches (many points per request) for all origins and facilities.
- Flag cells whose origin snaps further than a threshold (e.g. 50 m) from a walkable edge, or to
  an unsuitable edge type; list them in the validation report.
- Reuse the same check for facilities (entrance far from the network, points on water).

**How to decide (validation experiment)**

- Run the counting step twice: cell centroid vs. building-based origin.
- Report per category and profile: share of cells and residents that change class
  (lack / insufficient / sufficient), and the change in district deficits.
- Check OSM building completeness for Tübingen first (e.g. building count vs. known totals,
  share of `building=yes` without use).
- If the differences are small → keep the centroid and document robustness. If they are large at
  the city edge → switch to the building-based origin.

**Effort:** small to medium (one pipeline step with GeoPandas, one validation run, `/locate` batching).

**V6 result (6 Nov 2026, run `20261106T142630Z`, `docs/validation_report.md`):** building
origin for 1,570 of 1,699 cells (96.5 % of residents; 33 % of OSM buildings are `building=yes`),
median shift 22 m (max 69 m); 1.9 % (walking 3.39) / 2.8 % (wheelchair) of residents ×
categories change class, in both directions. By the rule above the differences are small →
proposal: keep the centroid and document the robustness (decision open, Rico). The `/locate`
snap check is not part of V6.

---

## N2. Pipeline stage template and `pipeline/AGENTS.md`

**Status:** closed 2 Nov 2026 (P1: pattern in `pipeline/AGENTS.md`, `api/AGENTS.md` created; `web/AGENTS.md` follows in P6) · **Added:** 2 Nov 2026 · **Related:** `AGENTS.md` (folder-specific rules), `architecture.md` §7

When the code scaffold is created, define one pattern that every pipeline stage follows and
document it in `pipeline/AGENTS.md`:

- CLI entry (`python -m reach_pipeline <stage>` behind `make pipeline STAGE=…`), loading
  `config/config.yaml` through one typed config object.
- Inputs and outputs per `run_id`, manifest written at the end, previous manifest checked at the start.
- Logging format, runtime and peak-memory logging, exit codes (0 ok, non-zero with a clear message).
- Test layout: unit test with fixture per stage, mocked Valhalla responses.

Also create `api/AGENTS.md` and `web/AGENTS.md` with the scaffold.

---

## N3. Urban boundary leaves 8 % of residents unscored

**Status:** settled 2 Nov 2026 (architecture v0.12: O11 changed, O17 settled; methodology v0.3) ·
**Added:** 2 Nov 2026 · **Related:** `architecture.md` §4, O11, O17,
`config/config.yaml` `study_area.urban_boundary`, `validation.min_scored_share`

**Finding (P2, OSM snapshot 2026-11-01):** with `landuse: [residential, commercial, retail]` and
`closing_m: 50`, 7,232 of 90,355 grid residents in the city (8.0 %) live in cells whose centre
lies outside the urban boundary. Most are in the core town, not on farms: 3,956 in cells without
any land-use polygon at the centre (gaps between residential areas), 472 on the hospital area,
281 on the university campus; by district Universität 1,432, Au/Unterer Wert 740,
Feuerhägle 651, Weststadt 634, Zentrum 599.

**Variants measured on the same data** (residents outside / urban area):

| `landuse` | `closing_m` | Outside | Area |
|---|---|---|---|
| residential, commercial, retail (current) | 50 | 7,232 (8.0 %) | 14.6 km² |
| same | 100 | 5,386 (6.0 %) | 16.1 km² |
| + industrial, education, institutional, religious | 50 | 5,797 (6.4 %) | 16.6 km² |
| + industrial, education, institutional, religious | 100 | 4,015 (4.4 %) | 18.4 km² |

**Decision (Rico, 2 Nov 2026):** the scoring scope is every populated cell whose centre lies
inside the city boundary; `validate` checks that scored residents ÷ residents of all cells
touching the city ≥ 0.98 and lists excluded residents per district. The land-use boundary only
defines the map area, the live-endpoint check and the recommender candidates; it uses
`residential, commercial, retail, education, institutional, religious` and `closing_m` 100
(`industrial` joins Teilorte Bühl–Kilchberg and Kernstadt–Weilheim, ±100 m joins none).

**Result:** 1,699 scored cells, 90,355 of 90,443 residents scored (99.90 %); 88 excluded (edge
cells, most in Unterjesingen); urban boundary 12 parts, 16.6 km²; routing area 345.6 km².

**Addendum (W3, 9 Nov 2026):** the inspector said "No residents in this 100 m cell" for every
cell without a row in `cells`, also for the excluded edge cells with residents. Live answers now
carry `cell.status` (`scored`, `unpopulated`, `outside_city`) and the live endpoints accept a
point if it or its cell centre lies inside the city boundary (architecture v0.20, rule 12), no
longer the urban boundary + `api.boundary_margin_m`. The unused key was removed from the config
loader, `config.yaml` and the tests in W4 (confirmed by Rico, 9 Nov 2026).
The city test uses the union of the published districts as the city boundary. `validate`
checks gaps inside the city and overlaps (`district_coverage`), not district area outside the
city. Checked on run `20261106T142630Z`: gap 0.000 %, no populated unscored Zensus cell has its
centre inside the districts, and every scored cell origin lies inside them. If that ever
changes, publish the city boundary itself (open).

## N4. Valhalla keeps ~0.5–1.4 GB per worker thread after matrix requests

**Status:** open · **Added:** 3 Nov 2026 · **Related:** `architecture.md` §6.5 rule 15, §11
(memory budget), VF3, `compose.yaml` (`valhalla_service … 2`), `config/valhalla.json`

**Finding (P3, MacBook arm64, Docker 29.9.2, Valhalla 3.9.1, Tübingen tiles 12 MB):** idle
Valhalla uses 54 MB. During `count` its memory grows with the number of worker threads and is
not released afterwards: 2 threads → 1.0 GB after `walking_339`, 2.7–3.0 GB peak during the full
count (cycling), ~2.2 GB idle afterwards; 1 thread → 0.6 GB after `walking_339`, 1.4 GB peak
with cycling (cycling then takes 216 s instead of 120 s). Not changed by
`thor.clear_reserved_memory: true`, `mjolnir.max_cache_size` 64 MB, `MALLOC_ARENA_MAX` 1/2 or
`MALLOC_TRIM_THRESHOLD_`; lower `thor.max_reserved_labels_count_*` made it worse (2.9–3.8 GB).
The architecture estimate (≈ 0.5 GB) holds only when idle.

**Options for P8 (CX23, 4 GB):** (a) restart Valhalla after `count` in `make refresh` (frees the
memory; seconds of downtime for live calls at night); (b) 1 worker thread on the server (≈ 1.4 GB
peak, slower count, live calls queue behind the count); (c) both. Decide with VF3 on the server;
changing the thread count or the refresh sequence is an architecture change (ask first).

## N5. Walking times already depend on slopes when the tiles carry elevation

**Status:** settled 6 Nov 2026 (option a) · **Added:** 3 Nov 2026 · **Related:**
`architecture.md` §6.1, O7, gate G1 and V11 (`methodology.md` §1, §6), VF1, C6, N9

**Finding (P3, Valhalla 3.9.1):** with elevation in the tiles, the default `pedestrian` costing
is slower uphill and on steep downhill, and `use_hills` (0, default, 1) does not change the
times: Marktplatz → Schloss Hohentübingen (506 m) 681 s, back 619 s at 3.39 km/h (flat:
537 s; on the test clip tiles without elevation the default 5.1 km/h route takes 387.5 s vs.
463 s with elevation); Hauptbahnhof → Waldhäuser-Ost 3,950 s, back 3,335 s; golden pair cell
`CRS3035RES100mN2823200E4250800` → doctor (old town, 335 m) 443 s with elevation vs. 357 s on the
clip tiles. Cycling is
asymmetric as expected (VF2): 1,196 s vs. 865 s; `use_hills` 0 and default give the same times.

**Why it matters:** `architecture.md` §6.1 and O7 say slopes are "ignored for now" for walking
and wheelchair; in fact every walking and wheelchair count already includes the slope effect,
and the test clip (built without elevation, C6) gives different walking times than production.

**Options:** (a) accept and document that walking times include Valhalla's slope model (G1
answered: slopes do change walking times); (b) keep walking slope-free by building a second,
elevation-free tile set for walking/wheelchair (second graph, more memory, against §6.1 "same
tile set"); (c) look for a pedestrian costing option that disables the grade factor (`use_hills` does
not; not checked further in P3). Recommendation: (a), with a methodology note and G1 marked as
answered. Needs confirmation (architecture/methodology change).

**Resolution (6 Nov 2026, Rico):** option (a). Walking and wheelchair keep Valhalla's slope
model, counts do not change (architecture v0.16 §6.1/O7, methodology v0.4 §1/§6). Evidence
(running service, 3.9.1): N9 examples 932–984 s uphill vs. 740–894 s on flat ground;
wheelchair uses the same grade factor (Burgholzweg 127 → Waldkindergarten 881 s up, 700 s back,
666 s flat; `type: wheelchair` changes the route, not the factor; `max_grade` 2 or 30 changes
neither walking nor wheelchair times on the two test routes). 300 random walking routes
(≤ ~1 km) take a median 1.08 × the flat-ground time (0.91–1.66), 235 wheelchair routes 1.06
(0.94–1.79): gentle downhill can be up to 9 % faster than flat ground, so the prefilter factor
1.0 (O20) relies on the detour (measured required factor 0.94–0.96, `count` prefilter
evidence). The slope-free comparison is V11 (P7, one-off elevation-free tile set).


## N6. Faster walking can reach fewer facilities: Valhalla routes by cost, not time

**Status:** open (check tolerated, cause not removed) · **Added:** 4 Nov 2026 · **Related:**
`architecture.md` §7 (validate results), `config/config.yaml` `validation.results.monotonic`,
N5, V5

**Finding (P4, Valhalla 3.9.1, Tübingen tiles with elevation):** walking 5.0 km/h reaches fewer
facilities than walking 3.39 km/h in 6 of 1,699 cells (6 cell × category pairs, 1 transit row;
run `20261104T202436Z`). Example: cell `CRS3035RES100mN2824600E4251600` → supermarket
`n262528606` (238 m straight line): at 3.39 km/h Valhalla takes the steps Hackersteigle (309 m,
363 s); from 4 km/h on it avoids them and walks around (1,272 m, 919 s at 5.0 km/h, beyond the
budget). `/route` and `/sources_to_targets` agree, so this is the costing, not the matrix.
Valhalla picks the path with the lowest cost; step and grade penalties are not proportional to
walking time, so the cheapest path changes with the speed. Wheelchair ≤ walking 3.39 is violated
in 107 cells (6.3 %), cycling ≥ walking 3.39 in none.

**Decision (Juju, 4 Nov 2026):** no hard failure on any violation (as planned for P4); per pair
a share of violating cells above `warn_above` warns and above `fail_above` fails (walking
5.0 ≥ 3.39: warn > 0, fail > 1 %; pairs with different costings never fail). Report part 2
lists the share and examples.

**Options to remove the cause (not done):** check `step_penalty` / `use_hills` /
`max_hiking_difficulty` effects on the chosen path per speed; or accept, because "a faster
walker avoids steps" is Valhalla's model of preference, and document it in methodology (V5
sensitivity). Changing costing options changes counts → ask first.

## N7. Store the nearest facility per cell, category and profile in the pipeline

**Status:** settled 5 Nov 2026 (Rico, variant C of N8) · **Added:** 5 Nov 2026 · **Related:**
`architecture.md` v0.15 §6.5 rules 6 and 8, `docs/data_contract.md` (`reachable`), N8

**Decision:** `count` writes every facility a cell reaches within the budget with its matrix
time (`reachable`: `cell_id`, `profile_id`, `facility_id`, `time_s` smallint; only pairs within
the budget). The inspector lists reachable facilities and routes to the nearest one per category
from `current.reachable`, so list and count match the map by construction; `validate_results`
checks that `reachable` joined with `facilities` gives exactly `access_counts.count`. A live
matrix is only sent for grid cells without residents (and catchments).

## N8. Live matrix and pipeline blocks use different Valhalla matrix algorithms

**Status:** settled 5 Nov 2026 (Rico, variant C) · **Added:** 5 Nov 2026 · **Related:**
`architecture.md` v0.15 §6.5 rules 2 and 8, `config/valhalla.json`
(`thor.source_to_target_algorithm`), N4, N7

**Finding (P5, Valhalla 3.9.1, run `20261105T184022Z`):** with `select_optimal`, Valhalla answers
one-source matrices and single-cell blocks with `timedistancematrix` and larger blocks with
`costmatrix`. 24 of 960 live/precomputed cell × category pairs (2.5 %) differed by ±1. The
algorithm can only be set in the service config (`valhalla_build_config --help`: "one of
timedistancematrix or costmatrix; if blank, the optimal will be selected"); request parameters
(`prioritize_bidirectional`, `source_to_target_algorithm`) do not change it (tested).

**Comparison with /route** (facility decisions that differ between the algorithms): the 24 pairs
→ 25 facilities, `costmatrix` closer in 22; a random sample of 40 of the 975 rows that differ in
a full run → 48 facilities, `costmatrix` closer in 36 (median |Δ| 1 s vs. 20 s). Full `count`
(fresh container, 2 threads): `select_optimal` 243 s / Valhalla peak 2.6 GB, `costmatrix`
279 s / 2.5 GB, `timedistancematrix` 54 s / 195 MB; one-source matrix median for cycling
1,861 ms (`costmatrix`) vs. 152 ms. `costmatrix` also depends on the request: one source and the
whole block differ in 7 of 64 checked pairs (walking 5.0).

**`timedistancematrix` misses wheelchair routes** (reproducible on the Tübingen tiles of
5 Nov 2026, Valhalla 3.9.1 with `"source_to_target_algorithm": "timedistancematrix"`):

```bash
curl -s localhost:8002/sources_to_targets -d '{"sources":[{"lon":8.998298,"lat":48.502861}],
  "targets":[{"lon":8.99685,"lat":48.499493}],"costing":"pedestrian","verbose":false,
  "costing_options":{"pedestrian":{"type":"wheelchair","walking_speed":3.39}}}'
# timedistancematrix: durations [[null]]   costmatrix: [[463]]   /route: 463.9 s, 437 m
# same request without "type":"wheelchair": timedistancematrix [[463]]; reverse direction
# (target as source) with wheelchair: [[470]]
```

Origin = cell `CRS3035RES100mN2821500E4246900`, target = childcare `w611309782` (Katholisches
Kinderhaus St. Martin). In the random sample, 22 wheelchair facilities were "unreachable" for
`timedistancematrix` although /route finds a path within the budget; 616 of the 975 differing
rows of a full run are wheelchair rows.

**Decision (Rico, 5 Nov 2026, variant C):** `costmatrix` for every request (`config/valhalla.json`);
the inspector reads `current.reachable` (N7) instead of a live matrix for scored cells. The
remaining matrix-vs-/route deviation is measured every run (`validate_results`,
`matrix_vs_route`) and listed as a known limitation in report part 2. Not done: report the
`timedistancematrix` wheelchair gap upstream (Valhalla issue) — worth a short issue with the
example above. Memory: the Valhalla peak during `count` comes from `costmatrix` (N4 stays open).

## N9. Block matrices can miss facilities that a one-source matrix reaches within the budget

**Status:** settled 6 Nov 2026 (the three examples are no counting error; rare block
misses are now measured by `false_negatives`; branch `fix/rico-count-missing`) · **Added:**
6 Nov 2026 · **Related:** `architecture.md` §6.5, N5, N8, `validate_results`
(`matrix_vs_route`, `false_negatives`)

**Finding (P6, run `20261105T203945Z`, Valhalla 3.9.1, `costmatrix`):** for some cells, the
`count` block matrix seemed to give a much longer time than a one-source request, and the count
dropped to 0 near the budget:

| Cell | Facility | Run (block) | One source (reported) |
|---|---|---|---|
| `CRS3035RES100mN2822800E4249500` (Burgholzweg 127) | childcare `w644434788` | not within 900 s (walking 3.39); 667 s at walking 5.0 (≈ 927 m) | 740 s, 697 m |
| `CRS3035RES100mN2823600E4252700` (Österberg) | parks `w5541667` | lack | 834 s, 782 m |
| `CRS3035RES100mN2824700E4250800` (Schönblick) | parks `w222111961` | lack | 894 s, 837 m |

Also seen: the running Valhalla container still used the `config/valhalla.json` it loaded at
start (the file was replaced on disk by a git checkout; the single-file bind mount keeps the
old inode); a 25 × 101 pedestrian request was refused with error 150 "Exceeded max locations:
2500".

**Resolution (6 Nov 2026):**

- **The three examples are not missed.** With the running service, the count block, a one-source matrix, a
  39–365-source × 1-target matrix, `/api/catchment` and `/route` give the same time (±1 s) for
  all three examples: walking 3.39 984 s, 944 s, 932 s (not counted, correct); walking 5.0
  667 s, 640 s, 633 s (counted). The "one source" numbers above are route **length** ÷ 3.39 km/h
  (697 m → 740 s, 782 m → 834 s, 837 m → 894 s), i.e. flat-ground times, and "≈ 927 m" was
  time × speed. All three routes go uphill; Valhalla's pedestrian costing slows grades (2.3–2.6
  km/h on Burgholzweg; the way back takes 769 s) — the slope effect of N5, still open. The
  inspector shows the route length (697 m), not its time, which invites this reading.
  Prefilter (544–665 m < 848 m reach), snapping (on paths, < 10 m), block sizes (≤ 25 × 504,
  no split) and the budget comparison (`<=`) were checked and are not involved. Golden tests:
  `pipeline/tests/test_count_golden.py` (recorded blocks).
- **Published run used `costmatrix`.** The deleted inode in the container (born 20:24:39Z,
  9,548 bytes = the `costmatrix` file; `select_optimal` has 9,552) predates the container start
  (20:31:11Z) and the run's `count` (20:39:56Z); a recount of the run's inputs against a freshly
  started service with the effective config checked gives bit-identical outputs (552,917
  `reachable` rows, all times equal), whereas `select_optimal` changes ~28 rows (N8).
- **Config effective by construction:** `compose.yaml` mounts `config/`, the service copies
  `valhalla.json` to `<data_dir>/valhalla/valhalla.effective.json` at every start and serves
  that copy; `make valhalla-config` recreates the service when the copy differs (`make up`,
  `refresh`, `pipeline` run it); `count` fails if it differs and records it.
- **Validation gap closed:** `validate_results` check `false_negatives` routes random pairs
  within the prefilter reach that are not in `reachable`. Run `20261105T203945Z`: 0 of 480
  (2.6 s); a one-off sample of 4,800 pairs found 1 (cycling, /route 896.7 s, one-source matrix
  896 s, block matrix 906 s: `costmatrix` depends on the request, N8), i.e. ~0.02 %.
  New run `20261106T100859Z` (OSM 4 Nov): 1 of 480 (warn; cycling `CRS3035RES100mN2826200E4254900`
  → grocery `w217635610`: block matrix 954 s, one-source 859 s, /route 860 s) and 1 of 4,800 in
  a one-off sample (walking 5.0, /route 883 s). So block `costmatrix` times can be longer than
  one-source times (here by 95 s), but rarely (~0.02 % of the non-reachable pairs within reach,
  i.e. on the order of 100 of ~430,000 pairs over all profiles); `fail_above` 2 % stays far
  above that. Removing it (e.g. a one-source second pass for pairs within reach that are not
  reachable, or smaller blocks) changes counts → ask first.
- **Limits of the checks (review):** `count` checks the copy in its `data_dir`, not the service
  behind `VALHALLA_URL` (another Valhalla with a stale matching copy would pass);
  `validate_results` fails if the copy changed since `count` (checksum in
  `report_count.json`); `false_negatives` has no tolerance, so a /route time a few seconds
  under the budget counts (matrix and /route differ by seconds, `matrix_vs_route`); the
  start-time copy assumes the Valhalla image runs as root (it writes into the tile bind mount)
  — check on the server in P8.
- The "Exceeded max locations: 2500" error is not reproducible on our service (25 × 101, 25 ×
  476 and 1 × 2,600 pass for pedestrian, wheelchair and bicycle). **Likely cause (6 Nov 2026):**
  on this machine `localhost:8002` is another project's Valhalla (3.5.1, container
  `iso15-socke-valhalla-1`), which rejects every pedestrian matrix above 2,500 pairs; our
  service listens on `localhost:8003` (`VALHALLA_URL` in `.env`). A script that does not load
  `.env` falls back to `valhalla.url` (`http://localhost:8002`) and asks the wrong service. The
  pipeline (`make`, `uv run --env-file .env`) is not affected. **Fixed (6 Nov 2026):**
  `valhalla.url` is null in `config/config.yaml`; without `VALHALLA_URL` the pipeline stops
  with a clear configuration error (exit code 2) instead of guessing a port. The other
  project's containers were stopped (`docker compose down`, volumes kept).

**Open:** none. The inspector shows the route time first and its length second (6 Nov 2026,
branch `fix/rico-inspector-time`). N5 settled (6 Nov 2026: slopes kept); `false_negatives` warns above 0.5 % since then (one hit in ~480
pairs is expected).

## N10. `npm audit`: minimatch ReDoS in the lint toolchain (dev only)

**Status:** known, accepted for now · **Added:** 6 Nov 2026 · **Related:** `web/package.json`

`npm audit` reports GHSA-g3hv-75wg-m249 (moderate) for minimatch 10.2.6, pulled in by eslint
10.13.0 (`@eslint/config-array`) and typescript-eslint 8.72.0
(`@typescript-eslint/typescript-estree`). The fix is minimatch ≥ 11.0.1, a major version
outside the `^10.2` ranges these packages declare, so there is no non-breaking update and no
`overrides` entry; `npm audit fix --force` would downgrade eslint to 9 (breaking). It is not
in the production bundle (lint only, on trusted repository files). Recheck when eslint or
typescript-eslint allow minimatch 11.

## N11. Wheelchair profile: `max_grade` excludes no edges, routes include steep sections

**Status:** open: option (a) done 6 Nov 2026 (branch `docs/rico-wheelchair-text`: architecture v0.17 §6.1, methodology v0.5 §1, config comment), option (b) done 6 Nov 2026 in V11 (no effect; cause not found) · **Added:** 6 Nov 2026 ·
**Related:** `architecture.md` §6.1, O7, N5, `config/config.yaml` (`wheelchair_339`)

**Finding (running service, Valhalla 3.9.1, Tübingen tiles with elevation):** `/route` with
`pedestrian`, `type: wheelchair`, `walking_speed` 3.39 and `max_grade` unset, 1, 4, 6, 12 or 30
gives the same route, time and length in both directions on four steep routes; the
default route's steepest edge (`trace_attributes`, max. up/down grade) is shown:

| Route | Wheelchair up / back | Steepest edge | Walking up |
|---|---|---|---|
| Burgholzweg 127 → Waldkindergarten | 881 s, 627 m / 700 s | 12 % | 984 s, 697 m |
| Marktplatz → Schloss Hohentübingen | 681 s, 506 m / 619 s | 12 % | 681 s, 506 m |
| Hauptbahnhof → Waldhäuser-Ost | 5,262 s, 4,226 m / 4,601 s, 4,366 m | 20 % | 4,909 s, 3,849 m |
| Neckarbrücke → Österberg | 1,080 s, 1,028 m / 1,144 s, 1,035 m | 5 % | 1,124 s, 1,071 m |

So `max_grade` does not exclude edges in this version (even 1 % keeps edges with 12–20 %);
the wheelchair profile differs from walking by its route (no steps: other paths on
Burgholzweg and to Waldhäuser-Ost) and by the shared grade factor on time (N5), not by a
slope limit. Wheelchair routes can therefore use sections far steeper than ramp guidelines
(DIN 18040: 6 %), and wheelchair counts are optimistic on hillsides in this respect.
`architecture.md` §6.1 ("avoids steps and steep sections") and the `wheelchair_339` comment in
`config/config.yaml` overstate it.

**Options (ask first):** (a) document the limitation (§6.1 wording, methodology limitations,
data page); (b) find out why `max_grade` has no effect (option name or parsing in 3.9.1, edge
grades in the tiles) with a small request test against the Valhalla source; (c) exclude steep
edges ourselves — not possible with the matrix without a custom graph. Recommendation: (a) now,
(b) as part of V11.

**Option (b) result (V11, 6 Nov 2026):** `/route` wheelchair on the golden pair (12 % grade)
with `max_grade` unset, 1, 6, 12 and 30 gives the same route and time on the production tiles
(681 s) and on an elevation-free tile set (568 s): the option has no effect in 3.9.1, on either
tile set. Why (option name, parsing, edge grades) is not found out; the known limitation
(methodology §1) stands.

## N12. Recommender follow-ups

**Status:** open · **Added:** 6 Nov 2026 · **Related:** `methodology.md` §5 (M4),
`architecture.md` §6.4, `config/config.yaml` (`recommend`), N4

What the first version (P7, branch `feature/rico-recommender`) leaves open:

- **Cycling is off** (`recommend.profiles`, decision by Rico): hardly any cycling deficit, and
  large cycling `costmatrix` requests grow Valhalla's memory (N4). Switching it on is a config
  change; measure runtime and the Valhalla peak first (walking + wheelchair: 84 s, 1.2 GB).
- **The 2.5 GiB Valhalla limit for cycling (E6) came from the 4 GB server.** With the 8 GB target
  (architecture v0.22) the limit can be set again; cycling needs ~3.9 GiB for Valhalla alone.
- **Cycling stays off** (W6, measured 9 Nov 2026 on the Tübingen run, macOS/Docker Desktop):

  | `recommend` variant | runtime | pipeline peak | Valhalla peak | pairs |
  |---|---|---|---|---|
  | without cycling (3 profiles) | 44 s | 1.6 GB | 1.2 GiB | – |
  | + `cycling_15`, 100 m candidates | 295 s | 2.0 GB | 4.0 GiB | 1.48 M |
  | + `cycling_15`, 200 m candidates | 202 s | 1.7 GB | 3.9 GiB | 0.37 M |

  Limit (E6): runtime ≤ 10 min and Valhalla ≤ 2.5 GiB. Runtime passes, Valhalla does not, even
  with the 200 m grid (the memory is set by the 3.75 km source sets of the matrix requests, not
  by the number of candidates). Cycling would add 12 zones for ~130 cells with a deficit. The
  key `recommend.profile_overrides.<profile>.candidate_spacing_m` stays in the code; switching
  cycling on = adding `cycling_15` to `recommend.profiles`. Ideas if wanted later: smaller
  `group_size_m` for cycling, or fewer sources per request.
- **osmium peak ~950 MB** for the land-use filter (`tags-filter` on the clipped PBF; the ID
  bitmaps, not the 11 MB file, set the size). Could move into `validate` pass 1 (one pass fewer
  over the regional PBF there, but a new validate output); only if the CX23 needs it (P8).
- **Catchments are recomputed every run** (~80 s), like `count` (C10: no caching across runs).
- **Gains of ranks 2…N assume the better-ranked zones are built first** (greedy); the app says
  "deficit −X" per zone. A plain-language decision card (`features.md` §5) and the equity mode
  (M4) are not built yet.
- The data page does not list the recommender limits or the wheelchair limitation (N11) yet; the
  recommendation panel states its limits.

## N13. Validation follow-ups

**Status:** open · **Added:** 6 Nov 2026 · **Related:** `docs/validation_report.md`,
`methodology.md` §6, M1, M5, N1

What the first validation report (branch `feature/rico-validation-report`) leaves open:

- **V7 and V9 not run** (need people): protocols and result tables in the report; V9 by Socke
  or Juju, incl. a newer snapshot a week later.
- **OSM gaps (V2):** 13 of 104 Kitas of the city's list and 2 of 38 schools have no OSM match
  (list in `data/experiments/<run>/v02/`); mapping them in OSM (or a licensed city list) would
  lower childcare "lack" in a few areas. The city's pages state no licence, so the reference list
  stays local.
- **M5:** Moran's I / LISA work (V8: strong clusters on cells, none between districts); confirm
  with the supervisors that this is the "adequate method", then show the LISA map in the app?
- **Sensitivity (V5):** absolute shares depend strongly on speed and budget; the app and slides
  should always name the profile and budget next to a share.
- **V3/V4 as regression checks:** both run in seconds on stored data and could become checks of
  `validate_results` (e.g. greedy gap ≤ 5 % for N = 5); only if the team wants it.


## N14. Non-public playgrounds and parks are counted

**Status:** closed (10 Nov 2026, W7a) · **Added:** 9 Nov 2026 · **Related:** `methodology.md` §2,
`docs/osm_tagging.md` §4, `docs/app_iteration_plan.md` W7a

**Finding (run `20261106T142630Z`, OSM 2026-11-01):** the pipeline ignores `access=*`. Of 349
`leisure=playground` features in the routing area, 65 carry `access=private` and 15
`access=customers` (housing estates, restaurants, Kitas); 2 parks carry `access=private` and 1
`access=no`. All of them count as reachable parks & playgrounds, so the category is optimistic,
most likely in dense housing areas.

**Resolution (W7a):** `access` in `[private, no, customers]` is excluded for parks and
playgrounds only (not for schools, childcare, shops or practices, where the tag describes the
grounds or customers); a standing `warn` for `facility_subtypes_complete` is expected until the
schools are tagged; a private polygon hides only itself (an untagged playground node inside it
still counts); `validate` reports the dropped features (`facilities_excluded_by_access`:
in the city 58 private and 10 customers playgrounds, 1 private and 1 closed park; run
`20261109T175743Z`). Share of residents with a park or playground within 15 minutes (walking
3.39 km/h) 97.5 % before, 97.2 % after; wheelchair 95.8 % → 94.8 %. Parks alone: 69.2 % (walking
3.39), playgrounds alone: 95.8 %.


## N15. Housing potential: first run and open points

**Status:** open · **Added:** 10 Nov 2026 · **Related:** `methodology.md` §5b, `docs/app_iteration_plan.md` W8

**First run (scratch copy of `20261109T175743Z`, OSM 2026-11-01, local laptop):** 3,211 grid
cells in the urban boundary + 200 m; 1,642 are resident cells, 739 lie in excluded land use, **830
candidates remain** (2 outside every district). `housing` takes **14.9 s** (walking 3.39: 4.6 s,
5.0: 9.4 s; 159 + 162 matrix requests), peak RSS 1.7 GB. With the default score, 86 candidates
score ≥ 80 and 149 score 0 (walking 3.39). The Top 10 sit in Südstadt and Gartenstadt and are
cells with all seven categories within reach (not checked on a map). Whether a
cell is buildable is not known: some of them may be hospital, university or sports grounds that
OSM does not tag as an excluded land use.

**Open:**
- **Plausibility on areas built after the 2022 census** (plan W8): the team has to name three
  areas; the pipeline cannot know which grid cells were built up since. Until then
  `validation_report.md` carries only the first-run figures above.
- **Land use:** `landuse=retail`, `landuse=education`, `amenity=hospital` and sports pitches are
  not excluded (only industrial, cemetery, park in addition to the recommender's list); candidates
  inside them would show up in the Top 10. Decide after looking at the map.
- **Neighbouring municipalities:** the 200 m margin reaches into Kusterdingen, Ammerbuch and
  Rottenburg; empty cells there are candidates too (no district, shown as "Outside the districts").
- **No merging into sites:** neighbouring cells with the same score are separate entries.

## N16. Extended categories: open points after the config change

**Status:** open · **Added:** 11 Nov 2026 · **Related:** `methodology.md` §2 (v0.11), `architecture.md` O8, N4, N12, N15

Nine extended categories were added to `config/config.yaml` (16 in total). On the routing extract
of run `20261110T223016Z` the facility build gives **2,010 facilities with 2,581 routing points**
(the seven Core categories: 853 facilities); sports grounds alone are 566. All 16 categories
have at least one facility inside the test clip. Unit tests and the browser tests pass; **no
pipeline run with the new categories has been made yet**.

**Open:**
- **Runtime and memory not measured.** Matrix targets grow about 2.4-fold; `count` for cycling
  (1.13 M pairs before) and Valhalla's memory (N4) grow with them. Run `make refresh` and record
  the figures; if too heavy, drop `leisure=pitch` and keep `leisure=sports_centre` (138 features).
- **`architecture.md` O8** still says "coarse facility categories (≈ 7) in Core". The Core list is
  unchanged, the extended list is new; the decision text needs a line (ask first).
- **"All" and the housing default score** (§4b, §5b) now average over 16 categories, including
  restaurants and gyms. Decide whether the defaults should use the Core categories only.
- **Recommender** produces zones for every category; for sports grounds and senior care a
  100 m zone is hardly meaningful. Consider a per-category switch.
- **Completeness** of the extended categories is unchecked (V2 covers childcare and schools);
  sports grounds are optimistic (no `access` tag on about 87 % of the pitches).
- **Web fixtures** (`web/tests/fixtures/meta.json`) still hold the seven Core categories;
  re-record after the first run with the new config.

