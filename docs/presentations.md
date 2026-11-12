# Presentations

How we make the slides for the DS500 presentations and supervisor meetings. For the whole team
and for coding agents: read this before you touch `slides/`. The design rules come from the
mandatory workshop *Presentation Skills* (Papies, 4 Nov 2026) and from `docs/notes.md` N13.

## Purpose

Every presentation and every supervisor meeting gets its own deck, so all slides ever shown stay
in git, together with the numbers they showed and where those numbers came from.

## Folder layout

One folder per deck, named after the date it is shown and its topic (`YYYY-MM-DD-<topic>`). The
folder holds everything the deck needs, including its copy of the theme, so `pdflatex` in the
folder builds it with no paths or settings:

```text
slides/
  2026-11-12-supervisor/
    2026-11-12-supervisor.tex         the deck
    beamerthemereach.sty              this deck's copy of the theme
    facts.tex                         every number of this deck, each with its source
    figures/                          TikZ (.tex) and PNG used by this deck only
    2026-11-12-supervisor.pdf         rendered PDF, committed (the record of the deck)
    build/                            latexmk output, git-ignored (as are editor aux files)
  2026-11-25-interim/                 interim presentation, same structure
```

The final presentation will be `2027-01-29-final/` (slides due 28 Jan 2027, 20:00).

- **Theme:** `beamerthemereach.sty` holds colours, fonts, the header tracer, the footer,
  `\source`, `\keyfigure`, `\classchip` and the chart styles. Every deck has its own copy, so a
  frozen deck never changes when the look changes. A design change goes into the copy of every
  deck that is not frozen yet (and is copied on by `make slides-new`).
- **Facts:** `facts.tex` holds exactly the macros and chart tables its deck uses.
- **Figures:** a figure used by several decks is copied into each of them, so a frozen deck never
  changes when another deck does.
- **PDF:** `<deck>.pdf` is committed and must stay under 2 MB. All other build output goes to
  `build/`.

## Build

Requirements: TeX Live 2023 or newer with `latexmk` and the Fira fonts (MacTeX full, or BasicTeX
+ `sudo tlmgr install fira latexmk`). Without Fira the theme warns and falls back to Latin
Modern Sans; never present such a build.

**Editor** (TeXShop, TeXstudio, VS Code LaTeX Workshop, or `pdflatex` in the deck folder): open
any `.tex` of the deck and press *Typeset* (pdflatex, twice for the slide numbers). The main file
loads the theme from its own folder and the figures as `\input{figures/<name>}`, and
`facts.tex` and the figures carry
`% !TEX root`, so Typeset in a fragment compiles its deck. The editor writes the PDF next to the
deck: the same bytes as `make slides` (the theme takes the date and PDF ID from the deck name),
so `git status` stays clean. Its other files (aux, log, …) are git-ignored. If a build fails,
pdflatex deletes the PDF; restore it with `git restore slides/<deck>/<deck>.pdf`.

VS Code (LaTeX Workshop): the repo has no `.vscode/`; add this to your user or workspace settings:

```json
"latex-workshop.latex.tools": [{ "name": "pdflatex", "command": "pdflatex",
  "args": ["-synctex=1", "-interaction=nonstopmode", "-file-line-error", "%DOC%"] }],
"latex-workshop.latex.recipes": [{ "name": "pdflatex ×2", "tools": ["pdflatex", "pdflatex"] }],
"latex-workshop.latex.outDir": "%DIR%",
```

**Terminal** (the reference build), from the repository root:

```bash
make slides DECK=2026-11-25-interim    # one deck → slides/<deck>/<deck>.pdf (output in build/)
make slides                            # every deck; runs slides-check afterwards
make slides-check                      # fail if a log has "Overfull" or a LaTeX error ("!")
make slides-editor-check               # build every deck as an editor does (plain pdflatex x2,
                                       # no TEXINPUTS, temp dir) and check its log
make slides-clean                      # remove build/ and editor files; keeps the PDFs
make slides-new DECK=2026-12-03-supervisor FROM=2026-11-25-interim   # new deck, see below
pdftoppm -r 90 -png slides/2026-11-25-interim/2026-11-25-interim.pdf /tmp/slides  # every page
```

Look at every rendered page before reporting: text must not run into the source line or the
footer, labels must not cover markers. Report the page count and anything you could not fix.

## How to add a deck

