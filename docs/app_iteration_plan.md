# App iteration plan — 18 feedback points

> **Status:** v0.1 (9 Nov 2026), plan for agent sessions after P7. Written for Rico from a review of
> `dev` @ `342dfcf` and the local run `20261106T142630Z`. Once Rico confirms a work package, it
> counts as the confirmation of AGENTS.md ("A phase plan … counts as this confirmation") for the
> folders, files and contract changes that package **names**. Items marked **Ask first** still
> need their own "yes". Shared copy for discussion: Claude Doc "reach – 18 App-Punkte".

## 1. The 18 points and what we do

| # | Point (Rico, 9 Nov) | Decision | Package |
|---|---|---|---|
| 1 | Categorisation | Umbrella for 2 and 3: categories get a `group`, several can be selected | W7a, W7b |
| 2 | Split the groups (school → primary …) | Split by **OSM tags** (E3): parks / playgrounds, primary / secondary school; doctors not split (E4) | W7a |
| 3 | Filter several categories, aggregated view | Flexible **accessibility score 0–100** (E2) drives the colour scale | W7b |
| 4 | Green cell: show all POIs, not one route | With 6 | W4 |
| 5 | Left column clearer | Make it **easier to understand and more intuitive** (E1): plain-language labels, short explanations, collapsible sections, clear order | W1 |
| 6 | Green: pins with hover info; red/orange: route to the nearest POI also beyond 15 min, marked | Pins for reachable POIs; route to the next missing POI, dashed when beyond the budget | W4 |
| 7 | Pin in the cell centre, where routing starts | Marker moves to `cell.origin` | W1 |
| 8 | Toggle isochrones (5/10/15), grid, colours | Settings panel | W1 |
| 9 | No pin: colours; pin: isochrones only (default), toggle | Pin mode | W1 |
| 10 | Forward vs. reverse isochrone, choose which | New live endpoint with `direction` | W2 |
| 11 | Recommendations for cycling | Measure, then switch on (E6) | W6 |
| 12 | When is "no residents" shown; housing recommendations for empty cells with good access | Fix the message (three cases); new "housing potential" layer (E7 accepted) | W3, W8 |
| 13 | Drop the urban-boundary filter, score all populated cells; residents slider | Scoring already covers all populated cells in the city (O11, 99.9 %); slider in the web app; clicks in the whole city (E5) | W1, W3 |
| 14 | Pointer cursor over clickable points | Cursor per interactive layer | W1 |
| 15 | Settings button top right for map visuals | Settings panel | W1 |
| 16 | Click POIs in the list; more info (e.g. Google rating) | List click → map; info from OSM tags; **no Google rating** (rule 8, licence, cost), only a "open in Google Maps" search link | W4, W5 |
| 17 | Parks: routed to area or POI? Make it visible; POIs in settings | Routed to **access points** on the park boundary (methodology §2); show area + access points | W5 |
| 18 | Colour saturation slider / on-off | Cell opacity slider (keeps the checked palette) | W1 |

Finding during the review, added as W7a: **private playgrounds are counted.** The pipeline ignores
`access`; 65 `access=private` and 15 `access=customers` playgrounds (of 349) and 3 non-public parks
count as reachable (`docs/osm_tagging.md` §4, notes N14).

## 2. Decisions

| # | Question | Decision | Date |
|---|---|---|---|
| E1 | Point 5: "transparent" | Easier to understand and more intuitive (not a see-through panel) | 9 Nov 2026 |
| E2 | Combined view of several categories | Accessibility score normalised to 0–100 drives the colour scale; flexible: users choose time threshold, required count `k` and weights | 9 Nov 2026 |
| E3 | School types | OSM tagging (`school`, `school:de`, `isced:level`), no curated file; team tags in OSM | 9 Nov 2026 |
| E4 | GPs as own category | Not now; only what OSM tags support well | 9 Nov 2026 |
| E5 | Allow clicks outside the urban area | **Open** — proposal: yes, inside the city boundary | – |
| E6 | Limits for cycling recommendations | **Open** — proposal: switch on if `recommend` stays ≤ 10 min and Valhalla ≤ 2.5 GB | – |
| E7 | Housing potential candidates | Urban boundary + 200 m edge, without forest, water, protected nature, industrial, cemeteries, parks | 9 Nov 2026 |

