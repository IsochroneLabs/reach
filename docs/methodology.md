# Methodology — reach

> **Status:** draft v0.10 (10 Nov 2026). Binding definition of **what** is measured, scored,
> recommended and validated. `architecture.md` describes **how** the system computes it. Every
> change bumps the version and adds a line to the [Change log](#change-log). Items marked
> **[M#]** are open methodology questions (Section 7).

Methodological basis: Mouratidis (2026), *Travel Behaviour and Society* 42, 101151 — proximity to
disaggregated everyday facilities plus public transport supply, with lack / insufficient /
sufficient classes. We add full automation, application to Tübingen with German open data, more
travel profiles, and a recommender for new facility locations.

---

## 1. Measurement

- **Unit:** populated Zensus 2022 100 m cell *i* whose centroid lies inside the city boundary of
  Tübingen, population $P_i$, origin = cell centroid (`architecture.md` §4, §5.2).
- **Profiles *m*:** walking 3.39 km/h (inclusive default, 850 m in 15 min), walking 5.0 km/h
  (comparison), cycling 15 km/h, wheelchair 3.39 km/h.
- **Slopes:** the speeds are flat-ground speeds. Valhalla's slope model (kept as it is,
  `architecture.md` §6.1, O7) reduces them uphill and on steep downhill and raises them slightly
  on gentle downhill; walking and wheelchair times are a median 6–8 % longer than flat-ground
  times (up to +66 % on steep routes, at most −9 %). Results are therefore conservative compared
  with a flat-ground model: fewer facilities count as reachable on hillside cells. V11 measures
  the effect.
- **Known limitation, wheelchair:** the wheelchair profile avoids steps but not steep sections.
  Valhalla's `max_grade` excludes no edges in the version we use (`architecture.md` §6.1, notes
  N11), so wheelchair routes can include grades of 12–20 %, far above ramp guidelines
  (DIN 18040: 6 %). The slope factor still lengthens these times, but wheelchair counts are
  **optimistic** on hillsides: some facilities counted as reachable are not usable for many
  wheelchair users.
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
| Parks | `leisure=park`; not `access` in `private`, `no`, `customers` | 1 | Presence within reach |
| Playgrounds | `leisure=playground`; not `access` in `private`, `no`, `customers` | 1 | Presence within reach |
| Public transport | GTFS stops (departures, see §3) | – | Own classes, see §3 |

**Access rule.** Only facilities the public can use count. Parks and playgrounds with
`access=private`, `access=no` or `access=customers` are dropped; schools, childcare, shops and
practices are not filtered by `access` (there the tag describes the grounds or the customers, not
who may enrol or visit). Every category carries a thematic `group` (food, health, education,
green) and may restrict its tag match with `require` and `exclude` conditions in the config; the
validation report lists the features dropped per category. Schools stay one category until at
least 95 % of the schools in the city carry a type tag (`school`, `school:de` or `isced:level`;
check `facility_subtypes_complete`, `docs/osm_tagging.md`); then `primary_school` and
`secondary_school` follow.

**Facility locations.** OSM nodes are used as they are. Polygons (e.g. a supermarket building or
a school site) are represented by one representative point inside the polygon. **Parks and
playgrounds** are represented by **access points**: the intersections of walkable ways with the
park boundary; if there are none, points along the boundary every 50 m; at most *N* points per
park (spacing and *N* in `config/config.yaml`). A park counts **once** if at least one of its
access points is reachable within the budget; its travel time is the minimum over all access
points. The app shows the park area and its access points and says so: "Measured to the nearest
park entrance (where a path meets the boundary). A park counts once." (display only, no change
of the measurement). Informative tags of a facility (opening hours, wheelchair access, address,
contact, speciality; `facility_tags` in the config) are displayed as stored and never change a
count.

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

### 4b. Flexible accessibility score (display only)

The app can combine several categories into one score per cell. For cell *i*, profile *m*, the
selected categories *S* and, per category, a time threshold $t_c$ (minutes, at most the facility
budget), the facilities needed $k_c \ge 1$ and a weight $w_c \ge 0$:

$$A_{ic}(t_c) = \#\{\text{facilities of } c \text{ reached from } i \text{ within } t_c\},\qquad
\text{coverage}_{ic} = \min\!\left(1, \frac{A_{ic}(t_c)}{k_c}\right),\qquad
\text{score}_i = 100 \cdot \frac{\sum_{c \in S} w_c \,\text{coverage}_{ic}}{\sum_{c \in S} w_c}.$$

- **Defaults:** $t_c$ = the facility budget (15 min), $k_c$ from the config, $w_c = 1$. With the
  defaults, one category gives $100\,(1 - U_{ic}/P_i)$, the saturating coverage of the deficit
  (§4), so map, deficit and recommender stay consistent; the class map is the special case
  "one category, defaults" and stays the default view.
