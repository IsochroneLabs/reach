# Methodology — reach

> **Status:** v1.3-draft (26 Nov 2026). Binding definition of **what** is computed: origins,
> destinations, modes, trip windows, travel times, the fit, explanations and validation.
> [`architecture.md`](architecture.md) describes **how**. Every change bumps the version and adds
> a line to the [Change log](#change-log). **[OPEN]** items are decided before the related code;
> open questions are M-numbers (Section 11).

## 1. Question

For a student with a given profile: **from which parts of Tübingen are their own everyday trips
short and easy**, by the modes they use, at the times they travel, and why? The answer is
personal (it depends on the profile) and explained (every result carries the facts that drive
it). There is no fixed time threshold. The same question is answered for a single place or a
current listing: **how do my own trips look from this flat?**

## 2. Origins and areas

- **Origin cells** *i*: populated Zensus 2022 100 m cells inside the city boundary, plus cells
  with an OSM residential address but no residents (A1). Origin point = cell centroid.
- **Ranking** uses populated cells only; address cells are answered in *Check*.
- **Listing points** *l*: geocoded listing addresses (§8.1). They are routed as points of their
  own (architecture §6.5), never ranked and never mixed into a cell's value.
- **Areas** *a*: core-town districts (OSM admin level 11) and Teilorte (level 9). An area's fit
  summarises the fit of its populated cells (M3).

## 3. Destinations

A destination *j* belongs to one destination type *d*. Types, their sources and draft defaults
(defaults are prefilled in the profile panel and can be changed by the student; values marked
[VERIFY] are checked with students in S2.0):

| Type | Source | Nearest k stored | Default fine time | Default trips/week | Trip window |
|---|---|---|---|---|---|
| `campus_site` | Alma programme sites (§3.2), overrides and fallback in `config/campus.yaml` | all sites used by a programme | 20 min [VERIFY] | 5 | weekday morning arrival |
| `mensa` | OSM + list in `config/campus.yaml` | 3 | 15 min [VERIFY] | 3 | weekday midday |
| `library` | OSM `amenity=library` (university and public) | 3 | 20 min | 2 | weekday midday |
| `university_sports` | `config/campus.yaml` | all sites | 20 min | 1 | weekday evening |
| `grocery` | OSM `shop=supermarket`; label = brand (§3.1) | 3, plus 2 per brand | 10 min | 2 | weekday evening |
| `pharmacy`, `doctor` | OSM `amenity=pharmacy`, `amenity=doctors` (GP where tagged) | 3 | 15 min | 0.1 | weekday midday |
| `main_station` | GTFS/OSM Tübingen Hbf | 1 | 25 min | 0.5 | Saturday to the station |
| `park` | OSM `leisure=park`, public only, access points | 3 | 10 min | 1 | weekday evening |
| `sport` | OSM sport places; label = sport category (§3.1), replaces `gym`, `climbing`, `swimming`, `sports_club` | 2 per category | 20 min | – (no trips per week, §6) | weekday evening |
| `hobby` | OSM hobby places; label = hobby category (§3.1), replaces `music` | 2 per category | 20 min | – (no trips per week, §6) | weekday evening |
| `nightlife`, `cinema_theatre` | OSM tags in `config/config.yaml`, `docs/osm_tagging.md` | 3 | 20 min | per type | `nightlife`: night return; otherwise evening |
| `place_of_worship` | OSM `amenity=place_of_worship`; label = religion | 3, plus 2 per religion | 20 min | 1 | Saturday to the station window |

Only facilities the public can use count (OSM `access` rule, `docs/osm_tagging.md`). Polygons are
represented by one point inside; parks by their access points (a park counts once, with the
minimum time). Every destination type and every label the profile panel offers must have at least
one destination in the routing area (V3, V10).

### 3.1 Destination labels

A **destination label** groups destinations inside one type by what the student chooses between
(architecture O22). Labels come from OSM tags through the mapping in `docs/osm_tagging.md` and
`config/config.yaml`; a destination can carry several labels (a sports centre with climbing and
fitness).

| Type | Label | Source | Use in the fit (§6) |
|---|---|---|---|
| `grocery` | **brand** (EDEKA, ALDI SÜD, PENNY, Lidl, REWE, Netto, Kaufland, Norma, Alnatura, denn's; brands with fewer than 2 stores are not offered on their own) **and group** (organic, package-free, international, discounter, full-range, village and farm shop, other) | brand: `brand:wikidata`, then `brand`/`name`; group: tags (`organic=only`, `zero_waste=only`), brand, name patterns, first match wins | **favourite supermarkets:** the grocery term uses only the brands and groups the student chose (union); none chosen → all supermarkets |
| `sport` | category: 25 categories from football to motor and model sports (`config/config.yaml`, `docs/osm_tagging.md` §5.2) | `sport=*` on sport `leisure` values and `club=sport`; the `leisure` value decides only if no sport value maps | **every chosen category is its own term** |
| `hobby` | category: music, arts and culture centres, makerspace, chess | tags in `docs/osm_tagging.md` §5.3 | every chosen category is its own term |
| `place_of_worship` | religion | `religion=*` | the term uses the chosen religion |

**One place, one destination.** Features of the same label closer than `cluster_radius_m` (75 m)
or inside the same `leisure=sports_centre` form one destination, represented by a point inside the
largest feature (a tennis club with ten courts, or a shop mapped as node and building, counts once).
Clustering is per label, so a sports centre with climbing and fitness is one destination in each
category.

**Offered labels.** Every label with at least `min_destinations` (1) destination after clustering
is offered in the profile panel, without a remark on how many there are. Counts of 26 Nov 2026
and known gaps: `docs/osm_tagging.md` §5, notes N23.

### 3.2 Programmes and campus sites (Alma)

The programme a student studies decides where they have lectures (architecture O23):

1. **Input:** the public Alma course catalogue of the current semester, read once per semester.
   For each programme *p* (name and degree: bachelor, master, state examination, …) the
   **compulsory** modules with their recommended semester *σ*, their courses and the course sessions
   (weekday, start, end, room, building).
2. **Buildings → sites:** each building is matched to an OSM address or building of the clipped
   extract; buildings are assigned to the campus sites of `config/campus.yaml`, and buildings far
   from every site form new sites (distance from config).
3. **Weekly hours per site:** *h(p, σ, s)* = weekly hours of compulsory sessions of programme *p*
   in semester *σ* held at site *s*; the **site share** *π(p, σ, s) = h(p, σ, s) / Σ_s' h(p, σ, s')*.
4. **Profile:** the student picks the degree (bachelor or master), the programme and the semester
   (default: 1; master's students count from their master's semester 1). Without a programme the
   default campus mix of `config/campus.yaml` applies.
5. **Overrides and fallback:** entries in `config/campus.yaml` win over Alma; if Alma is not
   available for a programme, the programme → site table of `config/campus.yaml` is used with equal
   shares, and the app says so.

Elective modules are not counted (their sites are unknown before the student chooses them).

## 4. Modes and travel time

Travel time *T(i, j, m, w)* from cell *i* to destination *j* by mode *m* in trip window *w*, door
to door, in minutes:

- **walk:** Valhalla `pedestrian`, 5.0 km/h on flat ground; Valhalla's grade factor slows uphill
  and steep downhill (archive: median 1.08 × flat time, up to 1.66 × on steep routes).
- **bike:** Valhalla `bicycle`, Hybrid, 15 km/h; uphill slower, downhill faster.
- **transit:** walk from the origin to a stop + wait for the departure + in-vehicle time +
  transfers (walk and wait) + walk to the destination, computed with OpenTripPlanner
  (architecture O17). **The time includes the wait at home (M6, decided 23 Nov 2026):**
  - *depart-at windows* (e.g. evening, Saturday): *T* = earliest arrival at the destination when
    the student is ready to leave at the window time − window time. A bus that leaves 20 minutes
    later costs those 20 minutes; infrequent service shows up in the time itself.
  - *arrive-by windows* (e.g. the morning lecture): *T* = required arrival time − latest
    departure from home that still arrives on time.
  The legs (access walk, wait, in-vehicle, transfers, egress, first stop and route, departure) are
  stored next to *T* for the reasons. Transit is never faster than walking the whole way: if walk
  is shorter, the transit time equals the walk time and the reason says so.
- **bike_transit** (optional, first cut): bike to a stop, park at OSM bike parking, ride, walk to
  the destination; no bike on board (OTP `BICYCLE_PARKING`, M5). Same window rule as transit.
  Shown only for areas where it beats bike-only and transit-only (V2).

Times are stored raw (seconds), also beyond any "fine" time. The targets per origin are the
nearest k destinations per type and the nearest *k_label* per label (§3, §3.1), plus every campus
site used by a programme. Listing points use the same targets and the same definitions.

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
   nearest destination of type *d* in the type's trip window. Which destinations count follows
   the profile (decided 26 Nov 2026):
   - **`campus_site`:** the weighted mean over the sites of the student's programme and
     semester, *T_campus(i) = Σ_s π(p, σ, s) · T_s(i)* with the site shares of §3.2 (closes M7).
   - **`grocery` with favourite supermarkets:** the nearest supermarket among the chosen brands
     only (minimum over their destinations); no brand chosen → every supermarket.
   - **`sport` and `hobby`:** every chosen category *c* is its own term *d = (type, c)* with its own
     importance and fine time; *T_d(i)* is the time to the nearest destination of that category.
     These terms use **only the time to the amenity**: they have no trips per week and do not
     enter the weekly travel time (step 4).
   - **`place_of_worship`:** the nearest destination of the chosen religion.
2. **Smooth decay around the fine time** (no cut-off):

   *s_d(i) = 1 / (1 + (T_d(i) / (1.25 · t_d))^4)*

   With *t_d* = 15 min: 10 min → 0.93, 15 min → 0.71, 20 min → 0.44, 30 min → 0.13.
   Alternatives for S1.3: exponential decay beyond *t_d*; logistic in minutes.
3. **Fit:** *fit(i) = 100 · Σ_d w_d · s_d(i) / Σ_d w_d* (0–100).
4. **Weekly travel time:** *W(i) = Σ_d f_d · (T_d,to(i) + T_d,back(i))* in minutes per week over
   the types that have trips per week (campus, Mensa, grocery, …; **not** the sport and hobby
   categories); the back trip uses the return window where one is defined, otherwise the same
   window. Shown next to the fit as the intuitive measure ("about 3 h 40 min per week on the
   way"), labelled as excluding sport and hobbies.

Worked examples with personas follow in S1.3. Sensitivity of the ranking to ±25 % of *t_d*, the
exponent and the weights is V4.

## 7. Explanations

Every result (cell, area, place) carries 2–4 reasons, chosen from the numbers that drive it:
the types with the largest weighted contribution *w_d · s_d* (strengths) and the largest
weighted loss *w_d · (1 − s_d)* (weaknesses), each as "destination, time, mode, window" (e.g.
"Morgenstelle 12 min by bus at 8:00"), plus transit reliability where it matters ("last bus home
00:47"). Labelled destinations are named with their label and place ("REWE Mühlstraße 6 min on
foot", "Tennis: 9 min by bike"); the campus reason names the site with the largest share. Reasons are generated from the same values as the fit, so they cannot contradict it (V4
checks this).

## 8. Rent (optional, second cut)

Zensus 2022 average net cold rent per m² on the 100 m grid (rented flats in residential
buildings, without student halls; 15 May 2022). Cells without a published value stay empty;
values the census marks as uncertain are shown in brackets; an area value is the mean of its
published cells, with their number. The app always shows "census 2022, no current offers". The
budget answer filters or labels areas; it never enters the fit unless decided otherwise (M4).

## 8.1 Listings

Listings come from the daily listings job (architecture O24). For each listing *l* the app shows
its parameters as published (rent warm and cold, utilities, deposit, size, rooms, flatmates as
counts and age range, available from/until, furnishing, features, district), its photos (linked
from the source, loaded only when the student opens the listing), a link to the original ad, the
travel times to the student's own destinations per mode and trip window, and its fit.

- **Geocode precision** decides the travel times: *house* → the listing point is routed (§4);
  *street* → a point on the street near its midpoint is routed and every time is labelled
  "approximate"; *district only* → no point routing, the app shows the area's values and says so.
- **Fit and weekly travel time** of a listing use the same formula as a cell (§6), with
  *T_d(l)* from the listing's own times.
- **Rent** of a listing is shown and compared in *Check* ("Listing 2 costs €80 more per month but
  saves 25 min on the bus per week"); it never enters the fit (M4).
- **Freshness:** a listing shows its "online since" date and the time of the last check; listings
  gone from the source disappear with the next snapshot.

## 8.2 Application text

For a listing the app drafts a message the student can send to apply (architecture O26). Inputs:
the student profile (programme, degree, semester, chosen sport and hobby categories), the listing
(title, flatmates, move-in date, what the flat is looking for) and up to five personal lines the
student types (name, age, about me), kept only in `localStorage`. Output: a short text in German
or English in one of three tones (casual, friendly, formal) from templates. Rules: never invent a
fact; a missing value stays as a visible gap in brackets; mention only hobbies the student chose;
the text is generated in the browser and never sent to the server. An LLM-generated variant is a
plan, not part of this methodology until it is decided.

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
| V3 | Completeness (every run) | every campus site found and routable; every offered destination type has ≥ 1 destination (labels: V10); GTFS covers every trip window; coverage of residents by origin cells | fail |
| V4 | Sensitivity and consistency | rankings under fit parameters ±25 % and other trip windows (Spearman rank correlation of areas); reasons match the numbers | reported |
| V5 | Matrix vs. single route | sample of walk and bike pairs, matrix vs. `/route` (archive V10: median deviation 0.5 s) | warn |
| V6 | Users | round 1: interviews on the onboarding questions (S2.0); round 2: app test with 5 students and a task script (S2.8) | reported |
| V7 | Deployment | smoke-test results per release (frontend, health, fit with a persona, cell detail) | fail = rollback |
| V8 | Reproducibility | a teammate runs the pipeline from the README only | reported |
| V9 | Programmes from Alma (every run with a new semester) | share of course buildings matched to an address; programmes without a site; sessions without a room; 20 programmes spot-checked by students against their own timetable | fail below the config limit for matched buildings (draft 95 %) |
| V10 | Labels (every run) | destinations per offered brand and category; spot check of 10 supermarkets and 10 sport places against reality; label time ≥ type time for the same origin and mode | fail if an offered label has no destination |
| V11 | Point routing | listing point times vs. the values of the listing's cell and vs. `/route` (as V5) | median deviation reported |
| V12 | Listings (every listings job) | share of listings with all required fields parsed; geocode precision shares; age of the published snapshot | fail below the config limit for parsing (draft 90 %) or when the snapshot is older than the config limit (draft 36 h) |

## 11. Open methodology questions

| ID | Question | Proposal |
|---|---|---|
| M1 | Fit formula (decay shape, parameters, weights) | §6 proposal; decide in S1.3 with persona examples. Calibrate so that *s(t_d)* ≈ 0.9 (a trip of exactly the fine time should feel good; the §6 draft gives 0.71) |
| M2 | Default fine times, trips per week and trip window per destination type | §3 drafts; check in user-test round 1 (S2.0) |
| M3 | Area value from cell fits | median fit of the populated cells plus the best cell, with the share of cells above the city median |
| M4 | Rent in the fit or as a filter | filter/label only |
| M8 | Defaults for sport and hobby categories (fine time, importance) | 20 min, "important"; check in user-test round 1 (S2.0) |
| M9 | Programmes whose compulsory courses spread over many sites or are mostly online | show the shares as they are; programmes with < 2 weekly hours of compulsory sessions in a semester fall back to `config/campus.yaml` |

Settled:

| ID | Question | Decision |
|---|---|---|
| M5 | Bike + transit | OTP `BICYCLE_PARKING` (bike to a stop, park, ride); still the first cut if time runs short (§4, 23 Nov 2026) |
| M6 | Transit time inside a window | the wait at home counts: arrival − window time for depart-at, required arrival − latest departure for arrive-by (§4, 23 Nov 2026) |
| M7 | Several campus sites per programme | weighted by the weekly hours of compulsory sessions per site from Alma, for the programme, degree and semester the student picks (§3.2, §6 step 1; 26 Nov 2026) |

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v1.3-draft | 2026-11-26 | §3.1: supermarkets get a group next to the brand (organic, package-free, international, discounter, full-range, village and farm shop, other); all 25 sport categories offered; clustering of same-label features within 75 m or one sports centre; offer rule (≥ 1 destination, no remark on the count) | F2.1 taxonomy measured on the extract; Juju's decisions of 26 Nov 2026 (groups clustered in the pipeline, "everything in") |
| v1.2-draft | 2026-11-26 | §3.1 destination labels (favourite supermarkets by brand, sport and hobby categories replacing `gym`, `climbing`, `swimming`, `sports_club`, `music`; religion); §3.2 programmes and campus sites from Alma with degree and semester; §6: grocery uses the chosen brands, each sport/hobby category is its own term with the time to the amenity only (no trips per week, not in the weekly travel time), campus weighted by site shares (M7 settled); §8.1 listings, §8.2 application text; V9–V12; M8, M9; "onboarding" → "profile panel", "U2" → *Check* where touched | Team decisions QF1–QF6 after the interim presentation (Juju, `docs/extension_plan.md`) |
| v1.1-draft | 2026-11-23 | §4: transit and bike + transit with OpenTripPlanner (O17); M6 decided (the wait at home counts: arrival − window time, or required arrival − latest departure); M5 decided (bike parked, `BICYCLE_PARKING`, still first cut) | T1 decided 23 Nov 2026 (spike PR #79); M6 so that rare buses show in the time students feel |
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
