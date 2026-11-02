# Methodology — reach

> **Status:** draft v0.2 (2 Nov 2026). Binding definition of **what** is measured, scored,
> recommended and validated. `architecture.md` describes **how** the system computes it. Every
> change bumps the version and adds a line to the [Change log](#change-log). Items marked
> **[M#]** are open methodology questions (Section 7).

Methodological basis: Mouratidis (2026), *Travel Behaviour and Society* 42, 101151 — proximity to
disaggregated everyday facilities plus public transport supply, with lack / insufficient /
sufficient classes. We add full automation, application to Tübingen with German open data, more
travel profiles, and a recommender for new facility locations.

---

## 1. Measurement

- **Unit:** populated Zensus 2022 100 m cell *i* inside the urban boundary, population $P_i$,
  origin = cell centroid (`architecture.md` §5.2).
- **Profiles *m*:** walking 3.39 km/h (inclusive default, 850 m in 15 min), walking 5.0 km/h
  (comparison), cycling 15 km/h, wheelchair 3.39 km/h.
- **Time budgets:** 15 minutes to facilities; 10 minutes on foot or by wheelchair to public transport stops.
- **Count** $A_{i,c,m}$: number of facilities of category *c* reachable from cell *i* within the
  budget, using network travel times from the Valhalla matrix (never isochrone polygons).
- **Nearest time** $T_{i,c,m}$: travel time to the nearest facility of category *c* (also stored).
- Raw counts and nearest times are stored; everything below is derived from them at read time.

## 2. Facility categories **[M1]**

Coarse categories in Core (proposed, to be confirmed with a completeness check per category):

| Category | OSM tags | $k_c$ | Rationale |
|---|---|---|---|
| Grocery | `shop=supermarket` (incl. discounters) | 2 | Paper treats 1 store as insufficient |
| Pharmacy | `amenity=pharmacy` | 1 | One pharmacy is adequate |
| Doctors | `amenity=doctors` | 2 | Choice and capacity; GP speciality is too sparsely tagged for a separate category |
| Childcare | `amenity=kindergarten`, `amenity=childcare` | 2 | Choice and capacity |
| School | `amenity=school` | 1 | Catchment-based provision |
| Parks & playgrounds | `leisure=park`, `leisure=playground` | 1 | Presence within reach |
| Public transport | GTFS stops (departures, see §3) | – | Own classes, see §3 |

**Facility locations.** OSM nodes are used as they are. Polygons (e.g. a supermarket building or
a school site) are represented by one representative point inside the polygon. **Parks and
playgrounds** are represented by **access points**: the intersections of walkable ways with the
park boundary; if there are none, points along the boundary every 50 m; at most *N* points per
park (spacing and *N* in `config/config.yaml`). A park counts **once** if at least one of its
access points is reachable within the budget; its travel time is the minimum over all access
points.

Tag mapping lives in `config/config.yaml`. Higher-order facilities (hospitals, universities,
specialised shops) are excluded. Bars, gyms and similar amenities are not part of 15-minute
compliance. Finer categories (discounters, GPs, school types) are Stretch, added only where OSM
completeness allows.

## 3. Public transport supply

- Stops reachable within **10 minutes on foot** via the matrix, for the walking profiles
  (3.39 and 5.0 km/h) and the wheelchair profile; not for cycling.
- Supply $S_i$ = sum of scheduled departures at these stops on the **reference weekday** (regular
  Tuesday in the feed validity period, no public or school holiday). Raw values ($S_i$, number of
  stops, time to the nearest stop) are stored; the classes below are derived at read time.
- Classes (provisional, from the paper's Copenhagen example; calibrate to the Tübingen
  distribution before freezing **[M2]**): lack 0 · insufficient 1–150 · medium 151–1,000 ·
  high > 1,000. Raw departure counts, no mode weighting in Core.

## 4. Scoring (single source of truth)

**Classes per cell, category and profile**

| Class | Rule |
|---|---|
| Lack | $A_{i,c,m} = 0$ |
| Insufficient | $0 < A_{i,c,m} < k_c$ |
| Sufficient | $A_{i,c,m} \ge k_c$ |

Where $k_c = 1$ the class "insufficient" is empty.

**Deficit (unmet demand)**

$$U_{i,c,m} = P_i \cdot \max\left(0,\; 1 - \frac{A_{i,c,m}}{k_c}\right)$$

**District results:** share of residents per class, sum of deficits, and residents lacking
access, per district × category × profile. Districts are ranked by total deficit (absolute need)
and by share of residents in "lack" (relative need).

Thresholds are stored with each run; changing them never requires re-routing.

## 5. Recommender

**Objective.** For a new facility of category *c* at candidate site *x* with catchment
$C(x)$ (cells reaching *x* within the budget):

$$\Delta W(x, c) = \sum_{i \in C(x)} P_i \cdot \left[\min\left(1, \tfrac{A_{i,c}+1}{k_c}\right) - \min\left(1, \tfrac{A_{i,c}}{k_c}\right)\right]$$

Population-weighted gain in saturating coverage. The objective is monotone and submodular in the
set of added sites, so greedy selection has a $(1 - 1/e)$ approximation guarantee.

**Procedure**

1. Candidates: cells in high-deficit areas, filtered by OSM land use (no water, forest, farmland,
   industrial, protected areas).
2. Catchment of each candidate via Valhalla matrix (cells as sources, candidate as target).
3. Greedy: pick the candidate with the largest $\Delta W$, update $A_{i,c}$, recompute, repeat.
4. Output: **ranked zones** with residents gaining sufficient access, class changes and an
   uncertainty note — not exact coordinates.
5. Optional equity mode (prioritise the worst-served cells) **[M4]**.

**Stated limits (shown in the app):** accessibility only; zoning, parcels, minimum catchment,
capacity and statutory planning (e.g. *Bedarfsplanung* for doctors) are not considered; results
depend on $k_c$ and OSM completeness.

## 6. Validation of results

Validation is a graded criterion; these experiments are part of the deliverable.

| # | Experiment | Question answered |
|---|---|---|
| V1 | Matrix counts vs. isochrone point-in-polygon counts on a sample of cells | How much would polygon counting be wrong, and where (Neckar, rail lines)? |
| V2 | OSM completeness for one or two categories (e.g. schools, childcare) vs. an official list | Recall and precision of the facility data |
| V3 | Recommender back-test: remove a random subset of existing facilities and check recovery | Does the recommender find plausible sites? (Interpret carefully: existing sites are not optimal.) |
| V4 | Greedy vs. exact solution (MILP, e.g. PuLP/CBC) on small instances | Optimality gap of greedy |
| V5 | Sensitivity: $k_c$, walking speed (3.39 vs. 5.0 km/h), time budget | Robustness of classes, rankings and recommendations |
| V6 | Origin point: cell centroid vs. building-based origin (`notes.md` N1) | Effect of the origin choice on classes |
| V7 | Plausibility with local knowledge: highest-deficit areas vs. known neighbourhoods | Do results make sense to people who know Tübingen? |
| V8 | Spatial statistics on district or aggregated level **[M5]** | Are deficits clustered? |
| V9 | Reproducibility: a team member who did not write the pipeline runs it from the README only, for the current and a newer data snapshot | Can someone use it without touching the code? |

Gate G1 (Stretch): test whether elevation changes walking times in Valhalla, with and without
slopes, on 2–3 steep routes (e.g. old town → castle, city → Waldhäuser-Ost) and across Neckar bridges.

## 7. Open methodology questions

| ID | Question | Proposal |
|---|---|---|
| M1 | Final category list and $k_c$ | Table in §2; confirm after an OSM completeness check |
| M2 | Transit supply class thresholds | Calibrate to the Tübingen distribution (e.g. quantiles) before freezing |
| M3 | Density strata (urban core vs. outlying villages) with different expectations | Report by district first; strata only if results are misleading for villages |
| M4 | Equity mode in the recommender | Implement after the efficiency mode works |
| M5 | Analysis method beyond counting (course asks for "adequate methods") | Global/Local Moran's I and hot spots on aggregated units; confirm with supervisors |
| M6 | Demand by age group | Only if the Zensus 100 m grid provides usable age data; otherwise total residents |

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v0.2 | 2026-11-02 | §2 facility locations (representative point for polygons, access points for parks and playgrounds, park counted once with minimum time); §3 transit supply for walking and wheelchair profiles, raw values stored, classes derived at read time | Answers to the P0 implementation plan questions (Q1, Q5) |
| v0.1 | 2026-11-02 | Created from the still valid parts of `architecture_proposal.md` (§5 scoring, §8 validation, §9 recommender), updated to current decisions (profiles, coarse categories, urban boundary, cell centroid) | Replace the outdated proposal with one binding methodology document |
