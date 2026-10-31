# Product Features & Functional Requirements

This document lists the user-facing capabilities, analytical models and delivery phases of the 15-Minute City Platform. Scoring rules are defined once, in `architecture_proposal.md`, Section 5, and are not repeated here with different numbers. Decisions still open are in Section 3 of that file.

**Priority labels:** **Core** = required for the graded deliverable. **Stretch** = built only if Core is finished and validated.

**Primary user:** municipal and district planners (and the course graders acting as such). Citizens and residents are a secondary audience served by the same map.

---

## 1. Neighborhood Accessibility Map (Core)

*Users: planners, residents, researchers*

* **Region selector and map:** Pick the study region and view accessibility on the 100 m Zensus grid or aggregated to official city districts (reporting unit, decision D21). Detail at cell level is shown with a note that small cells may be perturbed by disclosure control.
* **Travel mode:** Walking only in Core (decision D18). The mode is a configuration parameter; cycling is a stretch goal and is not shown in the UI until it is validated.
* **Per-category layers (disaggregated):** One layer per facility category, never grouped into broad classes:
  * *Food:* supermarkets, discounters, bakeries, greengrocers
  * *Health:* general practitioners, pharmacies, dental clinics
  * *Childcare and education:* kindergartens/daycare, primary schools, secondary schools
  * *Leisure:* parks, playgrounds, public squares
* **Class view:** Lack / Insufficient / Sufficient per category, exactly as defined by the scoring spec. A separate "lack only" view shows areas with zero access.
* **Population statistics panel:** Number and share of residents in each class per category and per district (for example "12% of residents have no grocery store within a 15-minute walk").
* **Walking speed preset:** Inclusive (3.39 km/h, 850 m in 15 min, following Mouratidis 2026) as default; 5.0 km/h as comparison.
* **Data transparency:** Every view shows data sources, snapshot dates and known data-quality warnings from the pipeline's validation report.

**Acceptance:** classes and statistics in the UI match the scoring spec for a hand-checked sample of cells.

---

## 2. Public Transport Supply Layer (Core)

* **Departure-based supply:** Total scheduled weekday departures at stops reachable within a 10-minute walk (565 m at the inclusive speed on flat ground), not just stop presence.
* **Classes:** Lack (0), insufficient (1-150), medium (151-1,000) and high (above 1,000), as in the paper's Copenhagen example. The upper thresholds are provisional until calibrated to the study region (decision D4).
* **Dual view:** Side-by-side or swipe comparison of walking accessibility to amenities and transit supply, plus a view of where both are lacking.
* **Feed information:** Shows which GTFS feed and validity period the numbers come from.

**Acceptance:** departure totals for a few sample stops match a manual count from the GTFS timetable.

---

## 3. Deficit & Equity Analysis (Core)

*Users: planners, civil society organizations, district councils*

* **Deficit index:** Unsatisfied demand per cell and category, using the single formula in the scoring spec:

  $$U_{i,c} = P_i \cdot \max\left(0,\; 1 - \frac{A_{i,c}}{k_c}\right)$$

  Unpopulated areas drop out automatically because $P_i = 0$.
* **District ranking:** Districts ranked by total deficit and by share of residents without access, so planners can compare absolute need and relative need.
* **Density strata:** Results are interpreted by settlement type (urban core, suburban, rural) so that sparse areas are not judged against urban expectations.
* **Spatial pattern diagnostics (Core if decision D19 option b or c is chosen, otherwise Stretch):** Global and Local Moran's I, hot-spot analysis and comparison with population density, as in the paper. Spatially varying regression (MGWR) of accessibility on density and distance to center is Stretch.
* **Demographic filters (Stretch, depends on data):** Child-weighted deficit for kindergartens and playgrounds, and senior-weighted deficit for pharmacies and general practitioners, only if the Zensus grid provides age data at a usable resolution.

---

## 4. Facility Placement Recommender (Core)

*Users: urban planning departments, municipal councils*

* **Recommendation per category:** For a selected district or the whole region and a chosen category, the tool proposes where adding one or more facilities gives the largest population-weighted gain in accessibility.
* **Category diagnosis:** Shows which missing category causes the largest population-weighted deficit in the selected area.
* **Output as ranked zones:** Each recommendation is a zone with the number of residents gaining sufficient access, the change in class counts, and an uncertainty note. It is not presented as a single exact coordinate.
* **Efficiency and equity modes:** One mode maximizes total residents served; another prioritizes the worst-served areas. The UI shows how the two differ.
* **Decision-support card:** A plain-language summary, always with its caveats, for example:

  > *"Adding a pharmacy in zone Z would give about N residents who currently have no pharmacy within a 15-minute walk access to one. Based on OSM data from <date>; capacity, zoning and parcel availability are not considered."*

