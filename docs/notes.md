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
