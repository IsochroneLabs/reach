# Slides

LaTeX (beamer) slides for the DS500 presentations. Rules for writing them (also for coding
agents): [`AGENTS.md`](AGENTS.md).

| Deck | Date | Status |
|---|---|---|
| `interim.tex` | 25 Nov 2026, interim presentation | draft (speakers and screenshots open) |
| `final.tex` | 29 Jan 2027, final presentation (slides due 28 Jan, 20:00) | *planned* |

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

**Open dependency:** the current numbers come from run `20261110T223016Z`, which has seven
categories (parks and playgrounds separate). That split is in PR #57 (`feature/juju-categories`)
and not yet on `dev`, where parks and playgrounds are one category. Merge #57 first, or switch
the deck to a `dev` run with six categories.

## Checklist before presenting (workshop)

- Do the titles alone tell the story? Is the key message on slide 2?
- Does every number have a source line, and every share its profile and budget?
- Is each speaker's part marked (`% Speaker:`) and rehearsed within the time limit?
- Backup slides for the expected questions (OSM completeness, wheelchair limits, recommender
  scope)? Screenshots for the demo in case the network fails?
