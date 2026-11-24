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