- **Threshold:** the routing stores only facilities within the budget, so $t_c$ cannot exceed it
  (sliders stop there). Times are minimum travel times over a facility's routing points.
- **Data:** per cell and category the sorted times of the nearest facilities
  (`GET /api/cells/times`, at most `api.score.max_times_per_category`, default 5); the browser
  computes the score, so changing a parameter needs no request. $k_c$ is capped at that number.
- **Display:** five bins (0–19, 20–39, 40–59, 60–79, 80–100); score 100 (everything selected
  fulfilled) is outlined; the legend gives the share of residents per bin and the share who reach
  everything selected; a district shows the resident-weighted mean score.
- **Not part of the score (yet):** public transport (own supply classes, §3). The score is a
  display aggregate: it is never stored, ranked or used by the recommender (§5), which works per
  category.

## 5. Recommender

**Objective.** For a new facility of category *c* at candidate site *x* with catchment
$C(x)$ (cells reaching *x* within the budget):

$$\Delta W(x, c) = \sum_{i \in C(x)} P_i \cdot \left[\min\left(1, \tfrac{A_{i,c}+1}{k_c}\right) - \min\left(1, \tfrac{A_{i,c}}{k_c}\right)\right]$$

Population-weighted gain in saturating coverage. It equals the reduction of the deficit sum
$\sum_i U_{i,c}$ (§4) when $A_{i,c}$ grows by one in the catchment. The objective is monotone and
submodular in the set of added sites, so greedy selection has a $(1 - 1/e)$ approximation
guarantee.

**Procedure**

1. Candidates: 100 m Zensus grid cells (populated or not; spacing in `config/config.yaml`) whose
   centre lies inside the urban boundary (`architecture.md` O17), filtered by OSM land use (no
   water, forest, farmland, nature reserves, and protected areas of a nature-protection class:
   `protect_class` 1–4 and 7). Industrial and commercial land stays allowed: supermarkets and
   doctors are often located there. Other protected areas stay allowed: landscape protection and
   nature parks (class 5, e.g. Naturpark Schönbuch around villages), cultural heritage (class
   22, e.g. the Altstadt ensemble) and areas without a class; their number and area are reported. Only candidates within the prefilter reach
   of a cell with a deficit for the profile are routed; the others cannot gain anything.
2. Catchment of each candidate via Valhalla matrix (cells as sources, candidate centre as target,
   in groups of candidates, `architecture.md` §6.4); it is the same for every category of a
   profile.
3. Greedy per category and profile: pick the candidate with the largest $\Delta W$, update
   $A_{i,c}$, recompute, repeat until top-*N* zones are chosen or the best gain falls below a
   minimum (both in config). Each zone is chosen at most once; where $k_c \ge 2$ a neighbouring
   zone can still rank high, because a second facility helps the same residents (pure
   objective, no minimum spacing).
4. Output: **ranked zones** (the 100 m candidate cell, not an exact site) with the gain
   $\Delta W$, residents gaining access (cells that had $A_{i,c} = 0$), residents reaching
   "sufficient", the catchment (cells and residents) and an uncertainty note.
5. Optional equity mode (prioritise the worst-served cells) **[M4]**.

**Stated limits (shown in the app):** accessibility only; zoning, parcels, minimum catchment,
capacity and statutory planning (e.g. *Bedarfsplanung* for doctors) are not considered; results
depend on $k_c$ and OSM completeness.

## 5b. Housing potential (display only)

**Question.** Where would new homes already have good 15-minute access? The counterpart of the
recommender (§5): there a facility is placed where people lack access, here people are placed where
access is good — the *Innenentwicklung* question.

**Candidates.** 100 m Zensus grid cells **without residents** (no residents in the 2022 census: every Zensus cell with residents is
excluded, also outside the scoring scope, e.g. in neighbouring municipalities), whose centre lies inside the urban boundary grown by
`housing.edge_buffer_m` (200 m, so that the edge of town counts), outside the OSM land use of
the recommender's exclusion list (water, forest, farmland, nature reserves, protected areas of a
nature class) and, in addition, outside industrial areas, cemeteries and parks
(`housing.exclude_tags`). A cell the census shows empty can be built up since; the app says so.

**Counting.** Like a resident cell (§1, §4): the Valhalla matrix from the candidate's centre to
the facility points within the facility budget, counts $A_{i,c}$ and nearest times per category,
for the profiles in `housing.profiles` (walking 3.39 and 5.0 km/h). Transit supply is not
counted. Counts and times are stored raw; classes (as `scores`) and the score are derived.