## 3. Order and timing

| Package | Points | Branch (`rico` = person driving the session) | Folders | Target |
|---|---|---|---|---|
| W1 Map usability | 5, 7, 8, 9, 13 slider, 14, 15, 18 | `feature/rico-map-settings` | web | 16 Nov |
| W2 Isochrone direction | 10 | `feature/rico-isochrone-direction` | api, web | 18 Nov |
| W3 Cell status, click area | 12 fix, 13 | `fix/rico-unscored-cells` | api, web | 18 Nov |
| W4 POI pins and routes | 4, 6, 16 list | `feature/rico-poi-pins` | api, web | 22 Nov |
| — Interim presentation, `v0.1.0` | | | | 25 Nov |
| W5 POI details and parks | 16 info, 17 | `feature/rico-facility-details` | config, pipeline, infra/db, api, web | 4 Dec |
| W6 Cycling recommendations | 11 | `feature/rico-cycling-recommend` | config | 4 Dec |
| W7a Categories from OSM tags | 1, 2, access fix | `feature/rico-categories` | config, pipeline | 11 Dec (gate: school tags ≥ 95 %) |
| W7b Flexible score + combined view | 1, 3 | `feature/rico-flexible-score` | api, web | 18 Dec |
| W8 Housing potential | 12 feature | `feature/rico-housing-potential` | config, pipeline, infra/db, api, web | 10 Jan |
| OSM tagging (people, not agents) | 2 | in OSM, see `docs/osm_tagging.md` | – | from now, before W7a |

W1 and W2 can run in parallel (separate worktrees). W3 before W4 (W4 uses `cell.status`). W5 after
W4. W7a after W5 (both change `facilities.py` and the facilities table) and after the tagging gate. W7b
after W7a. W8 last. Cut order if time runs short: W8, then the click-area part of W3.

## 4. Start prompt (paste before every package)

```text
<role>
You implement one work package of docs/app_iteration_plan.md in the repository
IsochroneLabs/reach on behalf of <NAME> (GitHub <HANDLE>). Base branch: dev.
</role>
<context>
Read completely first: AGENTS.md, the AGENTS.md of every folder you will touch,
docs/app_iteration_plan.md (§1, §2 and your package), docs/architecture.md §6.5 and §9,
docs/methodology.md §1–§5, docs/data_contract.md (API responses), docs/osm_tagging.md for W5/W7a,
docs/notes.md N3, N4, N12, N14, and every file the package names.
The package is the confirmed plan for the folders, files and contract changes it names. Items
marked "Ask first" and anything not named (dependency, existing config value, deviation,
architecture/methodology text) need an explicit yes from your human.
</context>
<rules>
- git fetch --all --prune; branch from origin/dev with the package's branch name.
- Restate the package in five lines and list the files you will touch; start unless the spec
  conflicts with the repo (then stop and ask).
- Small commits, each with green checks. Web: npm run lint && npm run build && npx playwright test.
  Python: uv run ruff check . && uv run ruff format --check . && uv run pytest.
- Every API response change: docs/data_contract.md (version + change log), web/src/types.ts, API
  tests, re-recorded web fixtures (< 1 MB each).
- Verify on the running stack (make up); one screenshot per visible change in the PR.
- Draft PR into dev, body per CONTRIBUTING.md §4, naming on whose behalf you worked and which of
  the 18 points it closes. Update README.md, CHANGELOG.md and the folder AGENTS.md.
- End with: branch, commits, PR link, open points.
</rules>
```

## 5. Work packages

