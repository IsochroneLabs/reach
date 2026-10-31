# 15-Minute City Analyzer: System Architecture & Decisions

> Course context: DS500 Data Science Project (Tübingen, WT 2026/27), Topic 9 "The 15-Minute City". Team of 2-4, interim presentation 25 Nov 2026, project submission 22 Jan 2027, final presentation 29 Jan 2027. The product must run automatically on new data, be validated, be documented, and be hosted (bwCloud).
> Status: working draft. Items marked **[DECIDE]** must be settled in Section 3 before coding starts. Items marked **[VERIFY]** are assumptions that need a quick test.
> Scope of this file: technical and architectural decisions only. Team organization, individual contributions, presentation planning and questions for the supervisors are in `project_management_decisions.md`.

---

## 1. Project Objective & Core Concept

Measure and improve neighborhood accessibility using the 15-minute city framework, applied to one German region first and designed so that further regions can be added by configuration.

The platform follows the methodology of Mouratidis (2026, *Travel Behaviour and Society* 42, 101151) and combines two dimensions:

1. **Proximity-based accessibility:** walking access to disaggregated lower-order daily amenities.
2. **Public transport supply:** scheduled weekday departures reachable within a 10-minute walk.

On top of the measurement layer, the platform provides a **facility placement recommender**: it ranks candidate locations and amenity types by the population-weighted improvement in accessibility they would create.

What we take from the paper, and what we add:

| From Mouratidis (2026) | Our addition |
| --- | --- |
| Five-step pipeline: definition, data, measurement, visualization, analysis | Fully automated, scheduled version of that pipeline |
| Disaggregated lower-order facilities | Same, with an explicit facility catalog (Section 4.3) |
| Inclusive walking speed 3.39 km/h (850 m in 15 min) | Selectable speed presets and optional terrain-aware mode |
| Lack vs. insufficient accessibility classes | One formal scoring spec (Section 5) |
| Cluster/hot-spot analysis and MGWR (Core or stretch depending on D19) | Prescriptive recommender plus its validation |

---

## 2. Scope & Staging ("Architect for many regions, deliver one")

- **Delivered scope:** one study region (see decision D1). Everything is parameterized by a region config (boundary, extract URLs, thresholds), so a second region is a config change plus a pipeline run.
- **Stretch:** a second region, then Baden-Württemberg or Germany-wide runs on the university cluster (bwUniCluster) as an optional accelerator. Nationwide coverage is **not** a graded requirement and must not block the core deliverables.
- **Coordinate systems:** store geometry in EPSG:4326, compute distances in EPSG:25832 (ETRS89 / UTM 32N, appropriate for Baden-Württemberg), and use EPSG:3035 only where the Zensus grid requires it.
- **Extensibility:** table schemas are source-agnostic, so the Zensus grid can be replaced by Eurostat GEOSTAT or GHSL grids without API changes.

---

## 3. Fundamental Decisions Before Coding

These decisions shape the schema, the pipeline and the validation. Each needs an owner and a decision by the date shown. Where a decision depends on an experiment, the gate says what result settles it.