**Score.** The accessibility score of §4b with the same selection and parameters as the map
(default: all weights 1, $k_c$ from the config), so a housing cell and a residents' cell with the
same facilities get the same score. The app lists the ten best cells.

**Stated limits (shown in the app):** accessibility only; ownership, zoning (*Bebauungsplan*,
*Flächennutzungsplan*), noise, flood risk, soil and nature protection other than the listed classes
are not considered; adjacent cells with the same score are separate entries (no merging into
sites).

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
| V10 | Matrix vs. /route (in every run, `validate_results`, report part 2): a sample of counted pairs near the budget compared with /route (`matrix_vs_route`, Δ time), a sample of uncounted pairs within the prefilter reach routed with /route (`false_negatives`, warns above 0.5 %, fails above 2 %), and the flip rate from both: share of pairs on which matrix and /route lie on different sides of the budget, per profile and direction (`budget_flips`, warns only) | How often does the matrix decide differently from a single route near the budget, and in which direction? (notes N8, N9) |
| V11 | With vs. without slopes (planned, P7): counts of the walking and wheelchair profiles on the production tiles vs. a one-off elevation-free tile set built from the same PBF; compare counts, classes and residents per class, by district | How much do slopes change the classes, and where (hillside districts vs. valley)? |

Gate G1 (does elevation change walking times in Valhalla?) is answered: yes, for walking and
wheelchair as well as cycling (`architecture.md` §6.1, notes N5); its effect on the results is V11.

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
| v0.10 | 2026-11-10 | New §5b: housing potential (unpopulated grid cells inside the urban boundary + 200 m, land-use filtered, counted like resident cells for walking 3.39/5.0, scored with §4b); display only | App iteration W8 (point 12, E7); confirmed by Juju (plan v0.1) |
| v0.9 | 2026-11-10 | New §4b: flexible accessibility score (weighted mean of per-category coverage with time threshold, facilities needed and weight; defaults equal the deficit coverage); display only, computed in the browser from `/api/cells/times` | App iteration W7b (points 1, 3); approved by Juju (10 Nov 2026) |
| v0.8 | 2026-11-10 | §2: parks and playgrounds are separate categories (k = 1 each); access rule (private, no, customers dropped for parks and playgrounds only); category groups and `require`/`exclude` conditions; school split waits for the 95 % type-tag gate | App iteration W7a (points 1, 2, access fix); approved by Juju (10 Nov 2026); 1 of 42 schools in the city carries a type tag, so no school split yet |
| v0.7 | 2026-11-09 | §2: the app shows park areas and access points with a sentence on how parks are measured; informative OSM tags are displayed only, never counted | App iteration W5 (points 16, 17); confirmed by Rico (plan v0.1) |
| v0.6 | 2026-11-06 | §5: ΔW = reduction of the deficit sum; candidates = 100 m grid cells inside the urban boundary, land-use filter without industrial and with protected areas only of nature classes (1–4, 7), only candidates within reach of a deficit routed; catchment per profile; greedy with top-*N* and minimum gain, each zone once (no spacing); output fields | P7 recommender; decisions by Rico (6 Nov 2026): keep industrial land use (supermarkets, doctors), pure objective for k ≥ 2, protected areas only of nature classes (heritage protection excluded the Altstadt) |
| v0.5 | 2026-11-06 | §1: known limitation of the wheelchair profile (steps avoided, steep sections not; counts optimistic on hillsides) | N11: `max_grade` has no effect in Valhalla 3.9.1; architecture v0.17; no change to counts |
| v0.4 | 2026-11-06 | §1: speeds are flat-ground speeds, Valhalla's slope model reduces them, results conservative; §6: new experiments V10 (matrix vs. /route: `matrix_vs_route`, `false_negatives`, flip rate `budget_flips`) and V11 (with vs. without slopes, P7), G1 answered | N5 settled (decision by Rico: keep the slope model, no change to counts); the matrix-vs-/route checks of N8/N9 had no V-number; architecture v0.16 |
| v0.3 | 2026-11-02 | §1 unit = populated cells inside the city boundary (was: urban boundary); §5 candidates restricted to the urban boundary | Architecture v0.12, O11 (notes N3) |
| v0.2 | 2026-11-02 | §2 facility locations (representative point for polygons, access points for parks and playgrounds, park counted once with minimum time); §3 transit supply for walking and wheelchair profiles, raw values stored, classes derived at read time | Answers to the P0 implementation plan questions (Q1, Q5) |
| v0.1 | 2026-11-02 | Created from the still valid parts of `architecture_proposal.md` (§5 scoring, §8 validation, §9 recommender), updated to current decisions (profiles, coarse categories, urban boundary, cell centroid) | Replace the outdated proposal with one binding methodology document |