* **Stated limits:** Every recommendation view states that it covers accessibility only, and does not account for zoning, land availability, viable catchment size, existing capacity or statutory planning rules (for physicians, *Bedarfsplanung*).
* **What-if sandbox (Stretch):** Drop a hypothetical facility on the map and see the change in accessibility, with terrain-aware catchments where supported.

**Acceptance:** the validation experiments in `architecture_proposal.md`, Section 8 (back-test, exact solver comparison, sensitivity analysis) are run and reported in the app or in the documentation.

---

## 5. Interactive Explorer (Core for routing display; terrain mode depends on gate G1)

* **Address search or pin-drop:** Search an address (via the self-hosted or district-based option from decision D14) or drop a pin.
* **Walking catchments:** Shows the 5-, 10- and 15-minute pedestrian catchments along sidewalks, paths, steps and crossings.
* **Reachable amenities:** Lists reachable facilities per category with the sufficiency scorecard (lack / insufficient / sufficient) rather than raw counts alone.
* **Terrain handling:** A switch between a planar network and a terrain-aware mode, **only if** gate G1 confirms that the chosen engine changes walking time with slope. The labels in the UI follow the tested behavior of the engine's parameters, not assumptions.
* **Consistency requirement:** Catchments shown in the explorer and counts used in the batch baseline must agree within a documented tolerance.

---

## 6. Automation & Operations (Core, graded)

* **One-command pipeline:** Download, validate, count, score, recommend, build tiles, load database.
* **Scheduled refresh:** Detects new OSM snapshots and GTFS feeds and recomputes affected results without manual steps.
* **Validation report:** Automatically generated, readable by non-programmers, and linked from the app.
* **Error handling:** Clear failure messages, retries for downloads, previous results kept until a new run passes validation.
* **Hosting:** Public instance on bwCloud and read access for supervisors to the database through a dedicated user.
* **Usable by someone who did not write the code:** README-only setup and run, tested by a non-author in a clean environment for the study region and for a newer data snapshot or second region config (decision D20).

**Acceptance:** the D20 reproducibility test passes without editing code, and every README gap found is fixed.

---

## 7. Deliverables Mapped to the Course

| Course requirement | Where it is met |
| --- | --- |
| Data acquisition | OSM, GTFS and Zensus downloads, scripted |
| Data preparation and validation | Pipeline validation checks and report |
| Data analysis | Scoring, deficit analysis, recommender, plus spatial statistics according to decision D19 |
| Validation of results | Experiments in `architecture_proposal.md`, Section 8 |
| Presentation (interactive) | Web app |
| Automation, usable without touching the code | One-command pipeline, scheduled refresh, D20 reproducibility test |
| Version control | GitHub repository from day one (decision D16) |
| Individual evaluation, presentations, motivation and literature, supervisor questions | See `project_management_decisions.md` |
| Documentation | README, architecture, scoring spec, data dictionary |
| 3-minute video | Non-technical walkthrough of the map, a deficit district and one recommendation |
| 3-sentence summary | Written once the Core scope is frozen |

---

## 8. Roadmap

Dates follow the course schedule. Reassess at each milestone and cut stretch items first.

| Period | Milestone | Deliverables |
| --- | --- | --- |
| Now to 14 Nov | **Decisions and gate G1** | Decisions D1-D21 and T1-T10 (`project_management_decisions.md`) recorded; terrain/routing test result; scoring spec frozen; repository, CI and region config set up |
| 14 to 25 Nov | **Interim presentation (25 Nov)** | Automated ingestion for one region, validation report v1, baseline accessibility map for 2-3 categories, plan for the rest |
| 25 Nov to 20 Dec | **Core measurement** | All Core categories, transit supply layer, batch baseline with the chosen counting method, deficit index, statistics panel |
| 20 Dec to 10 Jan | **Recommender and app** | Greedy recommender, decision-support cards, validation experiments, web app features, scheduled refresh |
| 10 to 15 Jan | **Feature freeze** | Stretch items only if everything above passes validation |
| 15 to 22 Jan | **Submission (22 Jan, 23:59)** | Deployment on bwCloud, README and documentation, 3-minute video, validation report, summary |
| 22 to 28 Jan | **Final preparation** | Slides due 28 Jan, 20:00; rehearsal with Q&A |
| 29 Jan | **Final presentation** | Live demo, architecture, validation results |

**Cut order if time runs short:** what-if sandbox, age-weighted demand, MGWR, cycling, terrain-aware mode, second region, nationwide run. Moran's I and hot spots stay if D19 made them Core.
