# Notes — findings and open points

Points that are not (yet) part of [`architecture.md`](architecture.md) or
[`methodology.md`](methodology.md) but matter for the work. Each entry says why it matters and
what to do. Entries N1–N6 carry findings over from the archived project
(`archive/2026-11-21-planner`, `docs/notes.md`, `docs/validation_report.md`); they were measured
with Valhalla 3.9.1 on the Tübingen tiles of early November 2026.

---

## N1. Valhalla keeps memory per worker thread after large matrices

**Status:** open · **Origin:** archive N4, N12 · **Related:** architecture §6.4, §12, A4

Idle Valhalla uses ~54 MB. During large `costmatrix` requests its memory grows with the worker
threads and is not released: 2 threads → 2.7–3.0 GB peak during a full count incl. cycling, ~2.2 GB
idle afterwards; 1 thread → 1.4 GB peak (slower). Config options (`clear_reserved_memory`,
`max_cache_size`, `MALLOC_ARENA_MAX`) did not help; large cycling source sets reached 3.9–4.0 GiB.
**To do:** in the refresh, restart Valhalla after `travel_times` or run it with one thread;
measure on the server (S1.11, S3.1). Relevant for T1: a transit engine must fit next to this
under A4.

## N2. Elevation changes walking and cycling times

**Status:** settled (archive N5, V11) · **Related:** architecture §6.1, O2

With elevation in the tiles, Valhalla's `pedestrian` costing is slower uphill and on steep
downhill (`use_hills` does not change walking times) and `bicycle` is slower uphill and faster
downhill. Examples: Marktplatz → Schloss on foot 681 s up, 619 s back, 537 s flat (3.39 km/h);
Hauptbahnhof → Waldhäuser-Ost by bike 1,196 s up, 865 s down. Without slopes 3–4 % of the archive's
results changed, mostly on the hillsides north of the centre (Winkelwiese, Wanne,
Waldhäuser-Ost). This is the "Tübingen is hilly" effect the app shows; the test clip is built
without elevation, so its times differ from production.

## N3. Valhalla routes by cost, not time

**Status:** open, tolerated · **Origin:** archive N6, N16 · **Related:** V2

A faster walker can get a longer time to the same place: at 3.39 km/h Valhalla took the steps
Hackersteigle (363 s), from 4 km/h on it avoided them (919 s). Step and grade penalties are not
proportional to time, so the cheapest path changes with the speed or costing. **Consequence for
V2:** "bike ≤ walk" and similar comparisons cannot be exact; they are checked as shares with
warn/fail limits (archive: violating shares 0.3–6 % depending on the pair).

## N4. Use `costmatrix` for every matrix

**Status:** settled (archive N8) · **Related:** `config/valhalla.json`, architecture §6.4

With `select_optimal` Valhalla answers small requests with `timedistancematrix`, which misses
routes (e.g. wheelchair routes `/route` finds) and gave different times for 2.5 % of pairs than
the pipeline blocks. The algorithm can only be set in the service config, not per request.
`costmatrix` is also the source of the memory growth (N1).

## N5. Block matrices and one-source matrices rarely differ; check the effective config

**Status:** settled (archive N9, V10) · **Related:** V5

`costmatrix` times depend slightly on the request: block matrices were longer than one-source
matrices for ~0.02 % of the pairs within reach (by up to 95 s). Matrix vs. `/route`: median
deviation 0.5 s, 99.7 % within 5 s. A Valhalla container keeps the config it loaded at start (a
single-file bind mount keeps the old inode after `git checkout`): the service copies
`config/valhalla.json` at start and the pipeline compares the copy with the repository file.
Without `VALHALLA_URL` the pipeline stops instead of guessing a port (another project's Valhalla
once answered on `localhost:8002`).

## N6. Cell centroid as origin is robust

**Status:** settled (archive N1, V6) · **Related:** O1

A building-based origin (residential buildings, footprint-weighted medoid) moved origins by 22 m
(median, max 69 m) and changed ~2 % of results, in both directions. The centroid stays. A
`/locate` snap check (origins far from a walkable edge) was never built; worth adding to
`validate` if *Check* answers look wrong at the edge of town.