### W1 — Map usability (points 5, 7, 8, 9, 13 slider, 14, 15, 18)

`web/` only; no contract change.

1. **Settings state:** new `web/src/settings.ts` with type `MapSettings` and defaults
   `showCells: true`, `cellOpacity: 0.8`, `showDistricts: true`,
   `isochroneRings: {5: true, 10: true, 15: true}`, `isochroneDirection: 'forward'`,
   `showPois: true`, `showRecommendations: true`, `coloursWithPin: false`, `minResidents: 0`.
   Persisted in `localStorage`, every access in `try/catch` (web/AGENTS.md); hook `useSettings()`.
2. **Settings panel (15):** new `web/src/components/SettingsPanel.tsx`: gear button top right,
   below the `NavigationControl`; popover with groups *Cells* (on/off, opacity 0–100 % = 18,
   minimum residents per cell = 13), *Isochrones* (rings 5/10/15 separately; direction disabled
   until W2), *Layers* (districts, POIs, recommendations), *With a pin* (show cell colours).
   Keyboard operable, `aria-expanded`, Esc closes.
3. **Apply in `MapView.tsx` (8, 18):** visibility via `setLayoutProperty(…, 'visibility')`,
   opacity via `setPaintProperty('cells-fill', 'fill-opacity', …)`, rings via `setFilter` on
   `contour_min` for `isochrone-fill` / `isochrone-line`. Colours stay in `palette.ts`
   (opacity instead of saturation keeps the checked palette valid).
4. **Pin mode (9):** with a pin and `coloursWithPin` off, `cells-fill` opacity goes to 0 (thin
   outline stays), isochrone and route show; a switch "Show cell colours" in the inspector header
   toggles the same setting; closing the pin restores the colours.
5. **Pin in the cell centre (7):** on a successful `/api/inspect` answer set the marker to
   `data.cell.origin` (`App.tsx`); show the click point as a small grey dot for 1.5 s; outline the
   scored cell (feature from `cells` by `cell_id`); inspector note "Measured from the centre of
   this 100 m cell".
6. **Residents slider (13):** `useMemo` in `App.tsx` filters `cells.features` by
   `population >= minResidents`; `Controls.tsx` legend computes shares on the filtered cells and
   says "X of Y cells shown"; tooltip: Zensus perturbs small counts for disclosure control.
7. **Cursor (14):** for each clickable layer (`recommendations`, later `poi-pins`)
   `mouseenter` → `map.getCanvas().style.cursor = 'pointer'`, `mouseleave` → `''` (back to the
   crosshair of `styles.css`).
