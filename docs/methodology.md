# Methodology — reach

> **Status:** v1.0-draft (21 Nov 2026). Binding definition of **what** is computed: origins,
> destinations, modes, trip windows, travel times, the fit, explanations and validation.
> [`architecture.md`](architecture.md) describes **how**. Every change bumps the version and adds
> a line to the [Change log](#change-log). **[OPEN]** items are decided before the related code;
> open questions are M-numbers (Section 11).

## 1. Question

For a student with a given profile: **from which parts of Tübingen are their own everyday trips
short and easy**, by the modes they use, at the times they travel, and why? The answer is
personal (it depends on the profile) and explained (every result carries the facts that drive
it). There is no fixed time threshold.

## 2. Origins and areas

- **Origin cells** *i*: populated Zensus 2022 100 m cells inside the city boundary, plus cells
  with an OSM residential address but no residents (A1). Origin point = cell centroid.
- **Ranking** uses populated cells only; address cells are answered in U2.
- **Areas** *a*: core-town districts (OSM admin level 11) and Teilorte (level 9). An area's fit
  summarises the fit of its populated cells (M3).

## 3. Destinations

A destination *j* belongs to one destination type *d*. Types, their sources and draft defaults
(defaults are prefilled in the onboarding and can be changed by the student; values marked
[VERIFY] are checked with students in S2.0):

| Type | Source | Nearest k stored | Default fine time | Default trips/week | Trip window |
|---|---|---|---|---|---|
| `campus_site` | `config/campus.yaml` | all sites | 20 min [VERIFY] | 5 | weekday morning arrival |
| `mensa` | OSM + list in `config/campus.yaml` | 3 | 15 min [VERIFY] | 3 | weekday midday |
| `library` | OSM `amenity=library` (university and public) | 3 | 20 min | 2 | weekday midday |
| `university_sports` | `config/campus.yaml` | all sites | 20 min | 1 | weekday evening |
| `grocery` | OSM `shop=supermarket` | 3 | 10 min | 2 | weekday evening |
| `pharmacy`, `doctor` | OSM `amenity=pharmacy`, `amenity=doctors` (GP where tagged) | 3 | 15 min | 0.1 | weekday midday |
| `main_station` | GTFS/OSM Tübingen Hbf | 1 | 25 min | 0.5 | Saturday to the station |
| `park` | OSM `leisure=park`, public only, access points | 3 | 10 min | 1 | weekday evening |
| hobby types (`gym`, `climbing`, `swimming`, `sports_club`, `music`, `nightlife`, `cinema_theatre`, `place_of_worship`) | OSM tags in `config/config.yaml`, `docs/osm_tagging.md` | 3 | 20 min | per hobby | evening; `nightlife`: night return |

Only facilities the public can use count (OSM `access` rule, `docs/osm_tagging.md`). Polygons are
represented by one point inside; parks by their access points (a park counts once, with the
minimum time). Every hobby type the onboarding offers must have at least one destination in the
routing area (V3).

## 4. Modes and travel time

Travel time *T(i, j, m, w)* from cell *i* to destination *j* by mode *m* in trip window *w*, door
to door, in minutes:

- **walk:** Valhalla `pedestrian`, 5.0 km/h on flat ground; Valhalla's grade factor slows uphill
  and steep downhill (archive: median 1.08 × flat time, up to 1.66 × on steep routes).
- **bike:** Valhalla `bicycle`, Hybrid, 15 km/h; uphill slower, downhill faster.
- **transit:** walk from the origin to a stop + wait for the departure + in-vehicle time +
  transfers (walk and wait) + walk to the destination, for a departure that fits the trip window
  (T1 decides the engine; the exact handling of the window, e.g. best departure vs. a percentile
  over the window, is fixed with T1). Transit is never faster than walking the whole way: if walk
  is shorter, the transit time equals the walk time and the reason says so.
- **bike_transit** (optional, first cut): bike to a stop, park, ride, walk to the destination; no
  bike on board. Shown only for areas where it beats bike-only and transit-only (V2).

Times are stored raw (seconds), also beyond any "fine" time.

**Reliability (schedule-based).** For transit trips: departures per hour at the first stop in the
trip window, the spread of travel times across the window, and for night windows the last
departure that gets the student home. No delay data is used; the app says so.

## 5. Trip windows

A trip window *w* = weekday, reference date, time, direction (to the destination: depart at or
arrive by; return: depart from the destination after). Draft windows (in `config/config.yaml`):

| Window | Weekday | Time | Direction | Used for |
|---|---|---|---|---|
| `morning_lecture` | Tuesday | arrive by 08:10 | to destination | campus sites |
| `midday` | Tuesday | depart 12:00 | to destination | Mensa, library, health |
| `evening` | Tuesday | depart 18:00 | to destination | sport, hobbies, grocery |
| `night_return` | Friday night (Sat 00:30) | depart 00:30 | from destination home | nightlife and evening hobbies home |
| `weekend_station` | Saturday | depart 10:00 | to destination | main station (trips home) |

The reference date of a window is the first matching weekday on or after the run date inside the
GTFS validity that is no public or school holiday in Baden-Württemberg and has active services;
service-day times beyond 24:00 belong to the previous day. If the feed does not cover a window,
the run fails (V3).

## 6. Fit **[OPEN]**

Proposal for discussion in S1.3; nothing is implemented before it is confirmed.

For a student profile with allowed modes *M*, destination types *D* (from programme and hobbies),
importance *w_d* ∈ {0, 1, 2, 3}, fine time *t_d* (minutes) and trips per week *f_d*:

1. **Best time per type:** *T_d(i)* = minimum over the allowed modes of the travel time to the
   nearest destination of type *d* in the type's trip window. For `campus_site`: the mean over the
   sites of the programme (or the site the student picks).
2. **Smooth decay around the fine time** (no cut-off):

   *s_d(i) = 1 / (1 + (T_d(i) / (1.25 · t_d))^4)*

   With *t_d* = 15 min: 10 min → 0.93, 15 min → 0.71, 20 min → 0.44, 30 min → 0.13.
   Alternatives for S1.3: exponential decay beyond *t_d*; logistic in minutes.
3. **Fit:** *fit(i) = 100 · Σ_d w_d · s_d(i) / Σ_d w_d* (0–100).
4. **Weekly travel time:** *W(i) = Σ_d f_d · (T_d,to(i) + T_d,back(i))* in minutes per week; the
   back trip uses the return window where one is defined, otherwise the same window. Shown next
   to the fit as the intuitive measure ("about 3 h 40 min per week on the way").

Worked examples with personas follow in S1.3. Sensitivity of the ranking to ±25 % of *t_d*, the
exponent and the weights is V4.

## 7. Explanations

Every result (cell, area, place) carries 2–4 reasons, chosen from the numbers that drive it:
the types with the largest weighted contribution *w_d · s_d* (strengths) and the largest
weighted loss *w_d · (1 − s_d)* (weaknesses), each as "destination, time, mode, window" (e.g.
"Morgenstelle 12 min by bus at 8:00"), plus transit reliability where it matters ("last bus home
00:47"). Reasons are generated from the same values as the fit, so they cannot contradict it (V4
checks this).

## 8. Rent (optional, second cut)

Zensus 2022 average net cold rent per m² on the 100 m grid (rented flats in residential
buildings, without student halls; 15 May 2022). Cells without a published value stay empty;
values the census marks as uncertain are shown in brackets; an area value is the mean of its
published cells, with their number. The app always shows "census 2022, no current offers". The
budget answer filters or labels areas; it never enters the fit unless decided otherwise (M4).

## 9. Relation to classic accessibility measures

Cumulative-opportunity measures count destinations within a fixed time (e.g. the "15-minute
city", Moreno et al. 2021; the archived version of this project). They are easy to read but treat
14 and 16 minutes as different worlds and assume one budget for everybody. Gravity-type measures
weight destinations by a smooth decay of travel time (Hansen 1959), and person-based measures
evaluate accessibility for an individual's own activities and times (Kwan 1998; overview in Geurs
& van Wee 2004). The fit is a person-based, time-decayed measure: the student sets the
destinations, importance and fine times, and the decay replaces the threshold. We chose it
because the user's question is personal ("my campus, my sport, my night bus") and because a
threshold would make small time differences look decisive. This section is background only.

## 10. Validation

Validation is graded. Results per release in `docs/validation.md` (*planned, S1.11*).

| # | Check or experiment | Method | Limits |
|---|---|---|---|
| V1 | Travel times vs. external reference | ≥ 25 cell × destination pairs per mode: transit from the naldo/DB journey planner at the same trip window, walk/bike from a routing website or measured trips; stored as fixtures, never queried by tests or the pipeline; median and 90th-percentile deviation | reported per release |
| V2 | Plausibility (every run, `validate_results`) | transit ≥ walk to the first stop + wait; transit never faster than the straight line at bus speed; night never better than morning where service is thinner; bike ≤ walk for > 95 % of pairs; bike + transit shown only where it wins | warn/fail limits in config |
| V3 | Completeness (every run) | every campus site found and routable; every offered hobby type has ≥ 1 destination; GTFS covers every trip window; coverage of residents by origin cells | fail |
| V4 | Sensitivity and consistency | rankings under fit parameters ±25 % and other trip windows (Spearman rank correlation of areas); reasons match the numbers | reported |
| V5 | Matrix vs. single route | sample of walk and bike pairs, matrix vs. `/route` (archive V10: median deviation 0.5 s) | warn |
| V6 | Users | round 1: interviews on the onboarding questions (S2.0); round 2: app test with 5 students and a task script (S2.8) | reported |
| V7 | Deployment | smoke-test results per release (frontend, health, fit with a persona, cell detail) | fail = rollback |
| V8 | Reproducibility | a teammate runs the pipeline from the README only | reported |

## 11. Open methodology questions

| ID | Question | Proposal |
|---|---|---|
| M1 | Fit formula (decay shape, parameters, weights) | §6 proposal; decide in S1.3 with persona examples. Calibrate so that *s(t_d)* ≈ 0.9 (a trip of exactly the fine time should feel good; the §6 draft gives 0.71) |
| M7 | Several campus sites per programme | weight the sites by days per week the student spends there instead of the plain mean (§6 step 1); decide in S1.3 |
| M2 | Default fine times, trips per week and trip window per destination type | §3 drafts; check in user-test round 1 (S2.0) |
| M3 | Area value from cell fits | median fit of the populated cells plus the best cell, with the share of cells above the city median |
| M4 | Rent in the fit or as a filter | filter/label only |
| M5 | Bike + transit | decide with T1; first cut if time runs short |
| M6 | Transit time inside a window | best departure vs. a percentile over the window; decide with T1 |

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v1.0-draft | 2026-11-21 | New methodology for the student rebuild: origins and areas, destination types, modes, trip windows, fit proposal [OPEN], weekly travel time, explanations, rent, relation to classic measures, validation V1–V8 | Rebuild brief of 21 Nov 2026; plan S0.2 |

## References

- Geurs, K. T., & van Wee, B. (2004). Accessibility evaluation of land-use and transport
  strategies: review and research directions. *Journal of Transport Geography*, 12(2), 127–140.
- Hansen, W. G. (1959). How accessibility shapes land use. *Journal of the American Institute of
  Planners*, 25(2), 73–76.
- Kwan, M.-P. (1998). Space-time and integral measures of individual accessibility: a comparative
  analysis using a point-based framework. *Geographical Analysis*, 30(3), 191–216.
- Moreno, C., Allam, Z., Chabaud, D., Gall, C., & Pratlong, F. (2021). Introducing the
  "15-Minute City". *Smart Cities*, 4(1), 93–111.