## N7. The census misses part of the students

**Status:** open · **Related:** A1, methodology §2, §8

Zensus 2022 counts main residences on 15 May 2022. Students registered elsewhere and buildings
finished after 2022 are missing from the populated cells; address cells (A1) cover new buildings
for *Check*, not for the ranking. The rent grid excludes student halls (*ohne Wohnheime*), so halls of
the Studierendenwerk never get a rent value. **To do:** state both limits in the app; consider
listing the halls as information (no scraping; only an openly licensed list).

## N8. Campus sites and programmes need a check by students

**Status:** open · **Related:** `config/campus.yaml`, V3

The programme → site table and the site coordinates are drafts from general knowledge (the site
of Data Science / Machine Learning is a placeholder). **To do:** the team checks the whole file
against the university's own information (S1.6); the pipeline checks that
every site matches an OSM feature within a tolerance and is routable (V3).

## N9. OSM edits only by hand

**Status:** rule · **Origin:** archive `osm_tagging.md` §6, V2

Gaps found in validation (missing climbing gym, untagged Mensa) can be fixed in OSM by a team
member who knows the place, one feature at a time, following the automated-edits code of conduct.
Never copy lists from websites without a compatible licence. Changes reach the pipeline with the
next Geofabrik extract and `make refresh`.

## N10. Geofabrik moved the Regierungsbezirk extracts

**Status:** settled (21 Nov 2026) · **Related:** `config/config.yaml` `sources.osm`, acquire

The extract URL `…/baden-wuerttemberg/tuebingen-regbez-latest.osm.pbf` redirects to a 404 since
Geofabrik moved the Regierungsbezirk extracts into subfolders. The config now uses
`…/baden-wuerttemberg/tuebingen-regbez/tuebingen-regbez-latest.osm.pbf` (and `.md5`), checked on
21 Nov 2026. If acquire fails with HTTP 404 again, look up the current path on the Geofabrik index
page and update `sources.osm` (never fall back to Overpass, AGENTS.md rule 8).

## N11. validate peaks at ~2.6 GB during the OSM clip

**Status:** open · **Related:** A4, D1, N1

On the test clip (21 Nov 2026, M4 Pro) `validate` reached a peak RSS of 2,580 MB; it comes from
`osmium extract` over the regional PBF (memory grows with the highest node id, not the file
size). The whole test-clip refresh took 35 s. On 23 Nov 2026 (same machine, fresh downloads)
`validate` peaked at **3,629 MB** on the test clip and **3,778 MB** with `config/config.yaml`
(whole city): the peak varies by about 1 GB between runs and barely depends on the area, so plan
with ~4 GB for this stage. **To do:** measure the city run on the server
(S1.11) and keep the stage sequential with Valhalla and the transit engine (A4).

## N12. The preview environment's Cloudflare token is usable from every branch

**Status:** accepted (22 Nov 2026) · **Related:** docs/deployment.md, `ci.yml` `preview`

PR previews need `CLOUDFLARE_API_TOKEN` in the GitHub environment `preview`, which has no branch
restriction. A workflow edited on any branch of this repository can read it, and the token can
also deploy the production Worker. Fork PRs get no secrets. Accepted for a three-person team with
write access; alternatives if that changes: required reviewers on `preview` (blocks every preview)
or Cloudflare's Git integration instead of the token.

## N13. The first Cloudflare preview may need an existing Worker

**Status:** open · **Related:** S0.5, S0.6

`wrangler preview` creates a Preview "under the same Worker". Whether it creates the Worker
`reach` when it does not exist yet is not documented. If the first PR preview fails with a
"not found" error, a team member creates the Worker in the dashboard (Workers & Pages → Create →
Hello World, name `reach`); the v0.1.0 deploy then replaces its content.


## N14. The naldo GTFS feed ends on 12 Dec 2026

**Status:** open · **Related:** S1.6, S1.11, V3, risk "feed expiring"

