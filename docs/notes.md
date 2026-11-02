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

**Status:** open · **Added:** 2 Nov 2026 · **Related:** `architecture.md` §4, decision O17 (a),
`config/config.yaml` `study_area.urban_boundary`

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

**How to decide:** O17 (a) allows more built-up land-use values ("…"). Changing the values is a
config change (ask first) and possibly a methodology note; alternatively add the populated cells
of option (b) (census-based) to the land-use area. Check the remaining outside cells on the map
before choosing.
