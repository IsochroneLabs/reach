# AGENTS.md — slides

Rules for coding agents working in `slides/`. The root [`AGENTS.md`](../AGENTS.md) still applies
(branches, commits, ask first, docs in sync). The design rules below come from the mandatory
workshop *Presentation Skills* (Papies, 4 Nov 2026) and from `docs/notes.md` N13.

## What lives here

| Path | Content |
|---|---|
| `<deck>.tex` | One file per presentation or meeting (`interim.tex`, `final.tex` later, `YYYY-MM-DD-<topic>.tex` per supervisor meeting). Shown decks are frozen, see README "Versioning". `make slides` builds every `*.tex` here. |
| `common/beamerthemereach.sty` | The only theme: colours, fonts, header tracer, footer, `\source`, `\keyfigure`, `\classchip`, chart styles. |
| `common/facts.tex` | **Every number shown on a slide**, with the run or document it comes from. |
| `figures/*.tex` | TikZ figures as macros (`isochrone.tex`, `system.tex`), shared by all decks. |
| `build/` | latexmk output, git-ignored. |

## Content rules

1. **The docs are the source of truth.** Take statements from `docs/methodology.md`,
   `docs/architecture.md`, `docs/validation_report.md` and the run reports. If a slide would
   say something the docs do not, stop and ask; do not invent results, features or plans.
2. **Results only through `common/facts.tex`.** Never type a result into a deck: shares, counts,
   residents, cells and validation figures come from macros or chart tables there, each with a
   comment naming its source (run id, report, section). Method parameters fixed in
   `docs/methodology.md` (15 min, 3.39 km/h, $k_c$, number of categories and profiles) and
   experiment set-ups (150 cells, 90 instances) may be written directly. Exception: the backup
   table of V1–V11 quotes the summary of `docs/validation_report.md` directly, with a source line.
   Updating to a newer run means updating the whole block and the run id together.
3. **Name profile and budget next to every share** ("43 % … walking 3.39 km/h, 15 min"); shares
   change strongly with speed and budget (V5, notes N13).
4. **Every slide with a number has a `\source{…}` line** (run id or document section).
5. **Use the project vocabulary** of `docs/glossary.md` (cell, profile, class, deficit, zone, …).
6. English only. Mark planned things as planned; never present open work (V7, V9, hosting) as done.

## Storyline rules (workshop part 2)

1. **Write the titles first.** The frame titles, read in order, must tell the whole story; they
   are the executive summary. Keep the list of titles in `slides/README.md` in sync.
2. **Action titles:** a full sentence with the slide's key message, at most two lines
   ("More than four in ten residents cannot walk to a pharmacy within 15 minutes", not
   "Results"). Backup slides start with "Backup:".
3. **Pyramid:** key message first (slide 2), then supporting points that are mutually exclusive
   and collectively exhaustive; details go to backup slides after `\appendix`.
4. **One statement per slide, one slide per statement.**
5. Explain terms before they are used (e.g. the isochrone on slide 4, before the V1 result).

## Design rules (workshop parts 3 and 4)

1. Use the theme only: no local colours, fonts or `\setbeamer…` in a deck. Class colours
   (`lack`, `insufficient`, `sufficient`) equal `web/src/palette.ts`; change both together.
2. **No animations:** no `\pause`, `\only`, `\uncover` or overlay specifications.
3. Smallest body text `\footnotesize` on main slides; `\scriptsize` only for side notes and
   backup tables; `\tiny` only for the source line, figure labels and captions.
   No overfull boxes: the build log must not contain `Overfull`.
4. Charts: horizontal bars for rankings (sorted), years left to right, proportional scales
   starting at 0, no 3D, round to whole percent unless the decimal matters, units in the axis
   label. Use the `reach ranking` / `reach legend` pgfplots styles.
5. Figures as TikZ/pgfplots (vector, reviewable in diffs). Raster images (app screenshots) go to
   `figures/` as PNG under 1 MB each; never data files.
6. Slides are numbered (theme); start the backup with `\backupslides` (numbered B1, B2, …, not
   counted in the total).
7. Mark the speaker of each section with a `% Speaker:` comment (team decision T3).

## How to verify

```bash
make slides DECK=interim                       # or `make slides` for every deck
grep -c Overfull slides/build/interim.log      # must print 0
pdftoppm -r 90 -png slides/build/interim.pdf /tmp/slides   # look at every page
```

Look at the rendered pages before reporting: text must not run into the source line or the
footer, labels must not cover markers. Report the page count and anything you could not fix.

## Ask first

- A new deck, a change of the theme's look, or a new LaTeX package (it must be in TeX Live).
- Any content that is not backed by the docs or a run report.