8. **Left column easier to understand (5, E1):**
    - Order top to bottom: one-sentence intro ("Each square is 100 m. Colour = how many
      facilities residents reach in 15 minutes."), profile and category, legend, then the
      inspector when a pin is set, recommendations, district.
    - Plain-language labels next to the technical ones: "Lack" → "None within 15 min",
      "Insufficient" → "Fewer than needed", "Sufficient" → "Enough"; profile names as
      "Walking (slow, 3.4 km/h)" etc. Labels live in `labels.ts`.
    - Each card gets a one-line "What does this show?" toggle with two or three sentences.
    - Cards are collapsible (`<details>`), state remembered in settings; phone layout unchanged.
    - Empty states say what to do next ("Click any square on the map").
9. **Tests:** extend the Playwright smoke test (open settings, cells off, slider to 10, legend
   changes); screenshots: default, pin mode, settings open.

**Done when:** lint, build and Playwright pass; every switch works without reload and survives a
reload; `web/AGENTS.md` (status, layout incl. `settings.ts`, `SettingsPanel`) and `CHANGELOG.md`
updated.

### W2 — Isochrone direction (point 10)

`api/`, `web/`, data contract, `architecture.md` §9 endpoint list (named here, version + change log).

1. **API:** `POST /api/isochrone` in `api/src/reach_api/routes/live.py`, body
   `{lon, lat, profile, direction: "forward" | "reverse"}`; uses `_locate` and
   `_isochrone(d, origin, p, reverse=…)`; cache key `(run_id, "isochrone", cell_id, profile_id,
   direction)` in `live_cache`; rate-limited like the other live endpoints. Answer: `run_id`,
   `profile_id`, `cell`, `direction`, `isochrone`, `cached`. `/api/inspect` stays forward.
2. **Tests:** `api/tests/test_live.py` with a recorded reverse Valhalla answer; cache hit and 422
   outside.
3. **Web:** settings choice *Forward / Reverse / Both*; reverse requested only when chosen; source
   `isochrone-reverse` with its own colour in `palette.ts` and a dotted line (forward stays dashed),
   so the two differ without colour. Inspector legend: "Forward: where you get in 5/10/15 min ·
   Reverse: from where people reach this point".
4. **Docs:** data contract, architecture §9, `features.md` §4.

**Done when:** endpoint tests pass; at the Schloss (slope) both isochrones differ visibly
(screenshot).

### W3 — Cell status and click area (points 12 fix, 13)

`api/`, `web/`, docs. **Ask first:** architecture §6.5 rule 12 (E5).

1. **Finding:** "No residents in this 100 m cell" is shown for every cell without a row in
   `current.cells`: (a) no residents in the Zensus grid, or (b) populated but centre outside the
   city boundary (88 residents in run `20261106T142630Z`).
2. **API:** `db.locate` adds `in_city` = cell centre inside the union of `current.districts`
   (they cover the city up to `districts.coverage_tolerance_pct`). `cell.status` in every live
   answer: `"scored"`, `"unpopulated"` (inside the city, not in the Zensus grid) or
   `"outside_city"`.
3. **Click area (E5, after the yes):** `allowed` = scored cell or `in_city`; the urban boundary
   plus margin is no longer the click limit. `api.boundary_margin_m` stays in the config but is no
   longer read → update its comment; removing it is a separate ask (note in `notes.md`).
4. **Web:** inspector text per status: "N residents in this 100 m cell" / "No residents in the
   Zensus 2022 grid — values computed live" / "Outside the city boundary — not scored".
5. **Docs:** architecture §6.5 rule 12, data contract (`cell.status`), glossary, notes N3 addendum.

**Done when:** tests cover all three statuses (Marktplatz, a field near Hagelloch, an edge cell in
Unterjesingen); 422 only outside the city.

### W4 — POI pins and routes (points 4, 6, 16 list)

`api/`, `web/`, data contract, two new config keys under `api`. **Ask first:** architecture §6.5
(live matrix beyond the budget).

1. **`reachable` with coordinates:** `_by_category` in `live.py` exposes the internal `_point` as
   `point: [lon, lat]` (6 decimals); for parks this is the access point the time was measured to.
2. **Next missing facility:** per category with `count < k` a field `next_facility` = the fastest
   facility of that category **not** in `reachable` (the one that would raise the count by one).
   New query `nearest_facility_points(x, y, category, exclude_ids, limit)` (straight line, `<->`
   index) → one live matrix 1 × N via `live_matrix` for all such categories together → fastest
   point per category → `/route` to it. Fields: `facility_id`, `name`, `time_s`, `time_min`,
   `point`, `within_budget` (bool), `route` (Feature LineString). New config keys:
   `api.next_facility.candidates: 8`, `api.next_facility.max_time_min: 60` (beyond: `null` and a
   note).
3. **Route to one facility:** `POST /api/route` `{lon, lat, profile, facility_id}` → route from the
   cell origin to the facility's routing point, cached like inspect (for point 16).
4. **Web by class of the selected category (6):**
    - `sufficient`: no route; all `reachable` as small pins (circle 5 px, white with a dark ring,
      colours in `palette.ts`), time label from zoom 15.
    - `insufficient`: pins + route to `next_facility`.
    - `lack`: route to `next_facility`; beyond the budget dashed with the label
      "23 min · beyond 15 min"; its pin highlighted.
    - Hover on a pin → MapLibre popup with name, category, time (W5 adds details).
5. **List (16):** entries in `Inspector.tsx` become buttons: click → `flyTo`, pin highlighted,
   route via `/api/route` to exactly this facility; second click clears; hover in the list
   highlights the pin and vice versa.
6. **Tests:** API tests for `point`, `next_facility` (within, beyond, none within 60 min) and
   `/api/route`; re-record `web/tests/fixtures/inspect_walking_339.json`.
7. **Docs:** data contract, architecture §6.5 rules 8/11 and §9, `config.yaml` comments,
   `features.md` §4.

**Done when:** a green cell shows only pins, orange pins + route, red a marked route beyond
15 min; inspect for scored cells stays under 1 s (measured, in the PR).

### W5 — POI details and parks (points 16 info, 17)

`config/`, `pipeline/`, `infra/db/run_schema.sql`, `api/`, `web/`, data contract.

1. **Config:** new key `facility_tags` = list of informative OSM keys (`docs/osm_tagging.md` §5).
2. **Pipeline:** `facilities.match_categories` keeps the listed tags as JSON column `tags`; areas
   also keep `area_geometry` (MultiPolygon, 25832, simplified with 2 m). `validate` writes both to
   `facilities.parquet`; `publish` loads them.
3. **DB:** `run_schema.sql` → `facilities` gets, **at the end**, `tags jsonb NOT NULL DEFAULT '{}'`
   and `area_geom geometry(MultiPolygon, 25832)` (end: `current` views use
   `CREATE OR REPLACE VIEW`, which can only append columns; implementation_plan §8 item 5).
   Data-contract test.
4. **API:** `GET /api/facilities?category=` (read endpoint, ETag like `/api/cells`): points with
   `facility_id`, `name`, `category`, `tags`, `osm_url` (from the `n`/`w`/`r` prefix); with
   `&geometry=area` areas plus access points (`facility_points.kind = 'access'`). Inspect and
   `/api/route` include `tags` per facility.
5. **Web:** popup and list show opening hours (raw text), wheelchair symbol, address, doctors'
   speciality, links "View on OpenStreetMap" and "Open in Google Maps"
   (`https://www.google.com/maps/search/?api=1&query=<name>+<lat>,<lon>`, a link only, no API).
   New layer "All facilities" (settings) from `/api/facilities` for the selected category.
6. **Parks (17):** for parks the map shows the park areas (outline, light fill) and their access
   points (small dots); routes end at the access point; popup text: "Measured to the nearest park
   entrance (where a path meets the boundary). A park counts once." Same sentence on the data page.
7. **Docs:** data contract, methodology §2 one sentence on display (**ask first**, no content
   change), README data sources, glossary.

**Done when:** `make refresh REACH_CONFIG=config/test_clip.yaml` passes; DB contract test passes;
park area, access points and route visible together in one screenshot.

### W6 — Cycling recommendations (point 11)

`config/`, docs. **Ask first:** existing value `recommend.profiles`; limits E6.

1. **Measure:** temporarily add `cycling_15` to `recommend.profiles`, run
   `make pipeline STAGE=recommend`; record `runtime_s`, `peak_rss_mb`, `pairs`, `recommendations`
   from `report_recommend.json` and the Valhalla peak (`docker stats`). Reference without cycling
   (6 Nov): 87.6 s, 1,211 MB pipeline peak; `count` takes 325 s for cycling vs. ~19 s for walking.
2. **Decide (E6):** within limits → switch on. Otherwise try a cycling-specific candidate spacing
   (new key `recommend.profile_overrides.cycling_15.candidate_spacing_m: 200`, change in
   `recommend.py` + test). Still too heavy → leave off and record the numbers in notes N12.
3. **Web:** no change; the panel appears once `/api/recommendations` has cycling features. Check
   the panel text for cycling.
4. **Docs:** `config.yaml` comment, notes N12, `validation_report.md`, `CHANGELOG.md`.

**Done when:** numbers in the PR; `validate_results` (`recommendations_consistent`) passes with
cycling.

### W7a — Categories from OSM tags (points 1, 2; access fix)

`config/`, `pipeline/`, docs. **Ask first:** methodology §2 (new categories, `k`, access rule),
existing config values (`categories`). **Gate:** ≥ 95 % of the schools in the city carry a type
tag (`docs/osm_tagging.md` §6); until then only the parks/playgrounds split and the access rule.

1. **Config schema:** each category gets `group` (`food`, `health`, `education`, `green`) and
   optional `require` (list of alternative tag conditions) and `exclude` (list of conditions that
   drop a feature); a condition is `{key: value}`, `;`-separated OSM values match if any part
   matches. Loader validation and tests in `pipeline/tests/test_config.py`.
2. **Categories:** `parks` → `parks` (`leisure=park`) and `playgrounds` (`leisure=playground`),
   both `k: 1`, `location: access_points`, both with `exclude` `access` in
   `[private, no, customers]`. `school` → `primary_school` (`require` `school=primary` or
   `school:de=Grundschule` or `isced:level` contains `1`) and `secondary_school` (`school=secondary`
   or `school:de` in `[Gymnasium, Realschule, Gemeinschaftsschule, Werkrealschule, Hauptschule]`
   or `isced:level` contains `2`/`3`), both `k: 1`. Values exactly as in `docs/osm_tagging.md` §3.
3. **Pipeline:** `match_categories` applies `require`/`exclude` vectorised (no loops over
   features); the OSM export keeps the needed keys. `validate` adds checks
   `facility_subtypes_complete` (warns with the number of `amenity=school` features in the city
   matching no school category) and `facilities_excluded_by_access` (count per category and value,
   informative). `count`, `score`, `recommend` need no change (one matrix for all categories).
4. **Docs:** methodology §2 table and access rule (version + change log), `osm_tagging.md` §7 made
   binding-consistent, `validation_report.md` V2 note, README, CHANGELOG, notes N14 closed.

**Done when:** test-clip run passes; `validate_results` passes; the report lists excluded private
playgrounds; shares per class before/after the access fix in the PR.

### W7b — Flexible accessibility score and combined view (points 1, 3; E2)

`api/`, `web/`, data contract. **Ask first:** methodology new §4b (score definition) and the
`web/AGENTS.md` rule "Read the API, do not re-derive" (the score is a defined client-side display
computation).

**Score definition (proposed methodology §4b).** For cell *i*, profile *m*, selected categories
*S*, user parameters per category: time threshold *t_c* ≤ facility budget (minutes), required
count *k_c* ≥ 1, weight *w_c* ≥ 0:

```text
A_ic(t_c)  = number of facilities of c reachable from i within t_c (from `reachable`)
coverage_ic = min(1, A_ic(t_c) / k_c)
score_i    = 100 · Σ_{c∈S} w_c · coverage_ic / Σ_{c∈S} w_c
```

- Defaults: `t_c` = 15 min (the budget), `k_c` from the config, `w_c` = 1. With the defaults
  `score_i = 100 · (1 − Σ_c U_ic / (P_i · |S|))` — the same saturating coverage as the deficit
  (methodology §4), so map, deficit and recommender stay consistent.
- For one category the default score is 0 (lack), 100 (sufficient) or in between (insufficient),
  i.e. the class map is a special case.
- `t_c` cannot exceed the budget: `reachable` only stores times within it. The slider stops at the
  budget and says why.
- Optional transit term (off by default): class mapped to 0 / ⅓ / ⅔ / 1 for
  lack / insufficient / medium / high, with its own weight.

1. **API:** read endpoint `GET /api/cells/times?profile=` (ETag per run, read cache): per scored
   cell `cell_id`, `population`, `district_id` and per category the sorted times (seconds) of the
   nearest facilities up to `api.score.max_times_per_category` (new key, default 5 ≥ max `k` + 2);
   cell polygons come from `/api/cells` (already cached). Expected size ~1,700 cells × 8
   categories × ≤ 5 values. `/api/meta` adds `group` per category.
2. **Web:** new `web/src/score.ts` (pure functions, unit-tested with Vitest only if it is already
   a dependency, otherwise via the Playwright test — no new dependency without asking);
   category selector becomes a grouped checkbox list with "All"; panel "Score settings" (global
   time threshold slider 5–15 min with per-category override, `k` and weight per category,
   "Reset to defaults"). Map colour: sequential scale 0–100 in five classes
   (0–19, 20–39, 40–59, 60–79, 80–100) plus "100 = all fulfilled" outline; new ramp in
   `palette.ts`, monotonic L*, CVD check with min. ΔE stated (web/AGENTS.md). Legend: residents
   per class and "X % of residents reach all selected categories". District panel: population-
   weighted mean score. One category + defaults → today's class view unchanged. Recommendations
   only with exactly one category. URL hash keeps `category=a,b,c` and non-default parameters, so
   a demo link reproduces the view.
3. **Consistency test:** for the fixture cells the default score equals
   `100 · (1 − deficit / population)` from `/api/cells` (per category) — in the Playwright test.
4. **Docs:** methodology §4b (version + change log), data contract, `web/AGENTS.md` rule wording,
   `features.md` §1, README.

**Done when:** sliders update the map without a request (< 100 ms on 1,700 cells); default view
identical to the class map for one category; screenshot with three categories and a custom
threshold.

### W8 — Housing potential (point 12 feature, E7)

`config/`, `pipeline/`, `infra/db/run_schema.sql`, `api/`, `web/`, docs. **Ask first:**
methodology §5b, architecture (new stage, §8 tables).

1. **Question:** where would new homes already have good 15-minute access? The counterpart of the
   recommender (there: facility to people; here: people to facilities), a typical
   *Innenentwicklung* question.
2. **Candidates:** unpopulated 100 m Zensus cells (not in `cells`) with centre inside the urban
   boundary + `housing.edge_buffer_m` (200), without the land use of `recommend.exclude_tags` plus
   `landuse=industrial`, `landuse=cemetery`, `leisure=park`. Reference: 1,655 grid cells in the
   urban boundary, 1,566 after the recommender's land-use filter (6 Nov); the unpopulated share is
   reported.
3. **New stage `housing`** between `score` and `recommend`: matrix candidates → facilities with
   the block procedure of `count` (architecture §6.5); profiles from `housing.profiles` (default
   walking 3.39 and 5.0). Outputs `housing/housing_cells.parquet`, `housing/housing_counts.parquet`
   (columns as `access_counts`), manifest, `report_housing.json` with runtime and memory.
4. **DB:** tables `housing_cells`, `housing_counts`; view `housing_scores` (class per category as
   `scores`, plus the default score of W7b). `validate_results`: no housing cell is in `cells`.
5. **API:** `GET /api/housing?profile=` → polygons with the per-category counts and times needed
   for the W7b score, `district_id`.
6. **Web:** layer "Housing potential" in settings, coloured with the same score as W7b (same
   parameters), list "Top 10 cells for new homes" with limits (ownership, zoning, noise, flood risk
   not considered); click → inspect (W3 shows "No residents in the Zensus 2022 grid").
7. **Docs:** methodology §5b, architecture stages and §8, data contract, `features.md`, README,
   `validation_report.md` (plausibility on three areas built after the 2022 census).

**Done when:** test-clip run passes; stage runtime in the PR (target < 2 min); three plausibility
cells in the validation report.

## Change log

| Version | Date | Change |
|---|---|---|
| v0.1 | 2026-11-09 | First plan from Rico's 18 points; decisions E1–E4, E7; private-playground finding |