1. `make slides-new DECK=<YYYY-MM-DD-topic> FROM=<previous deck>` copies the previous deck
   without PDF and build files, renames the main file and sets the `% !TEX root` lines and the
   title date. It refuses an existing deck or a name without a date.
2. Update `facts.tex` to the run the app shows (new run id; every number and its source line
   together) and remove macros the new deck does not use.
3. Start with the answers received in the last meeting (decisions) and what is still open, then
   add the new material. Mark proposals as proposals until the supervisors agree.
4. Write the frame titles first (storyline rules below), then the slides.
5. `make slides DECK=<deck>`, look at every page, commit the `.tex`, `facts.tex`, `figures/` and
   the PDF.

## Freeze rule

A deck that has been shown is frozen: do not edit its source, facts or figures. Its committed PDF
is the record of what was shown. New decisions and questions go into a new deck; copy slides you
want to reuse and update them there.

## Content rules

1. **The docs are the source of truth.** Take statements from `docs/methodology.md`,
   `docs/architecture.md`, `docs/validation_report.md` and the run reports
   (`data/runs/<run_id>/validate_results/report_results.md`). If a slide would say something the
   docs do not, stop and ask; do not invent results, features or plans.
2. **Results only through `facts.tex`.** Never type a result into a deck: shares, counts,
   residents, cells and validation figures come from macros or chart tables in the deck's
   `facts.tex`, each with a comment naming its source (run id, report, section). Method
   parameters fixed in `docs/methodology.md` (15 min, 3.39 km/h, $k_c$, number of categories and
   profiles) and experiment set-ups (150 cells, 90 instances) may be written directly. Exception:
   a backup table of V1–V11 may quote the summary of `docs/validation_report.md` directly, with a
   source line. Moving to a newer run means updating the whole block and the run id together.
3. **Name profile and budget next to every share** ("43 % … walking 3.39 km/h, 15 min"); shares
   change strongly with speed and budget (V5, notes N13).
4. **Every slide with a number has a `\source{…}` line** (run id or document section).
5. **Use the project vocabulary** of `docs/glossary.md` (cell, profile, class, deficit, zone, …).
6. English only. Mark planned things as planned; never present open work as done.

## Storyline rules (workshop part 2)

1. **Write the titles first.** The frame titles, read in order, tell the whole story; they are
   the executive summary. The `.tex` is the only list of them.
2. **Action titles:** a full sentence with the slide's key message, at most two lines
   ("More than four in ten residents cannot walk to a pharmacy within 15 minutes", not
   "Results"). Backup slides start with "Backup:".
3. **Pyramid:** key message first (slide 2), then supporting points that are mutually exclusive
   and collectively exhaustive; details go to backup slides after `\appendix`.
4. **One statement per slide, one slide per statement.**
5. Explain terms before they are used (e.g. the isochrone before the V1 result).

## Design rules (workshop parts 3 and 4)

1. Use the theme only: no local colours, fonts or `\setbeamer…` in a deck. Class colours
   (`lack`, `insufficient`, `sufficient`) equal `web/src/palette.ts`; change both together.
2. **No animations:** no `\pause`, `\only`, `\uncover` or overlay specifications.
3. Smallest body text `\footnotesize` on main slides; `\scriptsize` only for side notes and
   backup tables; `\tiny` only for the source line, figure labels and captions. No overfull
   boxes (`make slides-check`).
4. Charts: horizontal bars for rankings (sorted), years left to right, proportional scales
   starting at 0, no 3D, round to whole percent unless the decimal matters, units in the axis
   label. Use the `reach ranking` / `reach legend` pgfplots styles.
5. Figures as TikZ/pgfplots (vector, reviewable in diffs). Raster images (app screenshots) go to
   the deck's `figures/` as PNG under 1 MB each; never data files.
6. Slides are numbered (theme); start the backup with `\backupslides` (numbered B1, B2, …, not
   counted in the total).
7. Mark the speaker of each section with a `% Speaker:` comment (team decision T3).

## Checklist before presenting

- Do the titles alone tell the story? Is the key message on slide 2?
- Does every number have a source line, and every share its profile and budget?
- Is each speaker's part marked (`% Speaker:`) and rehearsed within the time limit?
- Backup slides for the expected questions (OSM completeness, wheelchair limits, recommender
  scope)? Screenshots for the demo in case the network fails?
- After the meeting: the PDF is committed and the deck is frozen.

## Ask first

- A new deck, a change of the theme's look, or a new LaTeX package (it must be in TeX Live).
- Any content that is not backed by the docs or a run report.