| # | Decision | Options | Recommendation | Settled by |
| --- | --- | --- | --- | --- |
| D1 | **Study region and boundary** | Tübingen + Reutlingen district; Stuttgart city; Freiburg; a whole Regierungsbezirk | One mid-sized city with real topography and a functional (not purely administrative) boundary. Stuttgart or Freiburg stress-test the terrain logic; Tübingen is small enough for fast iteration and is the local context. Pick one primary region; a second is the stretch goal. | Week 1 |
| D2 | **Counting method** (how facilities are counted per grid cell) | (a) Isochrone polygons + point-in-polygon; (b) network distance counting (one-to-many, e.g. pandana, r5py, or Valhalla matrix) | (b) for the batch baseline, because polygons are smoothed and a facility inside a polygon is not necessarily reachable. Use isochrone polygons only for display. | After gate G1 |
| D3 | **Routing engine and terrain handling** | Valhalla; r5py (R5) with Tobler-style slope cost; pandana on a self-built graph | Decide by test G1 below. Valhalla is attractive for live isochrones; r5py is attractive if terrain-adjusted time is needed. | After gate G1 |
| D4 | **Scoring specification** | See Section 5 | One deficit formula, one threshold table, one definition of classes. Written down and frozen before any scoring code. | Week 1-2 |
| D5 | **Facility catalog and tag mapping** | OSM tags only; OSM + official lists (e.g. state data for schools, Kitas) | OSM as baseline, plus at least one authoritative source for one category to measure OSM completeness. | Week 2 |
| D6 | **Walking speed presets** | 3.39 km/h only; 3.39 and 5.0 km/h | Default to 3.39 km/h (850 m in 15 min, as in the paper). Offer 5.0 km/h as a comparison preset. | Week 1 |
| D7 | **Demand definition** | Total residents; residents by age group | Total residents as default. Age-weighted demand only if the Zensus 100 m grid actually provides it **[VERIFY]**. Disclosure control may perturb small cells. | Week 2 |
| D8 | **Recommender formulation** | Greedy maximum coverage with saturation; exact MILP; p-Median | Greedy on a saturating objective (monotone submodular, so greedy has a (1 - 1/e) guarantee) plus an exact MILP on small instances to measure the optimality gap. Treat "MCLP / p-Median" as related work, not as what we implement. | Week 3 |
| D9 | **Candidate location generation** | Any grid cell; cells with demand clusters; OSM land use restricted to plausible sites | Candidates from high-deficit clusters, filtered by land use (exclude water, forest, industrial). Output ranked zones with uncertainty, not a single exact point. | Week 3-4 |
| D10 | **Equity vs. efficiency objective** | Maximize population served only; add a "worst-off first" mode | Implement both, because the paper's motivation is socio-spatial inequality. Compare results in the report. | Week 4 |
| D11 | **Rural and low-density handling** | Same thresholds everywhere; thresholds by settlement type | Stratify by density class (e.g. via Zensus density or a degree-of-urbanisation class) so that villages are not all "lacking". Keep strata few and documented. | Week 2 |
| D12 | **Automation architecture** | Makefile; Snakemake; Prefect/Dagster; GitHub Actions | One orchestrated pipeline invoked by a single command, idempotent and resumable, with a scheduled refresh. Pick the tool the team can maintain (Makefile + Python for simplicity, Snakemake or Prefect if dependencies grow). | Week 1 |
| D13 | **Hosting and sizing** | bwCloud VM flavors and quota | Check available flavors, disk and RAM now. Everything that runs at request time must fit that VM. | Week 1 |
| D14 | **Geocoding and basemap** | Public Nominatim (not allowed for heavy use); self-hosted Nominatim/Photon for the region; hosted free-tier service | Self-hosted Photon or Nominatim for the study region, or restrict search to a neighborhood/district picker if geocoding proves too heavy. Basemap from an open vector tile source with correct attribution. | Week 2 |
| D15 | **Validation plan** | Informal checks only; defined experiments | Defined experiments (Section 8), because validation is a graded criterion. | Week 2 |
| D16 | **Repository and code workflow** | Ad hoc; defined workflow | GitHub repo from the start with branch protection, pull-request reviews, issues and a project board, so the history is readable by an external party. Team roles and contribution tracking are team decisions, see `project_management_decisions.md` (T1, T2). | Week 1 |
| D17 | **Definition of done and cut list** | Everything; core only | Core = Sections 4-8 for one region. Everything in Section 10 is stretch and is cut first. | Week 1 |
| D18 | **Travel modes** | Walking only; walking plus cycling; walking plus cycling as stretch | Walking only for Core: the paper argues it is the more inclusive basis, and every threshold, speed and validation experiment is built around it. The brief's topic text says "walk or bicycle ride", so state the choice and its reason explicitly in the README and the presentations, and keep the mode a config parameter so cycling can be added later (see Section 10). Confirm with the supervisors (`project_management_decisions.md`, T7). | Week 1 |
| D19 | **Analytical method beyond counting** (the brief asks for "adequate methods, traditional statistics or machine learning") | (a) Optimization plus sensitivity analysis only; (b) add spatial statistics (Global/Local Moran's I, hot spots) as Core; (c) add spatially varying regression (GWR/MGWR) of accessibility on density and distance to center as Core | At least (b) as Core: it is cheap once the grid results exist (PySAL), it reproduces part of the paper's step 5, and it gives the recommender candidate clusters a statistical basis. Treat (c) as stretch. If the team chooses (a), the report must argue why optimization with the validation experiments counts as the analysis method. | Week 2 |
| D20 | **Reproducibility acceptance test** (a person who did not write the code runs the analysis) | No explicit test; documented test | Defined test: a team member who did not write the pipeline starts from a clean machine or VM, follows only the README, and runs the pipeline for the study region and then for a newer data snapshot or a second region config, without editing code. Repeat before submission. | Week 1 (define), Jan (run) |
| D21 | **Reporting unit for "neighborhoods"** | Raw 100 m grid only; official city districts (Stadtbezirke/Stadtteile); statistical blocks; custom clusters | Compute everything on the grid, report on official districts from the city's open data, because planners know them and the brief talks about neighborhoods. Check that boundaries are available as open data. | Week 2 |

### Gate G1: terrain and routing test (week 1, blocking D2/D3)

Run on a steep neighborhood of the chosen region, with identical origins:

1. Compute a 15-minute catchment with terrain handling off and on.
2. Check that the catchment area and the set of reachable facilities actually change, in the expected direction (steep uphill shrinks the catchment).
3. Verify the meaning of Valhalla's `use_hills` parameter. As documented, it expresses the pedestrian's willingness to tackle hills (low = avoid hills, high = indifferent to hills). The toggle in the UI must be defined from the tested behavior, not assumed.
4. Check whether slopes affect elapsed time or only route cost, since isochrone contours are cut by time. If only cost changes, terrain will not shrink time-based catchments, and we use a time-based slope function (e.g. Tobler's hiking function) on our own graph instead.
5. Check DEM resolution. 30 m global models miss short steep sections and stairs; state-level terrain models are better where license and size permit **[VERIFY]**.

Outcome: a one-page note stating which engine, which counting method, and what the terrain toggle really does.

---

## 4. Data Sources & Specifications

### 4.1 Street and footpath graph

OpenStreetMap via Geofabrik regional extract (`baden-wuerttemberg-latest.osm.pbf`, clipped to the study region). Includes footpaths, steps, crossings and pedestrian zones. Download is scripted and versioned by snapshot date.

### 4.2 Topography

Digital elevation model: state-level DGM where available and license-compatible, otherwise Copernicus GLO-30 or SRTM. **[VERIFY]** resolution, license and download automation.

### 4.3 Amenities (disaggregated, lower-order only)

Extracted from OSM and kept separate per category, following the paper. Examples (final tag mapping fixed in D5):

| Function | Categories (kept separate) |
| --- | --- |
| Food | Supermarkets, discounters, bakeries, greengrocers |
| Health | General practitioners, pharmacies, dental clinics |
| Childcare and education | Kindergartens/daycare, primary schools, secondary schools |
| Leisure | Parks, playgrounds, public squares |
| Transport | Stops with scheduled departures (from GTFS) |

Excluded: specialized higher-order destinations (specialized hospitals, universities, specialized shops).

**Known data issue:** OSM tagging is uneven (general practitioners in particular). Every category gets a completeness note, and at least one category is compared against an authoritative list (D5).

### 4.4 Public transport supply

GTFS feeds for the region (DELFI / state or regional feeds). Pre-aggregate scheduled weekday departures per stop for a reference weekday. **[DECIDE]** whether to weight modes (rail vs. bus) or keep raw counts, as the paper does; the simplest defensible choice is raw counts, with weighting as a documented extension. Each feed's license and validity period is stored in the provenance table.

### 4.5 Population grid

Destatis Zensus 100 m x 100 m grid (INSPIRE). Used as the origin of all measurements and as the demand weight. Cell counts below disclosure thresholds may be perturbed, so results are interpreted at neighborhood level, not cell level. Age-group attributes at 100 m are **[VERIFY]** (D7).

### 4.6 Provenance and versioning

A `data_sources` table records, per run: source, version/snapshot date, license, download URL, checksum. Every result row references a `run_id`, so any map can be reproduced.

---

## 5. Scoring Specification (single source of truth)

This section replaces all earlier formula variants. Implementation code and UI text must follow it.

**Definitions**

- Cell *i*: population grid cell with population $P_i$.
- Category *c*: one disaggregated facility category.
- $A_{i,c}$: number of category-*c* facilities reachable from cell *i* within the time budget (15 minutes for facilities, 10 minutes for transit stops), at the selected walking speed.
- $k_c$: sufficiency threshold for category *c* (the count at which more facilities no longer add meaningful accessibility).

**Classes**

| Class | Rule |
| --- | --- |
| Lack of accessibility | $A_{i,c} = 0$ |
| Insufficient accessibility | $0 < A_{i,c} < k_c$ |
| Sufficient accessibility | $A_{i,c} \ge k_c$ |

**Deficit (unsatisfied demand)**

$$U_{i,c} = P_i \cdot \max\left(0,\; 1 - \frac{A_{i,c}}{k_c}\right)$$

**Sufficiency thresholds $k_c$ (proposed, to be frozen in D4)**

| Category | $k_c$ | Rationale |
| --- | --- | --- |
| Supermarket/discounter | 2 | The paper treats 1 grocery store as insufficient and 2-4 as medium |
| Pharmacy | 1 | One pharmacy is acceptable (paper's own example) |
| General practitioner | 2 | Choice and capacity; subject to OSM completeness |
| Dentist | 1 | Low-frequency use |
| Kindergarten/daycare | 2 | Choice and capacity |
| Primary school | 1 | Catchment-based provision |
| Secondary school | 1 | Catchment-based provision |
| Playground / park | 1 | Presence within walking distance |
| Public transport supply (daily departures within 10 min) | 1,000 (provisional) | The paper's classes are 0 / 1-150 / 151-1,000 / above 1,000, derived from Copenhagen. Calibrate to the German distribution in the study region before use |

Rules that follow from this spec:

- Where $k_c = 1$, the class "insufficient" is empty; the scorecard shows only lack/sufficient for that category.
- Thresholds may differ by density stratum (D11); the stratum and threshold used are stored with each run.
- Raw counts are stored; classes and deficits are derived at read time, so changing a threshold never requires recomputing the network step.

---

## 6. Technical Architecture

```text
 [ Browser: React + MapLibre GL ]
        |  HTTPS                         
 [ Reverse proxy (TLS, caching) ]
        |
   +----+-----------------+------------------------+
   |                      |                        |
 [ API: FastAPI ]   [ Tile server /          [ Static assets ]
   |                  PMTiles files ]
   |
   +--> [ Job queue (e.g. Redis + worker) ] --> [ Workers: scenario scoring, recommender ]
   |
   +--> [ Routing engine (live isochrones, display only) ]
   |
 [ PostgreSQL + PostGIS ]  <---  [ Pipeline (orchestrated, scheduled) ]
   - grid cells, facilities, stops                - download + checksum
   - accessibility results (raw counts)           - validate + clean
   - recommendations, runs, provenance            - network counting (batch)
                                                  - scoring + recommender
                                                  - tile build
```

### Component stack (to be finalized after G1)

| Component | Proposed implementation | Role |
| --- | --- | --- |
| Pipeline orchestration | Makefile/Python, or Snakemake/Prefect (D12) | Single-command, idempotent, resumable; scheduled refresh |
| Routing for batch counting | pandana, r5py or Valhalla matrix (D2/D3) | Count reachable facilities per cell by network distance or time |
| Routing for display | Valhalla (or engine chosen in D3) | Live isochrones for the explorer; display only |
| Spatial database | PostgreSQL 16 + PostGIS 3.4 | Grid, facilities, stops, results |
| Tiles | Pre-built PMTiles for baseline layers (tippecanoe); dynamic vector tiles only for scenarios | Fast maps with tens of thousands of cells |
| API | FastAPI | Scoring, scenarios, recommendations; long jobs via the queue |
| Frontend | React + MapLibre GL JS (one rendering library; add deck.gl only if a concrete layer needs it) | Maps, scorecards, scenario UI |
| Geocoding | Self-hosted Photon/Nominatim for the region, or district picker (D14) | Address search |
| Hosting | bwCloud VM with Docker Compose (D13) | Public, reachable by graders |

### Design rules

1. **Batch counting uses network counting, not polygon containment** (D2).
2. **Batch from the facility side where it is cheaper:** compute a catchment per facility and accumulate onto cells, which scales better than one isochrone per populated cell.
3. **Reverse reachability:** the recommender needs "who can reach a facility placed at x". With terrain, forward and reverse walking times differ. Either use a routing engine that supports reverse expansion or document the approximation **[VERIFY]**.
4. **Long computations never run in a request handler.** They run in workers and report progress.
5. **Raw results are stored once** and classified on read.

---

## 7. Pipeline, Automation & Error Handling

The brief gives automation "very high weight": someone who did not write the code must be able to run it on new data without touching it.

**One-command run:** `make all REGION=<name>` (or equivalent) performs: download, validate, build graph, count, score, recommend, build tiles, load database.

**Scheduled refresh:** a scheduled job (cron or CI) checks sources for new versions (OSM snapshot, GTFS feed validity period), reruns only affected steps, and publishes new results under a new `run_id`. The previous run stays available until the new one passes validation.

**Automated validation (runs inside the pipeline, fails loudly):**

- Boundary: geometry valid, area within expected range.
- Population: totals within tolerance of published totals; no negative or missing counts; cells with population but no walkable road within a set distance are flagged.
- Facilities: counts per category within plausible ranges versus the previous run; points outside the boundary or on water flagged; duplicates merged.
- GTFS: feed validity dates cover the reference weekday; stops with zero departures flagged; implausible departure counts flagged as outliers.
- Results: no negative counts; monotonic relationships hold (a 15-minute count is never smaller than a 10-minute count for the same category).

**Error handling:** retries with backoff for downloads, checksum verification, schema checks that stop the run with a readable message, and a validation report written to disk and shown in the app (data date, source, warnings).

**Reproducibility test (D20):** a team member who did not write the pipeline runs it from a clean environment using only the README, once for the study region and once for a newer snapshot or second region config, without editing code. Problems found are fixed in the README or the pipeline, not explained verbally.

---

## 8. Validation of Results

Validation is a graded criterion, so these experiments are part of the deliverable.

1. **Counting method agreement:** compare network counts with isochrone-polygon counts on a sample of cells; report differences and justify the method chosen.
2. **OSM completeness:** compare one facility category with an authoritative list; report recall and precision.
3. **Back-testing the recommender:** remove a random subset of existing facilities of one category, run the recommender, and measure how often and how closely it recovers the removed locations.
4. **Greedy versus exact:** solve small instances with an exact solver (e.g. OR-Tools or PuLP/CBC) and report the optimality gap of the greedy solution.
5. **Sensitivity analysis:** vary $k_c$, walking speed and time budget; report how rankings and recommended locations change.
6. **Terrain effect:** report how many residents change class when terrain handling is on versus off (if G1 confirms terrain affects time).
7. **Plausibility check with local knowledge:** compare the highest-deficit areas against known neighborhoods; document agreements and disagreements.
8. **Spatial statistics (if D19 option b or c is chosen):** report Global Moran's I per category, Local Moran's I clusters or hot spots, and (for option c) the model fit and coefficient maps; check that recommender candidates fall in statistically significant deficit clusters.
9. **Reproducibility (D20):** result of the clean-environment run by a non-author, including every step where the README was insufficient.

---

## 9. Optimization & Recommender Formulation

**Objective.** For a facility of category *c* placed at candidate *x*, with catchment$(x)$ the set of cells that can reach *x* within the time budget:

$$\Delta W(x, c) = \sum_{i \in \text{catchment}(x)} P_i \cdot \left[\min\left(1, \frac{A_{i,c} + 1}{k_c}\right) - \min\left(1, \frac{A_{i,c}}{k_c}\right)\right]$$

This is the population-weighted gain in saturating coverage. It is monotone and submodular in the set of added facilities, so the greedy algorithm (pick the candidate with the largest marginal gain, update $A_{i,c}$, repeat) has a (1 - 1/e) approximation guarantee for the chosen objective.

**Procedure**

1. Build candidates from high-deficit clusters, filtered by land use (D9).
2. Compute each candidate's reverse catchment with the same counting method as the baseline.
3. Select greedily; recompute marginal gains after each placement.
4. Report results as **ranked zones with population gain, class changes, and uncertainty**, not as exact coordinates.
5. Optional equity mode: weight cells by deprivation or prioritize cells with the lowest accessibility (D10).

**Limits stated in the product**

- The recommender considers accessibility only. It ignores zoning, available parcels, minimum viable catchment, existing capacity and, for physicians, the statutory planning of practice seats (*Bedarfsplanung*).
- Results depend on thresholds $k_c$ and on OSM completeness; both are shown next to every recommendation, with data date and source.

---

## 10. Stretch Goals (cut first)

- Second region or Baden-Württemberg-wide run on the cluster.
- Age-weighted demand (kindergarten by children, pharmacies/GPs by seniors), if the grid supports it.
- MGWR comparing deficits with density and distance to center (as in the paper). Hot-spot analysis and Moran's I are Core if D19 option b is chosen, otherwise also stretch.
- "What-if" sandbox with live scenario recomputation.
- Mode-weighted transit supply.
- Cycling as a second mode (D18); needs its own speed, distance thresholds and graph profile.

---

## 11. Deployment, Security & Privacy

- Docker Compose on bwCloud: reverse proxy, API, database, tile files, routing engine, worker.
- Backups of the database and of pipeline outputs; the dataset is not committed to Git, and supervisors can get read access via a dedicated database user (course requirement).
- Rate limits on endpoints that start jobs; do not log addresses or pin-drops beyond what is needed for debugging, and state retention in the README.
- Attribution: OpenStreetMap (ODbL), GTFS feed licenses, Destatis terms, basemap provider.

---

## 12. Repository & Documentation Plan

```text
repo/
  README.md              # purpose, quick start, order of execution
  docs/                  # architecture, scoring spec, data dictionary, validation report
  pipeline/              # download, validate, count, score, recommend, tiles
  api/                   # FastAPI app
  web/                   # frontend
  config/                # region configs, thresholds, tag mapping
  tests/                 # unit and data-validation tests
  deploy/                # Compose files, scripts
```

The README must state which commands to run and in what order, and how a new person refreshes the data. The scoring spec (Section 5) and the data dictionary are the documents code must match.
