# Features & Roadmap

User-facing capabilities, priorities and delivery plan. **How** features are computed is defined
in [`methodology.md`](methodology.md) (what is measured) and [`architecture.md`](architecture.md)
(how the system works); this file does not repeat formulas or numbers.

**Priorities:** **Core** = required for the graded deliverable. **Stretch** = only after Core works
and is validated.

**Primary users:** municipal and district planners (and the course graders acting as such).
Residents are a secondary audience served by the same map.

---

## 1. Accessibility map (Core)

- Map of the urban area of Tübingen on the Zensus 100 m grid, aggregated to city districts.
- **Profile selector:** walking (3.39 km/h inclusive, 5.0 km/h comparison), cycling, wheelchair.
- **Category layers:** one layer per category (`methodology.md` §2: seven Core and eight extended
  categories), chosen in collapsible groups (food, health & care, education, green space, sport,
  services).
- **Class view:** lack / insufficient / sufficient per category; a "lack only" view.
- **Combined score (W7b):** tick several categories (grouped, with "All") for one accessibility
  score per cell, with time threshold, facilities needed and weight per category (`methodology.md`
  §4b); settings live in the URL, one category with the defaults stays the class map.
- **Statistics panel:** residents and share per class, per category and district
  (e.g. "12 % of residents have no pharmacy within a 15-minute walk").
- **Data transparency:** data sources, snapshot dates and validation warnings on every view;
  note that small cells are perturbed by census disclosure control.

**Acceptance:** classes and statistics in the UI match the scoring for a hand-checked sample of cells.

## 2. Public transport supply (Core)

- Weekday departures at stops within a 10-minute walk, with supply classes (`methodology.md` §3).
- Side-by-side view of facility access and transit supply; view of areas where both are lacking.
- Shows the GTFS feed, reference weekday and validity period.

**Acceptance:** departure totals for a few sample stops match a manual count from the timetable.

## 3. Deficit analysis (Core)

- Deficit per cell, category and profile; district ranking by total deficit and by share of
  residents lacking access.
- Spatial statistics on aggregated units if confirmed (`methodology.md` M5).

## 4. Pin-drop inspector (Core)

- Click a point: 5/10/15-minute isochrone, reachable facilities per category with travel times,
  weakest category, route line to the nearest facility per category.
- **Isochrone direction:** forward (where you get from the point), reverse (from where people
  reach it) or both, chosen in the map settings (`POST /api/isochrone`); on slopes they differ.
- Values come from the precomputed cell, so map and inspector always agree
  (`architecture.md` §6.5).
- **Click area and cell status:** clicks are accepted anywhere in the city; the inspector says
  whether the cell is scored (its residents), has no residents in the Zensus grid (values
  computed live) or lies outside the city boundary (not scored).
- **POI pins and routes:** the facilities reachable in the selected category show as pins with
  name and time on hover. A cell with fewer than the required number also gets a route to the
  *next* missing facility, dashed and labelled "beyond 15 min" when it is outside the budget. The
  facility list is clickable (zoom, pin highlight, route to exactly this facility).
- **Facility details and parks:** popup and picked facility show the informative OSM tags (opening
  hours as raw text, wheelchair access, address, speciality, brand, website, phone) and links to
  OpenStreetMap and Google Maps (search link only; no ratings). Parks are drawn with their outline
  and access points, and the note says that the time is measured to the nearest entrance. The
  setting "All facilities of the category" draws every facility of the selected category.
- **Spread view (Stretch-light):** street-level spread via Valhalla `expansion`, animated by time.

## 5. Recommendations (Core)

- Per category and profile: ranked candidate zones with residents gaining sufficient access,
  class changes and an uncertainty note (`methodology.md` §5).
- **Decision-support card** in plain language with caveats, e.g.
  > "A pharmacy in zone Z would give about N residents who currently have none within a
  > 15-minute walk access to one. OSM data from <date>; zoning, parcels and capacity not considered."
- Stated limits on every recommendation view.
- **Housing potential:** layer and "Top 10 cells for new homes" for cells without residents inside the urban boundary (+ 200 m), scored like the map (`methodology.md` §5b); accessibility only, limits shown.
- Equity mode (worst-served first) after the efficiency mode works (`methodology.md` M4).

**Acceptance:** validation experiments V3–V5 (`methodology.md` §6) are run and reported.

## 6. Automation & operations (Core, graded)

- One-command pipeline and weekly scheduled refresh; new results published only after validation.
- Validation report readable by non-programmers, linked from the app.
- Hosted on a public server (Hetzner CX23, `architecture.md` §11); read-only database user for
  supervisors.
- Usable by someone who did not write the code: README-only setup, tested by a non-author (V9).

**Acceptance:** V9 passes without editing code; every README gap found is fixed.

## 7. Stretch

What-if sandbox (place a hypothetical facility), finer categories (discounters, GPs, school
types), age-weighted demand (M6), transit routing, second city,
address search.

## 8. Course requirements

| Course requirement | Where it is met |
|---|---|
| Data acquisition | Scripted OSM (Geofabrik), GTFS (NVBW) and Zensus downloads |
| Data preparation and validation | Pipeline validation stages and report |
| Data analysis | Network accessibility counting, scoring, deficits, recommender, spatial statistics (M5) |
| Validation of results | Experiments V1–V11 (`methodology.md` §6) |
| Presentation (interactive) | Web app |
| Automation, usable without touching code | One-command pipeline, weekly refresh, V9 |
| Version control | GitHub repository, `CONTRIBUTING.md` |
| Individual evaluation, presentations, literature | `project_management_decisions.md` |
| Documentation | README, architecture, methodology, data contract, glossary |
| 3-minute video | Non-technical walkthrough: map, one underserved district, one recommendation |
| 3-sentence summary | Written once Core scope is frozen |

## 9. Roadmap

| Period | Milestone | Deliverables |
|---|---|---|
| until 8 Nov | **Foundations** | Code scaffold (uv workspace, Compose, CI), `data_contract.md`, CODEOWNERS, config with categories (M1) |
| 9–25 Nov | **Interim presentation (25 Nov, `v0.1.0`)** | Acquisition + validation for Tübingen, Valhalla tiles, first counts for 2–3 categories and walking, baseline map (local demo) |
| 25 Nov – 20 Dec | **Core measurement** | All categories and profiles, transit supply, scoring, district results, pin-drop, server live from ~1 Dec |
| 20 Dec – 10 Jan | **Recommender and app** | Greedy recommender, decision cards, validation experiments, weekly refresh |
| 10–15 Jan | **Feature freeze** | Stretch only if Core passes validation |
| 15–22 Jan | **Submission (22 Jan, 23:59, `v1.0.0`)** | Documentation, validation report, video, summary, V9 run |
| 22–28 Jan | **Final preparation** | Slides due 28 Jan, 20:00; rehearsal |
| 29 Jan | **Final presentation** | Live demo, architecture, validation results |

**Cut order if time runs short:** what-if sandbox, age-weighted demand, finer categories,
equity mode, spread view, spatial statistics beyond Moran's I.
