# Slides

LaTeX (beamer) slides for the DS500 presentations. Rules for writing them (also for coding
agents): [`AGENTS.md`](AGENTS.md).

| Deck | Date | Status |
|---|---|---|
| `2026-11-12-supervisor.tex` | 12 Nov 2026, supervisor meeting: state of `dev`, decisions (recorded and implicit), open questions, outlook to all of Germany | draft for the meeting |
| `interim.tex` | 25 Nov 2026, interim presentation | draft (speakers and screenshots open) |
| `final.tex` | 29 Jan 2027, final presentation (slides due 28 Jan, 20:00) | *planned* |

## Versioning

Every meeting with the supervisors gets its **own deck**, so all slides ever shown stay in git.

- **Name:** `YYYY-MM-DD-<topic>.tex` (date of the meeting), for example
  `2026-11-12-supervisor.tex`. The two course presentations keep `interim.tex` and `final.tex`.
- **Freeze after the meeting.** Do not edit a deck that has been shown. New decisions and new
  questions go into a new deck; copy slides you want to reuse and update them there.
- **Carry over:** start the next deck with the answers received (decisions) and what is still
  open, then add the new material. Mark proposals as proposals until the supervisors agree.
- **Numbers** always come from `common/facts.tex`; a new meeting appends its own block with the
  source of each number and does not change the old ones, so frozen decks still build the same.
- Add a row to the table above and a storyline table below (frame titles in order) for every
  new deck. `make slides` builds every deck; PDFs are build output (`slides/build/`, git-ignored)
  and can be recreated from any commit.

## Build

Requirements: a TeX Live distribution with `latexmk` (MacTeX on macOS,
`texlive-full` on Ubuntu; tested with TeX Live 2023). From the repository root:

```bash
make slides                 # every deck → slides/build/<deck>.pdf
make slides DECK=interim    # one deck
cd slides && latexmk -pvc interim.tex   # rebuild on every save
```

## Storyline of the interim deck

The frame titles are the executive summary (workshop: write the titles first). Keep this list in
sync with `interim.tex`.

| # | Section | Title (key message) |
|---|---|---|
| 1 | | Title |
| 2 | | reach shows who cannot reach everyday services within 15 minutes, and where a new facility would help most |
| 3 | Problem | The 15-minute city asks whether residents reach daily needs without a car; we make that question measurable and actionable for Tübingen |
| 4 | Problem | An isochrone shows every place you can reach from one point within a fixed time |
| 5 | Method | We measure all 1,699 populated 100 m cells (90,355 residents) for seven categories and four ways of travelling |
| 6 | Method | We count facilities along the network, because isochrone polygons would add 18 % unreachable cell–facility pairs |
| 7 | Method | Each cell gets a class per category, and a deficit that weighs missing access by residents |
| 8 | Results | More than four in ten residents cannot walk to a pharmacy within 15 minutes |
| 9 | Results | Faster walkers reach far more; pharmacy and grocery stay the weakest on foot and by wheelchair |
| 10 | Results | A greedy recommender picks the zone that removes the most unmet demand, close to the exact optimum |
| 11 | System | One command turns open data into validated, published results |
| 12 | System | Eleven experiments test the method, and the main design choices hold |
| 13 | System | Live demo: anyone can click a place and see what is missing within 15 minutes |
| 14 | Next steps | By the submission on 22 January we close the open validations and host the app |
| 15 | | Thank you. Questions? |
| B1–B3 | Backup | References and data sources · validation V1–V11 · architecture at runtime |

The isochrone (slide 4) is defined early on purpose: slide 6 reuses the same drawing to show why
counting with the polygon goes wrong (validation V1).

## Updating the numbers

All numbers come from [`common/facts.tex`](common/facts.tex): results from one run
(`data/runs/<run_id>/validate_results/report_results.md`), validation figures from
[`docs/validation_report.md`](../docs/validation_report.md). Before a presentation, update the
block to the run the app shows and rebuild.

