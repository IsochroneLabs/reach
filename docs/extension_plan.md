# Extension plan — programmes, labelled destinations, listings, design

> **Status:** v0.2 draft (26 Nov 2026), written for Juju after the interim presentation of
> 25 Nov 2026. **Decisions QF1–QF6 taken by Juju on 26 Nov 2026** (§2) and recorded in
> `architecture.md` v1.3-draft (O22–O27), `methodology.md` v1.2-draft, `product.md` v1.2 and
> AGENTS.md rule 6. Still open from F0.2: the data-contract tables (they come with F2.4, F3.4,
> F4.1). Progress of the steps is tracked in the status block of
> [`implementation_plan.md`](implementation_plan.md) like every other step; this file holds the
> steps, their order and a ready-to-paste prompt per step.

The four extensions and the product question each one answers (`product.md`, "The questions they
have"):

| # | Extension | Answers question | In one sentence |
|---|---|---|---|
| X1 | **Programmes from Alma** | 1 (campus) | The pipeline reads the compulsory courses of every programme from the university's course catalogue (Alma), maps their rooms to buildings and addresses, and the app shows where a student actually has lectures and weights the campus sites by weekly hours. |
| X2 | **Labelled destinations** | 3, 4 | Every supermarket carries its brand and every sport or hobby place its categories (tennis, climbing, …), end to end from OSM to the profile panel, so a student can pick favourite supermarkets and their own sports. |
| X3 | **Listings** | 6 (and all) | Current WG-Gesucht listings appear in the app with their parameters and photos, routed with Valhalla and OTP to the student's own destinations; *Check* compares two listings or a listing with the student's own address; each listing offers a draft application text. Refreshed daily once deployed. |
| X4 | **Design system** | quality goals | A distinctive, minimal, editorial frontend inspired by the restraint of fashion-house websites, with explicit rules against the generic "AI look". |

Phases: **F0** decisions → **F1** design system → **F2** labelled destinations → **F3** programmes
from Alma → **F4** listings → **F5** integration and hardening. F1–F3 run partly in parallel; F4
starts once F0 has settled the listing source.

---

## 1. Conflicts with the sources of truth (settled in F0 before any code)

AGENTS.md: if the implementation needs to differ from `architecture.md` or `methodology.md`, stop
and ask first. The extensions touch these points:

| # | What the extension needs | Conflicts with | Proposal |
|---|---|---|---|
| C1 *(decided: A, O24; risk in N20)* | Listings from WG-Gesucht | `product.md` non-goal "no scraping of listing sites"; WG-Gesucht AGB §7 (12) "Eine Vervielfältigung der Angebote des Internetportals ist nur mit vorheriger Zustimmung der SMP GmbH & Co. KG gestattet", §8 (4) protection of the "gesamte Daten- und Datenbankstruktur" (read 26 Nov 2026); German database right (§ 87b UrhG); photos are the uploaders' copyright; listings contain personal data of third parties (names, ages, faces, phone numbers) | See **QF1**: write to SMP for permission now; build the source-agnostic listing model; ship the import **in the student's own browser** (variant C) as the default and the daily server crawl (variant A) only with written permission |
| C2 *(settled, O24)* | A daily listing job that writes to PostGIS | Architecture rule 6 / O7 ("only `publish` writes results"), O16 (sequential heavy steps) | A second, small writer `publish_listings` with its own schema `listings` and the same atomic switch; a lock so it never overlaps `make refresh` (architecture change, ask first) |
| C3 *(settled, O23)* | Alma as a data source | Architecture §4 lists no university source; O8 (no public data APIs **at runtime**: not violated, Alma is read by the pipeline once per semester) | New source `alma` in §4 with provenance, refresh per semester, manual overrides in `config/campus.yaml` (architecture change) |
| C4 *(settled, M7)* | Several campus sites weighted by weekly hours | Methodology §6 ("several = mean time"), open point M7 | Weight sites by the weekly hours of compulsory courses per site (closes M7; methodology change) |
| C5 *(settled, O22)* | Favourite supermarkets, sport categories | Methodology §3 (one list of destination types, nearest k per type) | A **destination label** below the type (brand or category); travel times stored for the nearest k per type **and** per label; fit uses the chosen labels (methodology + data contract change) |
| C6 *(settled, O25)* | Live routing of an arbitrary listing point | Architecture rule 9: caches key only on the weight vector | No cache for point routing; one request routes one point to all needed destinations in < 2 s |
| C7 *(settled, O26)* | Application text with an LLM (optional) | Rule 9 (privacy), "no new paid service without asking" | **QF2**: templates in the browser first; an LLM only after an explicit yes |
| C8 *(settled, O27)* | Self-hosted web fonts | `web/src/index.css` comment "System fonts only" (privacy rule, no third-party fonts) | Self-host OFL fonts from our own origin (no third party); every font file is a dependency decision (ask first) |

## 2. Decisions (F0.1)

Taken by Juju on 26 Nov 2026; Rico and Socke review them in the PR.

| # | Decision | Recorded in |
|---|---|---|
| **QF1** | **(A)** WG-Gesucht is crawled daily on the server. The permission request (appendix A) is still sent; data minimisation and the off switch stay (notes N20) | architecture O24, methodology §8.1 |
| **QF2** | **(a)** templates in the browser now; **(b)** LLM variant kept as a plan, needs its own yes | architecture O26, methodology §8.2 |
| **QF3** | **(i)** the grocery term uses the nearest of the chosen brands | architecture O22, methodology §6 |
| **QF4** | **(i)** every chosen sport/hobby category is its own term, **but only the time to the amenity**: no trips per week, not part of the weekly travel time | architecture O22, methodology §3.1, §6 |
| **QF5** | **(ii)** the student picks the semester (default 1) **and the degree (bachelor/master)** | architecture O23, methodology §3.2 |
| **QF6** | **Atelier**; no dark mode for now | architecture O27 |

### Questions as asked (for reference)

| # | Question | Options | Recommendation |
|---|---|---|---|
| **QF1** | Where do listings come from? | **(A)** server crawls WG-Gesucht daily, stores facts and image URLs · **(A′)** crawl without permission, facts only, no photos, no text · **(C)** "Send to reach": a bookmarklet (desktop) and a paste box (mobile) extract the listing **in the student's browser** from the page they are looking at; nothing passes through our server | **C as the default, A only with written permission of SMP GmbH & Co. KG.** Juju sends the request mail (appendix A) now; if no yes by 4 Jan 2027, A stays off and C ships. A′ is not recommended: systematic extraction is exactly what §87b UrhG and AGB §7 (12) cover, and the app is public under the university's name. The listing model, routing, API and UI (F4.1, F4.5–F4.8) are identical for A and C. |
| **QF2** | How is the application text produced? | **(a)** templates in the browser (profile + listing + a few personal lines, DE/EN, three tones) · **(b)** LLM through our API (needs a key, cost, profile data to a third party) | **(a)**; (b) later as an opt-in experiment only after a separate yes (new paid service, privacy review) |
| **QF3** | What does "favourite supermarket" mean in the fit? | **(i)** the grocery term uses the nearest of the chosen brands only · **(ii)** a bonus on top of the generic grocery term | **(i)**: one term, time = minimum over the chosen brands; without a choice the term uses every supermarket, as now |
| **QF4** | How do sports and hobbies enter the fit? | **(i)** each chosen category (tennis, climbing, choir, …) is its own term with importance, trips per week and fine time · **(ii)** one "sport" term over all chosen categories | **(i)**: matches how students think ("tennis twice a week, bouldering once"); replaces the current types `gym`, `climbing`, `swimming`, `sports_club`, `music` by two types `sport` and `hobby` with category labels |
| **QF5** | Which Alma courses count? | compulsory courses of **(i)** the first semester · **(ii)** a semester the student picks · **(iii)** all semesters | **(ii)** with default first semester: new students are the user, master's students pick semester 1 of their programme |
| **QF6** | Design direction (§6) | **Atelier** (light, white space, garment-tag labels) · **Monolith** (dark, concrete greys) · **Gothic** (black/white with a blackletter wordmark) | **Atelier** as the main theme, **Monolith** as dark mode; the blackletter wordmark as an option tested in F1.1 |

## 3. Timeline and dependencies

Phase 1 (backend, 14 Dec) and Phase 2 (web app, 9 Jan) of `implementation_plan.md` stay as they
are; the extensions attach to their steps. This roughly doubles the remaining scope in eight weeks
that include Christmas and exams. Keep to the cut order (§5).

| Step | Content | Depends on | Target |
|---|---|---|---|
| F0.1 | decisions QF1–QF6, mail to SMP, design direction | – | 2 Dec |
| F0.2 | product v1.2, architecture/methodology/data-contract proposals for C1–C8 | F0.1, Juju docs stack in `dev` | 4 Dec |
| F1.1 | `docs/design.md`: direction, rules, tokens, prototype page | F0.1 (QF6) | 4 Dec |
| F2.1 | taxonomy: brands and sport/hobby categories, measured on the extract | – | 4 Dec |
| F3.1 | Alma recon spike | – | 4 Dec |
| F1.2 | tokens, fonts, base CSS, app shell restyled | F1.1 | 11 Dec |
| F2.2 | labels in `validate` | F2.1, S1.6 | 11 Dec |
| F2.3 | travel times per label | F2.2, S1.8 | 15 Dec |
| F3.2 | `alma` source in `acquire` | F3.1, F0.2 | 15 Dec |
| F4.1 | listing model and data contract | F0.2 | 15 Dec |
| F2.4 | labels in data contract, publish, API | F2.3, S1.10 | 17 Dec |
| F3.3 | programmes → buildings → sites → weights | F3.2 | 18 Dec |
| F1.3 | *Find*/*Check* restyled, monochrome map | F1.2 | 18 Dec |
| F4.2 | listing parser + anonymised fixtures | F4.1 | 18 Dec |
| F2.5 | profile panel: favourite supermarkets, sports and hobbies | F2.4, F1.2 | 22 Dec |
| F3.4 | programmes in data contract, publish, API, fit weights | F3.3, S1.10 | 22 Dec |
| F4.3 | variant C: bookmarklet + paste box (**fallback only**, if the crawl is blocked or refused) | F4.2 | on demand |
| F4.5 | geocoding + routing of a listing point | F4.1, S1.10 | 8 Jan |
| F4.4 | variant A: daily crawl job | F4.2, F4.5 | 12 Jan |
| F3.5 | programme search + "where you study" in the app | F3.4, F1.3 | 8 Jan |
| F4.6 | listing API | F4.5 | 8 Jan |
| F4.7 | listings in *Find* and *Check* (incl. F1.4 listing components) | F4.6, F1.3 | 12 Jan |
| F4.8 | application text | F4.7 | 12 Jan |
| F4.9 | daily schedule on the server (with S3.1) | F4.4 | 14 Jan |
| F5.1 | E2E tests, axe, visual snapshots for all new flows | F2.5, F3.5, F4.7 | 14 Jan |
| F5.2 | validation V9–V12 in `docs/validation.md`, user test incl. listings | all | 16 Jan |

Releases: what is merged by 9 Jan goes into **v0.3.0** (expected: F1.1–F1.3, F2, F3.1–F3.4,
F4.1–F4.2); the rest into **v0.4.0** (16 Jan); fixes into **v1.0.0**.

## 4. Steps and prompts

### How to use the prompts

Paste one prompt per Claude Code session, in order, after the previous step is merged into `dev`
(or explicitly stacked). Every prompt starts with the same preamble; it makes the agent read the
rules and stop for your yes after the plan:

```text
Read AGENTS.md, the folder AGENTS.md of every folder you will touch, docs/extension_plan.md
(step <ID> and §1–§3), docs/notes.md and the sources of truth the step names. I am Juju; branch
from fresh dev (`git fetch --all --prune`) as <branch>. First give me a short plan (files,
tables, config keys, dependencies, doc changes, tests) and bundle at most 4 questions, each with
a recommendation. Wait for my yes. Then small Conventional Commits, lint + tests after each
step, pipeline work verified on the test clip, docs and the status block of
docs/implementation_plan.md updated in the same branch, draft PR into dev, report.
```

Below, each step lists **Branch**, **Touches**, **Done when** and the step-specific part of the
prompt (paste it after the preamble).

---

### Phase F0 — Decisions

#### F0.1 Decisions QF1–QF6 — target 2 Dec

- **Branch:** `docs/juju-extension-decisions`.
- **Touches:** this file (decisions recorded in §2), `docs/notes.md` (one N-entry per open
  risk), `docs/implementation_plan.md` (status).
- **Your part (no agent):** discuss QF1–QF6 with Rico and Socke; send the mail of appendix A to
  WG-Gesucht (SMP GmbH & Co. KG) and record the date; optionally ask the university (ZDV / Alma
  team) for a data export of the public course catalogue (appendix B), which would replace F3.2.
- **Done when:** every QF has an answer and a date in §2.

```text
Step F0.1. Record the team's answers to QF1–QF6 that I give you below in §2 of
docs/extension_plan.md (answer, date, who decided), move settled conflicts in §1 to "settled",
add an N-entry in docs/notes.md for each risk that stays open (WG-Gesucht permission pending,
Alma reachability), and update the status block of docs/implementation_plan.md.
Answers: <paste the answers here>.
```

#### F0.2 Proposals for product, architecture, methodology, data contract — target 4 Dec

- **Branch:** `docs/juju-extension-sources-of-truth`.
- **Touches:** `docs/product.md` (v1.2: listings in *Check*, favourites, sports/hobby categories,
  programme with semester; the non-goal on listing sites reworded per QF1), `docs/architecture.md`
  (sources `alma` and `listings`, `publish_listings` + schema `listings`, lock against the
  refresh, live point routing without cache), `docs/methodology.md` (destination labels, sport
  and hobby types, campus weights by weekly hours closing M7, listing travel times, V9–V12),
  `docs/data_contract.md` (tables of F2.4, F3.4, F4.1), `docs/glossary.md` (§7).
- **Done when:** your human said yes to each document change; versions bumped and change-log
  lines added.

```text
Step F0.2. Turn the settled decisions of §2 into proposed changes of docs/product.md (v1.2),
docs/architecture.md, docs/methodology.md, docs/data_contract.md and docs/glossary.md, as
listed in step F0.2. This is an Ask-first change: show me each document's diff separately and
wait for my yes per document before you commit it. Bump the version line and add a change-log
line (date, what, why) in each. Do not touch code or config. If a proposal conflicts with the
Juju docs stack (PRs #83–#86) or with notes N16/N17, report it instead of picking a side.
```

---

### Phase F1 — Design system

The direction is described in §6; F1.1 turns it into a binding `docs/design.md`.

#### F1.1 Design direction and prototype — target 4 Dec · in review (26 Nov 2026)

- **Branch:** `docs/juju-design-system`.
- **Touches:** `docs/design.md` (new), `web/AGENTS.md` (one rule: follow `docs/design.md`),
  one static prototype page (outside `web/src`, e.g. `docs/design/prototype.html`, or a private
  artifact for team review).
- **Done when:** the team picked the direction and the type pairing from the prototype.
- **State (26 Nov 2026):** `docs/design.md` v0.1 and `docs/design/prototype.html` on
  `docs/juju-design-system`; open: pairing A or B. Blackletter wordmark dropped (Juju, 26 Nov 2026).

```text
Step F1.1. Write docs/design.md for the reach web app from §6 of docs/extension_plan.md:
principles, the anti-slop rules as checkable rules, design tokens (colour, type scale, spacing,
rules/lines, motion), the grid for desktop and mobile, the component vocabulary (index label,
garment-tag label, hairline table, big number, text toggle, inverted selection), map style
(monochrome basemap, monochrome fit ramp, no-data hatching), copy tone with good/bad examples,
(no dark mode for now, QF6). Then build ONE static prototype page that shows Find and a listing detail in the
Atelier direction with two type pairings side by side, so the team can choose. Read
web/src/index.css and the components first; name every current pattern that breaks a rule
(e.g. pill buttons, shadows, rounded radius, teal accent, viridis ramp). Do not copy logos,
fonts, images or layouts of real brands; describe the references in words. Fonts: propose only
OFL-licensed fonts we can self-host, with licence links verified; no font is added yet.
```

#### F1.2 Tokens, fonts, base CSS, shell — target 11 Dec

- **Branch:** `feature/juju-design-tokens`.
- **Touches:** `web/src/index.css` (split into `web/src/styles/` if it helps), `web/public/fonts/`
  (self-hosted, after the yes), `Header`, `ProfilePanel`, `BottomSheet`, `Toast`, `StatusBanner`.
- **Coordinate with Rico:** the components come from his Phase 2 branches.
- **Done when:** shell, header and panel follow `docs/design.md`; `npm run lint && npm run build
  && npm run test:e2e` green; axe without serious violations; screenshots before/after in the PR.

```text
Step F1.2. Implement the tokens and base styles of docs/design.md in web/: CSS custom
properties, type scale, self-hosted fonts (ask first: list each font file, size and licence),
reset of radius/shadow/accent, focus styles that stay visible in the new look (light theme only, QF6). Restyle the shell, header, profile
panel, bottom sheet, toast and status banner. No new npm dependency. Keep every existing test
green; add Playwright screenshots of Find on mobile and desktop to the PR description.
```

#### F1.3 *Find*, *Check* and map restyled — target 18 Dec

- **Branch:** `feature/juju-design-find-check`.
- **Touches:** `FindResults`, `CheckResults`, `CompareView`, `PlaceCard`, `Reasons`, `Minutes`,
  `DataNote`, `MapView` (style JSON, fit ramp, legend).
- **Done when:** both modes follow `docs/design.md`; the fit ramp passes a contrast check and
  stays readable in grayscale; axe green.

```text
Step F1.3. Restyle Find and Check after docs/design.md: the fit as the big number, reasons as
an indexed list (01, 02, …), trips as a hairline table with tabular numerals, compare view as
columns with the differences in plain language. Replace the viridis ramp by the monochrome ramp
of docs/design.md (7 steps, no-data hatched) and hand-write a monochrome basemap style for the
self-hosted tiles of N18. Check contrast of every text on the map and of the ramp against the
basemap; report the numbers.
```

#### F1.4 Listing components — with F4.7

Listing card (photo-first, data in micro type), gallery, parameter table, application-text
sheet. Built on fixtures inside F4.7; no separate branch.

---

### Phase F2 — Labelled destinations (supermarkets, sports, hobbies)

#### F2.1 Taxonomy, measured on the extract — target 4 Dec

- **Branch:** `docs/juju-destination-labels` (+ `exp/juju-label-counts` for the measurement, not
  merged).
- **Touches:** `docs/osm_tagging.md` (brand normalisation, sport and hobby categories with their
  OSM tags), `config/config.yaml` (new keys only, with comments: `labels` under `grocery`, new
  types `sport` and `hobby` as proposals until F0.2 is settled).
- **Done when:** a table with the count per brand and per category in the routing area, gaps
  named, the taxonomy confirmed.

```text
Step F2.1. Measure on the current clipped OSM extract (data/, never committed) how supermarkets
and sport/hobby places are tagged in the routing area: shop=supermarket with brand,
brand:wikidata and name; leisure=sports_centre|pitch|fitness_centre|swimming_pool|track,
club=sport and sport=* values; hobby candidates (amenity=music_school|arts_centre|
community_centre, leisure=hackerspace|dance, club=*). Propose (1) a brand normalisation
(REWE, EDEKA, Lidl, ALDI SÜD, Kaufland, PENNY, Netto, Alnatura, denn's, tegut, …, others →
"independent") keyed on brand:wikidata with name fallback, and (2) sport categories (racket:
tennis, table tennis, badminton, squash, padel; climbing/bouldering; swimming; fitness; team ball
sports; running/athletics; martial arts; dance; yoga; rowing/canoe; cycling; equestrian; …) and
hobby categories, each with its OSM tags (methodology §3.1). Report counts per label, labels with < 1 destination,
and polygons vs. points. Write the result to docs/osm_tagging.md and the config keys (new keys
only, commented). Keep the measurement script on the exp branch.
```

#### F2.2 Labels in `validate` — target 11 Dec

- **Branch:** `feature/juju-destination-labels`.
- **Touches:** `pipeline/src/reach_pipeline/destinations.py` (from S1.6), `stages/validate.py`,
  `config.py`, tests with a small OSM fixture.
- **Done when:** every destination has `labels` (array; one place can have several sports);
  validation report lists counts per label and fails per config limit if a label offered in the
  panel has no destination (V10).

```text
Step F2.2. Extend the destinations of S1.6 with labels from docs/osm_tagging.md: brand label
for grocery, category labels for sport and hobby (a destination may carry several). Vectorised
tag matching, no loops over features. Add V10 to the validation report part 1: count per label,
fail if a label that the config marks as offered has 0 destinations, warn below the config
limit. Unit tests on a small OSM fixture with tagged and untagged examples; run the test clip.
```

#### F2.3 Travel times per label — target 15 Dec

- **Branch:** `feature/juju-label-travel-times`.
- **Touches:** `stages/travel_times.py` (from S1.8), config `nearest_k_per_label`.
- **Done when:** for every cell the nearest k per type **and** per label are routed (deduplicated);
  runtime and peak memory before/after in the PR.

```text
Step F2.3. Extend the travel-time stage so the target set per cell is the union of the nearest
k per destination type and the nearest k_label per (type, label), deduplicated, with the same
straight-line prefilter and costmatrix blocks; transit uses the same targets. k_label comes from
config. Measure runtime, number of pairs and peak memory on the test clip and estimate the city;
put both in the PR. Plausibility: every label time ≥ the type time of the same cell and mode.
```

#### F2.4 Data contract, publish, API — target 17 Dec

- **Branch:** `feature/juju-label-api`.
- **Touches:** `infra/db/run_schema.sql` (`destinations.labels`, table `destination_labels`),
  `stages/publish.py`, data-contract tests, API `GET /api/destination-types` (labels with counts
  and display names), `POST /api/fit` (profile with `labels`), reasons naming the place
  ("REWE Mühlstraße 6 min on foot").
- **Done when:** data-contract test green; fit with labels < 500 ms for the city.

```text
Step F2.4. Implement the label part of docs/data_contract.md (as settled in F0.2): run schema,
publish, data-contract test. API: destination types return their labels; the fit profile takes
{"grocery": ["rewe", "lidl"], "sport": {"tennis": {...weights}, ...}}; grocery uses the minimum
over the chosen brands (QF3), every chosen sport/hobby category is its own term (QF4). Reasons
name the destination. Response-time test for the whole city; POST bodies stay unlogged.
```

#### F2.5 Profile panel — target 22 Dec

- **Branch:** `feature/juju-label-panel`.
- **Touches:** `ProfilePanel`, `state/profile.ts`, `state/hash.ts` (URL encoding), i18n EN/DE,
  map layer of chosen destinations, fixtures.
- **Done when:** a student picks several supermarkets and sports, the map recolours at once, the
  choice survives a reload and a shared link; Playwright test.

```text
Step F2.5. In the profile panel add "Your supermarkets" (multi-select of brands with counts,
default: any) and "Sports and hobbies" (categories grouped, searchable, each with importance and
fine time only: no trips per week, methodology §6 QF4), styled per docs/design.md (text
toggles, no chips with icons). Encode the choice compactly in the URL hash; extend the hash
tests. Show the chosen destinations as small labelled points on the map. Update fixtures and
add a Playwright test: pick Lidl + tennis, check the reasons mention both.
```

---

### Phase F3 — Programmes from Alma

#### F3.1 Recon spike — target 4 Dec

- **Branch:** `exp/juju-alma-recon` (not merged) + an N-entry in `docs/notes.md` on
  `docs/juju-alma-recon`.
- **Known (26 Nov 2026):** the university says the public course catalogue is reachable through
  the Alma portal without login, the full one only after enrolment; `alma.uni-tuebingen.de`
  refused connections from outside during this check (possibly university network only — test
  from eduroam/VPN and from the server of D1).
- **Done when:** the N-entry answers: reachable from where; `robots.txt` and terms of use; the
  path programme → module tree (compulsory/elective, recommended semester) → course → dates
  (weekday, time, room) → building with address; exports that avoid HTML scraping (iCal per
  course, room/building lists); page count and polite crawl time; approach and libraries.

```text
Step F3.1 (exploration, exp branch, not merged). Find out how to read from the public Alma
course catalogue (HISinOne) of the University of Tübingen, for one programme first (e.g.
B.Sc. Informatik): programme → module tree with compulsory/elective and recommended semester →
courses of the current semester → dates (weekday, start, end, room) → building and its address.
Check robots.txt and Alma's terms of use, whether the pages are server-rendered or need
JavaScript/session state, and whether exports exist (iCal per course, room or building lists).
Crawl politely (1 request/s, generic user agent without personal data, stop on errors). Report
in a docs/notes.md N-entry: reachability (from home, eduroam/VPN, server), legal notes, page
structure with example URLs, estimated pages and crawl time for all programmes, proposed
libraries (ask first; prefer httpx + a small HTML parser, no headless browser on the server).
```

#### F3.2 Source `alma` in `acquire` — target 15 Dec

- **Branch:** `feature/juju-alma-acquire`.
- **Touches:** `pipeline/src/reach_pipeline/alma.py` (new), `stages/acquire.py`, config section
  `alma` (base URL, semester, rate limit, user agent, refresh policy), provenance row `alma`,
  recorded HTML fixtures (< 1 MB).
- **Done when:** `make pipeline STAGE=acquire` fetches or reuses the semester's catalogue; raw pages
  under `data/raw/<run_id>/alma/`; unchanged semester → reused; network retries only.

```text
Step F3.2. Implement the source alma from the F3.1 notes: crawler in
pipeline/src/reach_pipeline/alma.py, called by acquire, all values from a new config section
alma (base URL, semester, rate limit, timeout, user agent, refresh: once per semester unless
forced). Raw pages to data/raw/<run_id>/alma/ with a provenance row; reuse the previous
semester's pages when nothing changed. Polite: rate limit, retries with backoff for network
errors only, fail loudly on unexpected page structure. Unit tests replay recorded pages (small,
public, no personal data). New dependency only after my yes.
```

#### F3.3 Programmes → buildings → sites → weights — target 18 Dec

- **Branch:** `feature/juju-programme-sites`.
- **Touches:** `pipeline/src/reach_pipeline/programmes.py` (new), `stages/validate.py`,
  `config/campus.yaml` (manual overrides win over Alma; existing values unchanged without a yes).
- **Done when:** tables `programmes`, `programme_modules`, `course_sessions`, `campus_buildings`,
  `programme_sites` (programme × semester × site → weekly hours, share) as GeoParquet; V9 checks.

```text
Step F3.3. Parse the alma raw pages into programmes (degree, name, exam regulation version),
compulsory modules with recommended semester, course sessions (weekday, start, end, room,
building) and buildings with address. Match each building to an OSM address/building in the
clipped extract (EPSG:25832, PostGIS-free in this stage, GeoPandas with spatial index); assign
buildings to campus sites (existing sites of config/campus.yaml, unassigned buildings clustered
by distance from config). Compute programme_sites: weekly hours of compulsory sessions per
programme × semester × site and their share. Manual overrides in config/campus.yaml win. Add V9
to the report: building match rate (fail below config limit), programmes without a site,
sessions without a room. Unit tests on recorded pages; test clip run.
```

#### F3.4 Data contract, publish, API, fit weights — target 22 Dec

- **Branch:** `feature/juju-programme-api`.
- **Touches:** run schema + publish (`programmes`, `programme_sites`, `campus_buildings`),
  travel times to every campus site that has a programme, `GET /api/programmes?q=` (search,
  degree filter), `GET /api/programmes/{id}?semester=`, fit with `programme_id` + `semester`
  (campus term weighted by `share`, closes M7).
- **Done when:** data-contract test green; persona fits unchanged where Alma agrees with
  `campus.yaml`, differences listed in the PR.

```text
Step F3.4. Publish the programme tables per docs/data_contract.md, make the travel-time stage
route to every campus site used by any programme, and extend the API: programme search (POST
body or query as settled in N17 for privacy), programme detail with sites, buildings and weekly
hours per semester, and the fit's campus term weighted by share (methodology as settled in F0.2).
Compare persona fits before/after and list the differences in the PR.
```

#### F3.5 Programme search and "where you study" — target 8 Jan

- **Branch:** `feature/juju-programme-panel`.
- **Touches:** `ProfilePanel` (programme search with degree and semester), map layer of the
  student's buildings with weekly hours, *Check* trips per site, i18n, fixtures.
- **Done when:** a student types "Informatik", picks B.Sc. semester 1 and sees their buildings on
  the map and the weighted campus time in *Check*; Playwright test.

```text
Step F3.5. Replace the programme list in the profile panel by a search over the programmes API
(degree select bachelor/master, semester select, default 1; methodology §3.2), keep the default campus mix when none is chosen.
Add a map layer "Where you study": the student's buildings as points sized by weekly hours, with
an indexed list as the non-map alternative. In Check show the time to each site and its weight.
Styled per docs/design.md; URL hash and fixtures updated; Playwright test.
```

---

### Phase F4 — Listings

#### F4.1 Listing model and data contract — target 15 Dec

- **Branch:** `docs/juju-listing-contract`.
- **Touches:** `docs/data_contract.md` (schema `listings`), `config/config.yaml` (section
  `listings`, `enabled: false` for variant A).
- **Fields (proposal):** `listing_id`, `source`, `source_url`, `kind` (`wg_room`, `studio`,
  `flat`), `title`, `rent_total_eur`, `rent_cold_eur`, `utilities_eur`, `other_costs_eur`,
  `deposit_eur`, `size_m2`, `rooms`, `flatmates` (count, genders, age range — no names),
  `looking_for`, `available_from`, `available_to`, `furnished`, `features[]` (internet,
  balcony, washing machine, …), `district`, `address_text`, `geocode_precision` (`house`,
  `street`, `district`), `geom`, `image_urls[]` (links, never copies), `description_excerpt`
  (contact data stripped), `online_since`, `first_seen`, `last_seen`.
- **Done when:** confirmed (data-contract change, ask first).

```text
Step F4.1. Propose the schema listings in docs/data_contract.md from the field list of step F4.1:
tables listings, listing_travel_times (listing × destination × mode × trip window, raw seconds,
transit legs), the switch view, retention (rows gone from the source for N days are deleted, N
from config) and which fields variant C keeps only in the browser. Mark every field that can
hold personal data and how it is reduced (no names, contact data stripped, images linked not
copied). Add the config section listings with comments (variant A disabled). Ask before
committing the contract.
```

#### F4.2 Listing parser and fixtures — target 18 Dec

- **Branch:** `feature/juju-listing-parser`.
- **Touches:** `pipeline/src/reach_pipeline/listings/parse.py` (Python, for A) and
  `web/src/listings/extract.ts` (TypeScript, for C) implementing the **same field spec**,
  shared anonymised HTML fixtures (names, faces, phone numbers removed by hand).
- **Done when:** both parsers pass the same fixture expectations; field coverage per fixture
  reported; parse failures produce a clear partial result, never a crash.

```text
Step F4.2. Write one field spec (docs/data_contract.md listings) and two parsers for WG-Gesucht
ad pages: Python for the server variant, TypeScript for the in-browser variant, both tested
against the same anonymised fixtures (3–5 saved ad pages I provide, personal data removed; keep
each < 200 KB) with one expected JSON per fixture. Parse German numbers, dates and "ab sofort",
warm/cold rent, size, flatmates, features, address parts, image URLs. Unknown fields stay null
with a warning; a missing address is an error the UI can explain. No network in tests.
```

#### F4.3 Variant C: "Send to reach" — fallback only (QF1 = A)

- **Branch:** `feature/juju-listing-import`.
- **Touches:** bookmarklet (built from `extract.ts`, offered on an about page), paste box in the
  header search ("paste a listing link or text"), *Check* place kind `listing`, URL hash.
- **Done when:** on desktop the bookmarklet opens reach with the listing in *Check*; on mobile
  pasting the ad text works; the listing never reaches our server except its address through the
  address search.

```text
Step F4.3. Build the in-browser import: (1) a bookmarklet generated from web/src/listings/
extract.ts at build time that, run on a WG-Gesucht ad the student is viewing, opens reach with
the extracted listing encoded in the URL hash; (2) a paste box that accepts the copied ad text
and extracts the same fields client-side. Add the place kind "listing" to Check (photos shown
from their original URLs, parameters, link to the ad). Only the address goes to the API, via the
POST address search. Document in the about page what happens to the data. Playwright test with a
fixture page.
```

#### F4.4 Variant A: daily crawl job — target 12 Jan

- **Branch:** `feature/juju-listing-crawl`.
- **Touches:** `pipeline/src/reach_pipeline/listings/crawl.py`, `stages/publish_listings.py`,
  `make listings`, lock file shared with `make refresh`, notification on failure.
- **Done when:** on the test clip a run fetches the Tübingen search pages (WG rooms, studios,
  flats), detail pages only for new or changed ids, geocodes, routes (F4.5), validates (V12) and
  switches `listings.current` atomically; stops on captcha or structure change and notifies.

```text
Step F4.4. QF1 = A (architecture O24, notes N20). Implement make listings:
crawl the Tübingen search result pages from config, fetch detail pages only for new or changed
listing ids, parse with listings/parse.py, geocode and route (F4.5), validate (V12: parse rate,
geocode precision shares, freshness), write a manifest and switch listings.current atomically in
publish_listings. Polite rate limit from config, stop and notify on captcha or unexpected pages,
never bypass bot protection. Take the lock shared with make refresh. Recorded pages in tests.
```

#### F4.5 Geocoding and routing of a listing point — target 8 Jan

- **Branch:** `feature/juju-point-routing`.
- **Touches:** `pipeline/src/reach_pipeline/listings/geocode.py` (against `current.addresses`:
  exact → street → district, with precision), API `POST /api/place` (one point → times to the
  nearest k per type and label and all campus sites, walk/bike via Valhalla matrix, transit via
  OTP per trip window; no cache, C6), shared routing code with `travel_times`.
- **Done when:** a point is answered in < 2 s on the server; times agree with the cell values
  of the same point within V5 tolerances; street-level points are labelled "approximate".

```text
Step F4.5. Implement geocoding of listing addresses against current.addresses (exact house
number, else street midpoint, else district centroid; precision stored) and point routing that
reuses the travel-time code: one point to the nearest k per type and label and all campus sites,
walk/bike as one Valhalla costmatrix request, transit as bounded-concurrency OTP queries per
trip window. Expose it as POST /api/place (body not logged, no cache). Test: recorded engine
responses; latency on the test clip; compare with the cell values of the same point.
```

#### F4.6 Listing API — target 8 Jan

- **Branch:** `feature/juju-listing-api`.
- **Touches:** `GET /api/listings` (filters: kind, max rent, min size, available from, bbox),
  `GET /api/listings/{id}` (detail + raw times), `POST /api/listings/fit` (profile → fit per
  listing, sorted), smoke test extended.
- **Done when:** fit for all current listings < 500 ms; data-contract test green.

```text
Step F4.6. Add the listing endpoints of step F4.6 reading only listings.current; the fit per
listing uses the same fit code as cells (labels, programme weights). Return image URLs as links,
never proxied. Response-time test with 500 synthetic listings; extend the deploy smoke test with
one listings request when listings are enabled.
```

#### F4.7 Listings in *Find* and *Check* — target 12 Jan

- **Branch:** `feature/juju-listing-views`.
- **Touches:** listings layer and list in *Find* (sorted by fit, filters), listing detail
  (gallery, parameter table, times to the student's destinations per mode, fit, link to the ad),
  *Check* with listing places (two listings, or a listing and the student's own address), F1.4
  components.
- **Done when:** the compare "Listing A vs. your address" reads in plain language incl. rent;
  axe and Playwright green on mobile and desktop.

```text
Step F4.7. Show listings in the app per docs/design.md: in Find a listings toggle with pins and a
photo-first list sorted by the student's fit (filters: kind, max rent, size, available from); a
listing detail with gallery, parameter table, trips to the student's own destinations per mode
and window, fit and a link to the original ad; in Check allow places of kind listing next to
addresses, so two listings or a listing and an own address can be compared with the existing
plain-language differences incl. rent. Variant C listings and variant A listings use the same
components. Fixtures, Playwright, axe.
```

#### F4.8 Application text — target 12 Jan

- **Branch:** `feature/juju-application-text`.
- **Touches:** `web/src/listings/application.ts` (templates DE/EN, tones: casual, friendly,
  formal), a sheet in the listing detail with a few personal fields kept in `localStorage`
  only, copy button.
- **Done when:** the text uses programme, semester, matching hobbies, move-in date and the
  listing's details without inventing facts; snapshot tests; nothing is sent to a server.

```text
Step F4.8. Build the application-text suggestion in the browser (QF2 a): templates in German
and English, three tones, filled from the student profile (programme, semester, chosen
sports/hobbies that match the listing or the area), the listing (title, flatmates, move-in date,
"looking for") and up to five personal lines the student types (name, age, about me), stored only
in localStorage and deletable. Rules: never invent facts, mark gaps as [brackets], keep it under
the length WG-Gesucht messages usually have. Copy button, no server call. Snapshot tests per
tone and language.
```

#### F4.9 Daily schedule on the server — target 14 Jan

- **Branch:** `feature/juju-listing-schedule` (together with S3.1).
- **Touches:** systemd timer or cron on the server (`docs/deployment.md` runbook), lock with the
  refresh, notification, freshness check in the smoke test (snapshot younger than 36 h).
- **Done when:** three consecutive daily runs succeeded on the server, measured runtime and peak
  memory in the runbook.

```text
Step F4.9. Schedule make listings daily on the server (time and timezone from config) next to
the scheduled refresh of S3.1: systemd timer files in infra/, lock shared with make refresh,
failure notification through the existing webhook, freshness check (listings.current younger
than the config limit) in the smoke test. Document install, logs and disabling in
docs/deployment.md. Do not log in to the server yourself; give me the commands to run.
```

---

### Phase F5 — Integration and hardening

#### F5.1 Tests across the new flows — target 14 Jan

- **Branch:** `feature/juju-extension-quality`.
- **Done when:** Playwright on mobile and desktop for: favourites + sports → *Find*; programme
  search → buildings; listing import → *Check*; compare listing vs. own address; application
  text. axe without serious violations; visual snapshots of the main screens.

```text
Step F5.1. Add Playwright flows for all extension features (list in step F5.1) on mobile and
desktop with API fixtures, axe checks on each screen and visual snapshots of Find, Check, listing
detail and the application sheet. Fix what fails; never disable a check. Make sure CI runs them.
```

#### F5.2 Validation and user test — target 16 Jan

- **Branch:** `docs/juju-extension-validation`.
- **Done when:** V9–V12 in `docs/validation.md` with numbers; the S2.8 user test script includes
  "compare two listings" and "write an application"; findings recorded.

```text
Step F5.2. Report V9–V12 (§5 of docs/extension_plan.md) in docs/validation.md with numbers from
the latest run, add listing and application tasks to the S2.8 user-test script, and record the
findings and resulting changes. Update README (what it does, data sources incl. Alma and the
listing source with licence notes) and CHANGELOG.
```

## 5. Cut order and new validation

**Cut order** (first cut first): (1) LLM application text (never started without QF2 b);
(2) variant A daily crawl (falls back to C); (3) hobby categories beyond sport; (4) "where you
study" building layer (the weights stay); (5) listing photo gallery (one photo + link). Never cut:
supermarket brands and sport categories, programme weights from Alma or `campus.yaml`, listing
check through variant C, the design system of F1.1–F1.3.

| # | Check | Limit (config) |
|---|---|---|
| V9 | Alma: share of course buildings matched to an address; programmes without a site; 20 programmes spot-checked by students against their own timetable | fail < 95 % matched |
| V10 | Labels: destinations per offered brand/category; spot check of 10 supermarkets and 10 sport places against reality | fail if an offered label has 0 |
| V11 | Listing point routing vs. cell values and vs. `/route` (as V5) | median deviation reported |
| V12 | Listings (A): parse rate of required fields, geocode precision shares, snapshot age | fail < 90 % parsed, > 36 h old |

## 6. Design direction (input for F1.1)

The references (Maison Margiela, Rick Owens, Yeezy, Chrome Hearts) are shops, but what makes them
recognisable carries over to a map app: **restraint, typography as the main graphic element,
large empty space and very few, very deliberate signature details.** We take the principles, not
their logos, fonts, images or layouts.

| Reference | What we take | Where it shows in reach |
|---|---|---|
| Maison Margiela | white space, the blank white label, numbered tags | destinations and reasons as an index (`01 CAMPUS`, `02 SUPERMARKET`); small garment-tag labels with a hairline frame for mode, trip window and data date |
| Rick Owens | radical reduction, dark concrete greys, monumental type | dark mode *Monolith*; the fit number set very large like a price |
| Yeezy | neutral ground, tiny type, images do the work | listing grid: photos on a light grey ground, data in small uppercase micro type |
| Chrome Hearts | gothic black and white, one ornament | ~~optional blackletter wordmark~~ dropped after the prototype review (Juju, 26 Nov 2026) |

**Rules against the generic AI look** (become checkable rules in `docs/design.md`):

1. No gradients, glass effects, glows or drop shadows; depth comes from hairlines (1 px) and
   inversion (black block = selected).
2. Radius 0 everywhere; no pill buttons, no rounded cards.
3. No emoji, no icon library; text labels first, at most a handful of hand-drawn SVG glyphs
   (arrow, close, pin).
4. No feature-card grids (icon + title + two lines), no centred hero, no "Discover your perfect…"
   copy, no exclamation marks.
5. One ink colour plus greys; no brand accent (teal, purple, blue). The only colour comes from
   listing photos.
6. Left-aligned, asymmetric 12-column grid; the map full-bleed; the panel is a column with a
   hairline divider, not a floating card.
7. Typography: one neo-grotesk for text, one monospace for numbers and labels (tabular numerals),
   two weights, a strict scale with big jumps (11 / 13 / 16 / 24 / 64 / 160 px); uppercase only for
   micro labels with tracking.
8. Motion only as 120–180 ms opacity/position, nothing bouncy; `prefers-reduced-motion` respected.
9. Map: grayscale basemap, cells in a **monochrome ramp** (light → black); no-data hatched. This
   is on-brand and colour-blind safe by construction.
10. Copy: short, declarative, factual ("12 min by bus at 8:00. Last bus home 0:41.").

Fonts are self-hosted, OFL-licensed, chosen in F1.1 from candidates such as a system
Helvetica/Arial stack (zero bytes), Host Grotesk or Schibsted Grotesk for text, IBM Plex Mono or
JetBrains Mono for numbers (**[VERIFY]** licences in F1.2); the blackletter wordmark was dropped.

## 7. Glossary candidates (added in F0.2)

**destination label** (brand or category below a destination type) · **favourite supermarket** ·
**sport category / hobby category** · **programme site share** (weekly hours of compulsory courses
per site) · **listing** (a room or flat offer from a listing source) · **listing source**
(WG-Gesucht; variant A server, variant C browser) · **geocode precision** · **application text**.

## Appendix A — Request to WG-Gesucht (send from the team, German)

> Betreff: Anfrage Datennutzung für studentisches Uni-Projekt (Universität Tübingen)
>
> Sehr geehrte Damen und Herren,
>
> wir sind drei Studierende der Universität Tübingen und entwickeln im Kurs DS500 eine nicht
> kommerzielle Web-App, die Studienanfänger:innen zeigt, wie lange ihre Alltagswege (Campus,
> Supermarkt, Sport) von einer Wohnung aus zu Fuß, mit dem Rad und mit dem Bus dauern. Wir würden
> gern aktuelle WG- und Wohnungsangebote in Tübingen mit diesen Wegezeiten anzeigen, jeweils mit
> Link auf die Anzeige bei WG-Gesucht, ohne Kontaktdaten und ohne eigene Kopien der Fotos.
>
> Dürfen wir dafür einmal täglich die öffentlichen Tübinger Angebote abrufen, oder gibt es eine
> Schnittstelle bzw. ein Partnerprogramm, das Sie stattdessen empfehlen? Die App läuft bis Ende
> März 2027 und ist ein Lehrprojekt.
>
> Mit freundlichen Grüßen
> <Namen, Kontakt>

## Appendix B — Request to the university (optional, German)

> Betreff: Export des öffentlichen Vorlesungsverzeichnisses (Alma) für ein Lehrprojekt
>
> … wir möchten für ein Lehrprojekt (DS500) die Pflichtveranstaltungen je Studiengang mit Raum und
> Gebäude aus dem öffentlichen Vorlesungsverzeichnis nutzen, um Studienanfänger:innen zu zeigen,
> an welchen Standorten sie Vorlesungen haben. Gibt es dafür einen Export (CSV, iCal, Schnittstelle)
> oder dürfen wir die öffentlichen Seiten automatisiert und gedrosselt (1 Anfrage/s, einmal pro
> Semester) abrufen? …

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v0.2 draft | 2026-11-26 | Decisions QF1–QF6 recorded (§2); conflicts C1–C8 settled; steps adapted (crawl is the main path, browser import only as fallback; sport/hobby without trips per week; degree choice; no dark mode) | Juju's decisions; architecture v1.3-draft, methodology v1.2-draft |
| v0.1 draft | 2026-11-26 | First extension plan: conflicts C1–C8, questions QF1–QF6, phases F0–F5 with prompts, cut order, V9–V12, design direction | Juju's request after the interim presentation of 25 Nov 2026 |