The feed downloaded on 23 Nov 2026 from the URL in `config/config.yaml` has
`feed_end_date` 20261212 (`feed_info.txt`, version 20261011); the last `calendar.txt` end date is
the same. After 12 Dec no reference date per trip window can be found, so V3 fails and the first
production data and v0.2.0 (target 14 Dec) need a newer feed. **To do:** check early December
whether NVBW has published the timetable from 13 Dec 2026; if not, decide how to label or pin an
older feed before S1.11. First seen in the T1 spike (PR #79).

## N16. Product v1.1 needs follow-ups in methodology, architecture and the API proposal

**Status:** open · **Related:** `docs/product.md` v1.1, M1, M4, M7, S1.4, O-decisions on the Juju
docs stack (PRs #83–#86)

Product v1.1 (24 Nov 2026) replaces U1–U3 with the modes *Find* and *Check*, opens on a map with a
default profile instead of an onboarding questionnaire, takes rent as a per-listing input and puts
English first. `methodology.md`, `architecture.md` and `data_contract.md` were left unchanged in
that branch, because they need an explicit yes (AGENTS.md) and are being rewritten on the Juju
docs stack, which is not in `dev` yet. **To do** when the stack reaches `dev`:

1. `POST /api/fit`: make `programme` optional; without it the API uses the default campus mix.
   **Open:** which sites, which weights (equal, or by number of students).
2. Wording: "onboarding" → "profile panel" (methodology §6 step 1, M7; data contract
   `destination_types`), "U2" → "*Check*" (methodology §2, architecture §3 and §5, data contract
   live route), "U1–U3" → "*Find* and *Check*".
3. Rank in the city ("better than 80 % of places for your profile"): computed in the browser from
   the cell fits `POST /api/fit` already returns; decide whether against populated cells only or
   also address cells.
4. Rent: the listing rent stays in the browser and never enters the fit (M4 settled that way).
   **Open:** keep the Zensus rent grid as a reference in *Check* ("average here: €11/m², without
   student halls", N7) or drop the source `zensus_rent`, the column `cells.rent_eur_m2` and its
   validation.


## N17. The web app needs five additions to the S1.4 API proposal (for Juju)

**Status:** open, used as PROPOSED in the web fixtures · **Related:** S1.4, S1.10, N16,
`docs/app_screens.md` §9, `web/src/api/types.ts`

The app of S2.2–S2.6 is built against the S1.4 proposal on `docs/juju-fit-formula`. Where it
needed more, the fixtures (`web/src/api/fixtures/`) answer with the shapes below, marked PROPOSED
in `web/src/api/types.ts`. Neither `data_contract.md` nor Juju's branches are changed; when the
API is built, take, change or reject each point and the app follows.

1. **Data date and trip windows: `GET /api/meta`** → `{run_id, sources: [{source, date,
   valid_to?}], trip_windows: [{trip_window, weekday, time, kind, direction, reference_date}],
   bounds: [[w, s], [e, n]], modes: [mode]}`. Every result block shows the data date; every time
   shows its trip window (product: "every number can be explained").
2. **Populated flag per cell:** `cells` in `POST /api/fit` as `{cell_id: [fit, weekly_min,
   populated]}` (`populated` 1/0), so the browser computes the rank in the city against populated
   cells only (A1, N16 point 3). Cells with no fit carry `null`.
3. **Address search via POST:** `POST /api/addresses/search {q}` instead of
   `GET /api/addresses?q=`, so a listing address never lands in an access log (rule 9).
4. **`programme` optional** in `POST /api/fit` and `POST /api/cell/{id}`: absent or null = the
   default campus mix `campus.default_mix` in `config/campus.yaml` (Tal + Morgenstelle, equal;
   decided 24 Nov 2026). `GET /api/campus-sites` adds `default_share` per site, so the app can
   say which sites the mix uses.
5. **Lists the app shows:** `GET /api/programmes` → `[{programme, label: {en, de}, sites}]` and
   `GET /api/personas` → `[{persona, label: {en, de}, profile}]` (from `config/campus.yaml` and
   `config/personas.yaml`). Without them the app would have to copy YAML into the bundle.

6. **Destination labels (F2.5, extension plan; added 27 Nov 2026):** `GET /api/destination-types`
   adds `labels: [{label, kind: brand|group|category, name: {en, de}, destinations}]`; the fit
   profile adds `labels: {grocery: [label]}` (favourite supermarkets: the grocery term is the
   nearest of the chosen brands and groups, QF3) and takes sport and hobby categories as their own
   keys in `destinations` (`"sport:tennis": {importance, fine_time_min}`, never in the weekly time,
   QF4); `sport` and `hobby` are containers and never a term themselves. `GET
   /api/label-destinations` → `[{destination_id, destination_type, labels, name, point}]` draws
   the chosen places on the map. The fixtures replace `gym`, `climbing`, `swimming`,
   `sports_club` and `music` with `sport`/`hobby` categories (methodology v1.3-draft §3);
   `config/personas.yaml` still uses the old types until S1.6 changes `destination_types`.

Also used by *Check*, smaller: `POST /api/cell/{id}` adds `weekly_min`, `populated` and
`fit_parts: [{destination_type, minutes, mode, score, weight, share}]` (share of the fit per
destination for the trips table), and `legs` of a transit trip carry `first_stop`, `first_route`,
`walk_only` and, in the night window, `last_departure`. The fixture fit follows the methodology §6
proposal (0.9 at the fine time, 0.1 at twice the fine time); it imitates the API and is never used
with a real API.

## N18. Basemap (D5): self-hosted vector tiles — proposal for a new O-decision

**Status:** implemented for the demo on 27 Nov 2026 as a self-hosted GeoJSON; the O-number and
Rico's yes for the vector-tile build are still open ·
**Related:** D5, A6, `docs/app_screens.md` §5.1, decided in principle 24 Nov 2026

**Demo implementation (27 Nov 2026, Juju's request):** `web/public/basemap/` ships a 4.5 MB
simplified GeoJSON of roads, water, green spaces and rail (21,017 features) from the 27 Nov OSM
extract, plus a hand-written monochrome MapLibre style; `MapView` loads `/basemap/style.json` when
`VITE_BASEMAP_STYLE` is empty. No tile host, no glyphs, no new npm package; the file is public OSM
data, not pipeline data. Limits: no buildings, footpaths or labels, one file for the city instead
of tiles. The vector-tile build below stays the production target.

**Proposal (O-number on acceptance):** The basemap is a vector-tile extract of public
OpenStreetMap data for the routing area (z ≤ 15), built in CI from a public Protomaps build and
served from **our own origin** with the frontend, with a small hand-written style and self-hosted
glyphs (Noto Sans, OFL). No tile host, font CDN or other third party sees a request from the
student (A6). **Narrow exception** to "data never passes through GitHub or Cloudflare": it covers
only public OSM basemap tiles, built in CI, without any user data; pipeline data stays on the
server as before.

**Checked on 24 Nov 2026 (Cloudflare docs):**
- Workers Static Assets: at most **25 MiB per file**, **20,000 files** per Worker version on the
  free plan (100,000 paid). Requests to static assets are free.
- Static assets **do not answer HTTP Range requests**: a `Range` request gets `200` with the full
  file, no `206` (developers.cloudflare.com/workers/static-assets/billing-and-limitations/). A
  single `.pmtiles` file read by the `pmtiles` library therefore does not work from `dist/`.

**Consequence:** ship the extract **unpacked as `tiles/{z}/{x}/{y}.pbf`** files (expected a few
thousand files for Tübingen at z ≤ 15, below the 20,000 limit; size to be measured when the
extract is built), so no Range requests and no `pmtiles` package are needed. Alternatives: a Worker
with `run_worker_first` that cuts byte ranges (adds a Worker script; web/AGENTS.md forbids that
today), or R2 (another service). Until then the app shows a plain background
(`VITE_BASEMAP_STYLE` empty); `maplibre-gl` 6.19.0 is installed, `pmtiles` is **not**, because it
would be unused.

## N19. With the default profile the proposed fit hardly separates central areas

**Status:** observation on sample data, for the fit discussion (methodology §6, M1) ·
**Related:** S2.3, N17

On the web fixtures (modelled times, not routed) the default profile (no programme, walk + bike +
bus, campus very important, Mensa, supermarket and station important) gives area fits between
83 and 100; seven of ten areas score 97–100, so the *Find* map is almost one colour. Personas with
fewer modes spread much more (Lena, walk + bus: 52–98). Cause: with all modes the fastest mode is
usually the bike, and the proposal scores 0.9 at the fine time, so short trips saturate. To check
on real times in S1.10: whether the map needs a relative colour scale next to the absolute fit, or
whether the default fine times are too generous.

## N20. Daily WG-Gesucht crawl: permission pending, legal risk accepted for now

**Status:** decided 27 Nov 2026 (Juju: the crawl is allowed for the academic project; run it at a
low rate with the data minimisation of O24; the request of appendix A is still worth sending) · **Related:** architecture O24, methodology §8.1, `docs/extension_plan.md` §1 C1,
appendix A

The team chose the daily server crawl (QF1 = A, Juju, 26 Nov 2026). The WG-Gesucht AGB (read 26 Nov
2026) say in §7 (12) "Eine Vervielfältigung der Angebote des Internetportals ist nur mit vorheriger
Zustimmung der SMP GmbH & Co. KG gestattet" and protect the "gesamte Daten- und Datenbankstruktur"
(§8 (4)); systematic extraction is also covered by the database right (§ 87b UrhG); photos belong to
the uploaders; listings carry personal data of third parties. `robots.txt` does not disallow the
listing pages. **To do:** send the request of appendix A before the crawl runs in production and
record the answer here; keep the data minimisation of O24; keep `listings.enabled` switchable so the
app works without listings; if SMP refuses, switch the crawl off and fall back to the import in
the student's browser (extension plan F4.3). `product.md` v1.2 (26 Nov 2026) replaced the non-goal
"no scraping of listing sites" by data limits (no contact data, no photo copies, WG-Gesucht only).

**Requests so far (27 Nov 2026, Juju's go "scrape it with a low rate"):** for the parser fixtures
(F4.2) 9 pages were fetched by hand: 3 search pages (WG rooms, 1-room flats, flats) and 6 ads, at
least 20 s apart, with a generic user agent, no login, `robots.txt` read first (listing pages not
disallowed). Raw pages stay in `data/listings_raw/` on Juju's machine (git-ignored); the committed
fixtures are reduced and anonymised (`pipeline/tests/fixtures/listings/README.md`). No crawl runs
until the permission is recorded here.

## N21. Alma was not reachable from outside the university network

**Status:** open · **Related:** architecture O23, §4, extension plan F3.1

On 26 Nov 2026 `alma.uni-tuebingen.de` refused connections from outside (connection refused on
443); the university says the public course catalogue needs no login. **To do (F3.1):** test from
eduroam/VPN and from the server of D1; if the server cannot reach Alma, run the semester crawl from
a team machine inside the network and hand the raw pages to `acquire` as a file source, or ask the
university for an export (extension plan appendix B).

## N22. AGENTS.md rule 6 needs the listings writer

**Status:** settled 26 Nov 2026 (Juju's yes; rule 6 extended) · **Related:** architecture O7, O24

AGENTS.md architecture rule 6 says "Only `publish` writes results to PostGIS". With O24,
`publish_listings` writes the `lst_<id>` schemas and the `listings` views. **To do:** extend rule 6
to "Only `publish` and `publish_listings` write …; the API reads only `current` and `listings`"
after the team's yes.

## N23. OSM gaps for sport, hobby and supermarket labels

**Status:** open · **Related:** methodology §3.1, `docs/osm_tagging.md` §5, V10, N9

Measured 26 Nov 2026 on the routing-area extract (F2.1):

- **Under-mapped indoor sports:** yoga 3, martial arts 3, squash/badminton 2, rowing 1
  destination(s); clubs that train in school halls are rarely mapped. These categories are offered
  ("everything in") without a remark in the app (Juju, 27 Nov 2026: "it is as it is").
- **Outdoor equipment counts as a place:** most `table_tennis` (55) and many `basketball` (53)
  and `chess` (6) destinations are tables, hoops and boards in parks and school yards, not clubs.
- **School pitches** usually carry no `access` tag and count as public.
- **Supermarkets in `other`:** Bonus (2), Emmiy, Schmackes (Wanne) have no tag that tells their
  kind; 18 of 87 supermarkets have no `brand`.

**To do:** spot checks of V10 (10 supermarkets, 10 sport places); team members who know a place
may add `sport=*`, `organic=only` or `brand` by hand (N9); re-count in F2.2 on the current extract.

## N24. Alma: polite crawl of the day view decided; shares from one reference week

**Status:** decided 27 Nov 2026 (Juju: "als akademisches Projekt dürfen wir es"; another course
group crawled Alma before) · **Related:** N21, N23a (branch `docs/juju-alma-recon`), architecture
O23, methodology §3.2, extension plan F3.2–F3.4

Alma's `robots.txt` disallows all crawlers except Googlebot (N23a). Juju decided on 27 Nov 2026 that
the team crawls it anyway, politely: `python -m reach_pipeline.alma crawl` fetches the public day
view "Tagesaktuelle Veranstaltungen" (no login) for the weekdays of one reference teaching week
(`alma.reference_week`), two requests per day (`rate_limit_s` = 20 s apart), user agent naming the
course project, once per semester; pages are kept under `data/raw/alma/<semester>/`. One page holds
a whole day (≈ 1 150 sessions with title, time, module number, room and building). Lecturer names
are never parsed or stored outside the raw pages; committed fixtures are synthetic.

**Deviation from F3.1–F3.3 as planned:** instead of programme → module tree → courses, the
programme of a session comes from its **module number prefix** and the site from its **building
name**, both by patterns in `config/campus.yaml` (`alma.programme_numbers`,
`alma.building_sites`). `shares` sums the weekly session hours per programme × site. Sessions
without a number (≈ 45 %) or room do not count. This gives the sites and shares of the larger
programmes; humanities and social sciences have few prefixed numbers. Methodology §3.2 (shares
from course hours) is met in spirit; the module-tree path stays possible later. **To do:** decide
whether the API weights a programme's sites by these shares (data contract: a `shares` array next
to `programmes.sites`) or keeps equal weights; review the building patterns against the
"buildings without site" list the command logs.

## N25. Label destinations far outside the cells slow the transit routing

**Status:** open · **Related:** methodology §3.1, `stages/travel_times.py`, N23

The full-city run of 27 Nov 2026 routes every cell to the nearest sport/hobby category even when
that is far away, e.g. `sport:golf` (Golfclub Schönbuch, ≈ 5 km north of the last cell).
OpenTripPlanner cannot link that point to its street graph ("Couldn't link …" in the OTP log),
and each failed query takes about 1 s instead of 20 ms, so the transit step drops from ≈ 230 to
≈ 60 queries/s for a while. **To do:** in `travel_times`, query each destination point once
first and skip the points OTP cannot link (time = unreachable, counted in the result report); or
limit label destinations to the routing area minus a margin in `validate`.

## N26. Listings in the demo: cell fit, hotlinked photos, permission still open

**Status:** building block 27 Nov 2026 · **Related:** F4.4, F4.6, F4.7, architecture O24, notes N20, data contract *Listings*

A real crawl of the Tübingen WG-Gesucht search pages (one page per kind, 20 s between requests,
60 ads) ran on 27 Nov 2026: snapshot `data/listings/20261127T090214Z` (60 listings, 386 image links),
published as `lst_20261127t090214z`. A second attempt the same morning stopped after 18 minutes on
a captcha page of a detail ad and wrote no snapshot (the crawler stops on a block page, as
designed); the 09:02 UTC snapshot stays current. *Find* shows the listings behind the toggle with
the fit and weekly
time of the listing's **cell**, not of its point; F4.5 point routing is not built yet. 45 of the
60 fall into a populated cell, and `street`/`marker` geocodes are labelled "address approximate".
Images stay links to the source; some WG-Gesucht images answer 403 and the card then shows the
hatched placeholder. The SMP permission request (extension plan appendix A) is still not sent
(N20); the crawl stays local to the demo until it is.

## N27. Point routing (F4.5): warm latency, cold OTP, cell vs point

**Status:** done 27 Nov 2026 (Juju's task) · **Related:** F4.5, architecture O25, V11, data contract
`POST /api/place`

`POST /api/place` routes one point to the nearest k per weighted type and label and all campus
sites: walk and bike as one Valhalla matrix each, transit and bike + transit as one OTP query per
target and window (concurrency 4), transit capped by walking. The fit is derived from those times
with the same code as `/api/cell`; no cache (O25). The listing detail uses the point and falls back
to the cell if the engines fail; the list's fit stays the cell fit.

Measured on the local stack (27 Nov 2026, 11 targets, default profile): 0.22–0.26 s warm;
3.5 s on the first call after OTP started (graph warm-up). V11 on the same point: median difference
to the cell times 0 min, maximum 1 min; fit 99 vs 99, weekly 133 vs 137 min. Geocoding of listing
addresses moved to `listings/geocode.py` (house → street → marker) and still runs in the crawl; the
API takes the resulting point. The OTP client in `api/otp.py` is a small copy of
`reach_pipeline.otp` (the API image should not pull in DuckDB/GeoPandas); keep the two in sync or
extract a shared package later.

## N28. Routes and university outlines on the map

**Status:** demo 27 Nov 2026 · **Related:** F4.5, F4.7, F3.4, D5/N18

The listing detail asks `POST /api/route` for the fastest walk or bike trip of each destination
(four at most) and draws the Valhalla lines above the cells; transit trips have no geometry in the
API and stay in the table. Opening a listing flies the map to its point at zoom 14.5 and hides the
other WG markers. `university.geojson` (214 OSM footprints, 64 KB) outlines university buildings;
the selected programme's campus sites (default mix Tal + Morgenstelle) get the ink outline and a
stronger fill, the other sites a grey hairline. It is OSM data, not Alma: the Alma pipeline only
has site shares, no building geometry. The filter is `amenity=university`, `building=university`,
operator Universität Tübingen/Universitätsklinikum, or a campus name within 2.5 km of a site.

**Integration (27 Nov 2026):** *Find* no longer toggles between areas and WGs. The WGs are the
primary list (best fit first, top six, the best one opened below the list); the grid hides while a
WG is open, the routes and university outlines are visible, and the areas are a secondary,
collapsible section.

## N29. Wrong campus, unlabelled destinations and opening hours

**Status:** fixed 27 Nov 2026 (Juju: "es wird sehr oft zum falschen Campus geroutet, die Wege sind
unklar, da die POIs nicht angezeigt werden") · **Related:** F4.5, F4.7, F3.4, data contract v1.3.0

**Causes.** (1) The listing detail drew one route per destination type to the *fastest* trip; for
the campus that was the nearest of all four sites, so a biology student was routed to Sand or the
Tal. (2) `POST /api/place` routed to all campus sites, not only the student's. (3) The site points
were rough coordinates from S0.3: Tal, Sand and Schnarrenberg lay 250–300 m from the lecture
buildings (Morgenstelle 14 m). (4) The map showed lines but not where they end or what is there.
Also, label keys (`sport:tennis`) never showed a row in the listing trips (looked up by type).

**Fixes.** The API routes only the student's campus sites (`campus_weights`: campus days, else
programme with Alma shares, else default mix) and each trip carries `point` and, for campus sites,
`share`; the app shows every campus site of the student with its share and draws a route to each
of them; the trips' destinations are labelled markers on the map (name, minutes, mode; campus as
a square). Site points in `config/campus.yaml` now sit at the main lecture buildings (checked
against OSM); they take effect with the next full refresh, because `publish` now takes the campus
geometry from the run's `validate` output instead of re-reading `campus.yaml` (no half update).

**Opening hours.** `publish` writes `destination_details` from the OSM tags that `validate`
already exports (`opening_hours`, `website`/`contact:website`, `wheelchair`): 689 destinations of
run 20261127T080940Z, 429 with opening hours. `open_in_window` says whether the place is open at
the time of its type's trip window (e.g. supermarket on Tuesday 18:00); `opening_hours.py` reads
the common subset (91 % of the tagged values; PH/SH rules are ignored because reference dates are
never holidays) and leaves the rest unknown. **Google Maps was not scraped**: its terms forbid
extracting content, the data would be Google's, not ours to publish, and AGENTS.md rule 8 keeps
the app on OSM. If the team needs more (popular times, ratings), the paid Places API would be the
legal route (ask first: paid product, new service).