**Runs:** the interim deck uses run `20261110T223016Z` (seven Core categories). PR #57 and #60
are merged; `dev` now publishes 15 categories (run `20261110T233930Z`, used by the deck of
12 Nov 2026). The seven Core shares are identical in both runs (same OSM snapshot).

## Checklist before presenting (workshop)

- Do the titles alone tell the story? Is the key message on slide 2?
- Does every number have a source line, and every share its profile and budget?
- Is each speaker's part marked (`% Speaker:`) and rehearsed within the time limit?
- Backup slides for the expected questions (OSM completeness, wheelchair limits, recommender
  scope)? Screenshots for the demo in case the network fails?

## Storyline of the deck of 12 Nov 2026 (supervisor meeting)

Numbers from run `20261110T233930Z` (block "supervisor meeting 12 Nov 2026" in `common/facts.tex`).
The Germany outlook (slides 23–25) is a vision of the team, marked as not planned.

| # | Section | Title (key message) |
|---|---|---|
| 1 | | Title |
| 2 | | reach runs end to end for Tübingen; today we explain the decisions behind it, ask four questions and sketch the way to all of Germany |
| 3 | Status | dev now measures 15 categories for every resident of Tübingen and publishes them in one validated run |
| 4 | Decisions | Every layer of reach rests on a deliberate choice; for each we can name the alternative we rejected |
| 5 | Decisions | We use only open data and read it from one snapshot per run, so every number can be traced and reproduced |
| 6 | Decisions | We keep the official Zensus 100 m grid instead of H3 hexagons, so every resident count stays exactly as published |
| 7 | Decisions | We score every resident of the city, but draw the city and place recommendations only where it is built up |
| 8 | Decisions | Valhalla is our only routing engine, self-hosted, so batch numbers and live answers always agree |
| 9 | Decisions | We count facilities along the network with a time matrix; isochrone polygons would add 18 % unreachable pairs |
| 10 | Decisions | We measure four ways of travelling, with a slow inclusive walking speed and Valhalla's slope model switched on |
| 11 | Decisions | Fifteen categories in six groups: seven Core ones follow the paper, eight extended ones are indicative |
| 12 | Decisions | Each cell gets a class per category and a deficit weighted by residents; the combined score is for display only |
| 13 | Decisions | The recommender is greedy because the objective allows it: within 2.8 % of the exact optimum in every test |
| 14 | Decisions | One command refreshes, validates and publishes a run atomically; a failed run never reaches the app |
| 15 | Decisions | We work docs first: binding documents with change logs, an owner per folder and reviewed pull requests |
| 16 | Open questions | Four questions need your answer; for each we bring a recommendation |
| 17 | Open questions | Question 1: should the frontend move to Cloudflare Pages? Socke's proposal is not approved |
| 18 | Open questions | Question 2: the ProDesk saves rent, a VPS saves operating effort; neither is chosen yet |
| 19 | Open questions | Question 3: Moran's I shows strong clusters between cells but none between districts; is this the adequate method? |
| 20 | Open questions | Question 4: five known limits remain; we propose to state them openly and fix only the cheap ones |
| 21 | Open questions | Smaller points: the interim format, database access and whether a larger area is of interest |
| 22 | Outlook | Until 22 January we finish Tübingen: close the validations, deploy, and deliver |
| 23 | Outlook | Our long-term goal is all of Germany, and the core choices already scale |
| 24 | Outlook | We would get there in three steps: the region we already download, Baden-Württemberg, then Germany |
| 25 | Outlook | Four problems decide whether Germany is feasible: compute, data quality, comparability and serving |
| 26 | Next steps | With your answers we record the decisions, finish Tübingen and keep the design open for more |
| 27 | | Thank you. Your decisions, please. |
| B1–B3 | Backup | Class shares of all 15 categories · cycling in the recommender · validation V1–V11 |
