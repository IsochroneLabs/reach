# Notes — open points and future work

Points that are deliberately **not** part of the current architecture
([`architecture.md`](architecture.md)) but should be revisited. Each entry says why it matters,
what to do, and how to decide. Move an entry into `architecture.md` once it is decided.

---

## N1. Origin point per census cell — validate and possibly replace the cell centroid

**Status:** open · **Added:** 2 Nov 2026 · **Related:** `architecture.md` §5.2, decision O5

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

**Status:** open, needs a decision · **Added:** 3 Nov 2026 · **Related:** `architecture.md`
§6.1, O7, gate G1 (`methodology.md` §6), VF1, C6

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

**Status:** settled 6 Nov 2026 (no counting error; branch `fix/rico-count-missing`) · **Added:**
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

- **No missed facilities.** With the running service, the count block, a one-source matrix, a
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
- The "Exceeded max locations: 2500" error is not reproducible (25 × 101, 25 × 476 and
  1 × 2,600 pass for pedestrian, wheelchair and bicycle); 2,500 is the limit of the `auto`
  costing.

**Open:** N5 (slopes in walking times: document or remove; architecture §6.1/O7 still say
"ignored for now"); show the route time next to its length in the inspector (web).

## N10. `npm audit`: minimatch ReDoS in the lint toolchain (dev only)

**Status:** known, accepted for now · **Added:** 6 Nov 2026 · **Related:** `web/package.json`

`npm audit` reports GHSA-g3hv-75wg-m249 (moderate) for minimatch 10.2.6, pulled in by eslint
10.13.0 (`@eslint/config-array`) and typescript-eslint 8.72.0
(`@typescript-eslint/typescript-estree`). The fix is minimatch ≥ 11.0.1, a major version
outside the `^10.2` ranges these packages declare, so there is no non-breaking update and no
`overrides` entry; `npm audit fix --force` would downgrade eslint to 9 (breaking). It is not
in the production bundle (lint only, on trusted repository files). Recheck when eslint or
typescript-eslint allow minimatch 11.
