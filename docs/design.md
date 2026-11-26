# Design — reach web app

> **Status:** v0.1 draft (26 Nov 2026), step F1.1 of [`extension_plan.md`](extension_plan.md).
> Binding for the look of `web/` once the team has picked the type pairing from
> the prototype ([`design/prototype.html`](design/prototype.html)). Direction ***Atelier***
> (architecture O27, decision QF6 of 26 Nov 2026); light theme only, no dark mode for now.
> Screens, components and texts stay in [`app_screens.md`](app_screens.md); this file decides how
> they look.

## 1. Idea

reach is a tool for one decision, where to live. It should feel like a well-made label
in a garment: quiet, exact, and recognisable at a glance. The references are fashion houses whose
websites sell through restraint (Maison Margiela, Rick Owens, Yeezy). We take their principles and none of their material: no logos,
fonts, images, layouts or wording of a real brand.

| Reference | What we take | Where it shows in reach |
|---|---|---|
| Maison Margiela | white space; the blank white label; numbers as the only decoration | small labels with a hairline frame for mode, trip window and data date ("tags"); ranks and steps as plain numerals |
| Rick Owens | radical reduction; monumental type next to almost nothing | the fit set very large like a price; nothing competes with it |
| Yeezy | neutral ground, tiny type, images carry the page | listing photos on a light grey ground, data in small uppercase micro type |

Three sentences the design must make true:

1. **The numbers are the design.** Minutes, the fit and the rent are the largest, blackest things
   on screen; everything else steps back.
2. **Every mark means something.** A line separates, a number ranks or counts, a black block means
   "selected". Nothing is there to fill space.
3. **Calm under data.** Many numbers, one ink, lots of white.

## 2. Rules against the generic look (checked in review)

Each rule is checkable in a PR diff or a screenshot. A PR that breaks one says why in its
description.

| # | Rule | Check |
|---|---|---|
| R1 | No gradients, glass, blur, glow or drop shadows. Depth comes from 1 px hairlines and inversion. | no `gradient(`, `box-shadow`, `text-shadow`, `backdrop-filter`, `filter: blur` in `web/src` (map label halos excepted, §6) |
| R2 | Radius 0 everywhere. No pills, no rounded cards, no round icon buttons. | no `border-radius` other than `0` (the map pin is a square, §6) |
| R3 | No emoji, no icon library. Text labels first; at most five hand-drawn SVG glyphs: arrow, close, pin, plus, minus. | no emoji code points in `src/`; no icon package in `package.json` |
| R4 | No feature-card grids (icon + title + two lines), no centred hero, no marketing copy. | screenshot review |
| R5 | One ink plus greys. No brand accent colour. The only colours on screen come from listing photos; `--alert` only for error text. | colour tokens of §3 only; no other hex values in components |
| R6 | Left-aligned, asymmetric grid. The map is full-bleed; the panel is a column with a hairline, not a floating card. | screenshot review |
| R7 | Two families, two weights (400, 600), the type scale of §4 and nothing in between. Uppercase only for micro labels, always tracked. | font sizes only from tokens |
| R8 | Numbering only where order is information: ranks of areas and listings, steps of a flow, the order of reasons by weight. Never as decoration. | review |
| R9 | Motion only as 120–180 ms changes of opacity or position, linear or ease-out; nothing bounces, nothing loops. `prefers-reduced-motion` turns it off. | `transition` durations from tokens |
| R10 | Copy is short, declarative and factual: no exclamation marks, no "Discover", "seamless", "perfect", no questions as headings. | copy review (§7) |

## 3. Colour

| Token | Value | Use |
|---|---|---|
| `--paper` | `#FFFFFF` | page, panel, inputs |
| `--wash` | `#F1F1EF` | photo ground, hover, the map's land |
| `--ink` | `#111111` | text, numbers, hairlines that matter, selected blocks |
| `--grey-1` | `#555555` | secondary text (units, windows, sources) |
| `--grey-2` | `#666666` | micro labels, placeholders, disabled text |
| `--rule` | `#D4D4D2` | hairlines between rows and blocks (not text) |
| `--alert` | `#A4161A` | error text only, always with words ("Address not found") |

Measured WCAG contrast (26 Nov 2026, script in the F1.1 PR):

| Pair | Ratio | Level |
|---|---|---|
| ink on paper | 18.88 | AAA |
| ink on wash | 16.70 | AAA |
| grey-1 on paper / wash | 7.46 / 6.59 | AAA / AA |
| grey-2 on paper / wash | 5.74 / 5.08 | AA / AA |
| paper on ink (selected) | 18.88 | AAA |
| alert on paper | 7.75 | AAA |
| rule on paper | 1.48 | decorative only; never the only cue |

**Selected state** = ink block with paper text. **Focus** = 2 px ink outline with 2 px offset on
paper (18.88 : 1), never removed.

## 4. Typography

Two families: a neo-grotesk for text and a monospace for numbers and labels. The pairing is chosen
from the prototype:

| Pairing | Text | Numbers and labels | Cost | Licence |
|---|---|---|---|---|
| **A** | system stack: `"Helvetica Neue", Helvetica, Arial, sans-serif` | `ui-monospace, "SF Mono", Menlo, Consolas, monospace` | 0 bytes, looks slightly different per device | system fonts |
| **B** | Host Grotesk 400/600 | IBM Plex Mono 400/600 | ≈ 4 WOFF2 files, ≈ 120 KB **[VERIFY at download]**, self-hosted under `web/public/fonts/` | SIL OFL 1.1 (both) **[VERIFY licence files at download, F1.2]** |

Fonts are never loaded from a third-party host in the app (root rule 9); the prototype loads B from
Google Fonts only for the team review.

**Scale** (px; `rem` in code, 1 rem = 16 px):

| Token | Size / line height | Family | Use |
|---|---|---|---|
| `--t-micro` | 11 / 14, uppercase, tracking 0.08 em | mono | labels, tags, column heads |
| `--t-small` | 13 / 18 | text | secondary text, notes, sources |
| `--t-body` | 16 / 24 | text | running text, list items, inputs |
| `--t-title` | 24 / 28 | text 600 | place names, listing titles, section heads |
| `--t-figure` | 64 / 64, tabular | mono 400 | rent, minutes in the trips header |
| `--t-fit` | 160 / 140, tabular | mono 400 | the fit of a place or listing (96 on phones) |

Numbers always use tabular figures. Units are set in `--t-small` grey next to the number
("12 min", "€ 420"), never in the same size.

## 5. Space, grid and lines

- **Spacing tokens:** 4, 8, 12, 16, 24, 32, 48, 96 px (`--s-1` … `--s-8`). Sibling groups use
  `gap`, not margins.
- **Desktop (≥ 1024 px):** header 56 px with a bottom hairline; panel column 360 px on the left
  with a right hairline; map full-bleed in the rest; results column 400 px on the right, scrolling.
  The text starts on a 24 px left edge in every column.
- **Tablet (768–1023 px):** panel as a column, results below the map.
- **Phone (< 768 px):** header 48 px; map on top; bottom sheet with a top hairline and a 2 × 32 px
  grip in ink; tabs as text with an ink underline.
- **Lines:** 1 px `--rule` between rows; 1 px `--ink` under column heads and around tags; nothing
  thicker except focus.

## 6. Components

| Component | Look | Replaces (current `index.css`) |
|---|---|---|
| **Tag** | micro text in a 1 px ink frame, 2 × 6 px padding: `BIKE`, `TUE 08:10`, `OSM 24 NOV` | pill `.badge`, rounded `.chip` |
| **Big number** | fit or rent in `--t-fit` / `--t-figure`, unit and label in micro type above it | bold numbers inside cards |
| **Hairline table** | trips and listing parameters: mono column heads with an ink rule, rows with `--rule`, numbers right-aligned | `.card` lists |
| **Rank list** | areas and listings: numeral (rank), name in `--t-title`, fit right-aligned in mono, 2–4 reasons in `--t-small` | `.card` stack |
| **Text toggle** | options as words; the chosen one is an ink block with paper text; keyboard: arrow keys | pill `.mode-switch`, `.mode-tab` |
| **Field** | label in micro type; input with only a bottom hairline, 40 px high; focus = ink outline | rounded `.search-input`, `.field` |
| **Button** | primary: ink block, paper text, micro or body type, 40 px high, radius 0; secondary: text with an ink underline | pill `.btn`, `.btn-quiet` |
| **Notice** | a line of text with a micro label (`NOTE`, `SAMPLE DATA`, `ERROR` in `--alert`) and a hairline above; no coloured box | yellow `.hint`, `.note`, red banner |
| **Sheet / dialog** | paper panel with a 1 px ink border, no backdrop blur; backdrop `rgb(17 17 17 / 0.4)` | rounded dialog with shadow |
| **Photo** | listing photo on `--wash`, 4 : 3, no border, caption in micro type; loaded only when the listing is opened (architecture §10) | – |
| **Map pin** | 12 × 12 px ink square with a 2 px paper border; selected = 16 px with a number | teardrop `.pin` with shadow |

**Map** (MapLibre, self-hosted basemap per N18):

- Basemap in greys only: land `--wash`, water `#E2E2E0`, streets `#FFFFFF` with `#D4D4D2` casing,
  buildings `#E6E6E4`, labels `--grey-1` in the text family with a 1.5 px paper halo (the only halo
  allowed, R1).
- **Fit ramp** (7 steps, low → high fit): `#EFEFEF`, `#D2D2D2`, `#B0B0B0`, `#8C8C8C`, `#686868`,
  `#444444`, `#1C1C1C`, drawn at opacity 0.72 under the labels. Monochrome is colour-blind safe by
  construction; adjacent steps differ by 1.31–1.75 : 1 in luminance. Cells without a fit are
  hatched (45°, 1 px `--grey-2`, 6 px spacing) and named "no data" in the legend.
- **Legend:** seven squares in a row with `0` and `100` in micro type, no gradient bar.
- Destinations: 6 px ink dots; chosen favourites and categories: 8 px squares with a micro label.

## 7. Copy

English first, German second (`web/src/i18n/`). Short sentences, numbers first, no apologies.

| Instead of | Write |
|---|---|
| "Discover your perfect neighbourhood!" | "Where your trips are short." |
| "Oops! Something went wrong." | "The server did not answer. Your profile is kept; try again." |
| "Great choice! 🎉" | (nothing) |
| "Your fit score is 74/100, which is quite good" | "74" with the micro label `FIT` and "Better than 81 % of places for you." |
| "Reasons why this place is great" | "Why" |
| "Click here to apply" | "Draft a message" |

Labels name what students know ("Supermarkets", "Sport"), never system words ("destination
label", "weight vector").

## 8. Current patterns to replace (F1.2, F1.3)

Found in `web/src/index.css` on 26 Nov 2026; to be changed together with Rico, whose Phase 2
branches built them.

| Pattern | Where | Rule |
|---|---|---|
| `border-radius: 999px` | `.btn`, `.badge`, `.mode-switch`, `.mode-tab`, `.search-input`, `.chip`, `.map-hint` | R2 |
| `border-radius` 5–16 px | `.card`, `.note`, dialog, toast, legend, sheet, inputs | R2 |
| `--shadow` and `box-shadow` | header, cards, search list, toast, dialog, legend, pins, sheet | R1 |
| teal accent `--accent: #0b6b57` and `--accent-soft` | buttons, links, selected options | R5 |
| `conic-gradient` logo mark | `.logo-mark` | R1, R3 |
| viridis ramp and `linear-gradient` legend | `--fit-0` … `--fit-6`, `.legend-ramp` | R1, §6 map |
| teardrop pin with white border and shadow | `.pin` | R1, R2, §6 |
| yellow hint box with round icon | `.hint`, `.hint span`, `--warn-bg` | R2, R5, notice |
| `text-shadow` on map labels | cell labels | R1 (use a map halo) |
| `font-weight: 800` | `.logo`, `.pin span`, `.hint span` | R7 |

## 9. Accessibility

- Contrast of §3 holds for every text; text on the map always sits on paper or carries a paper
  halo.
- Focus is always visible (§3); keyboard paths of `app_screens.md` stay unchanged.
- No information by colour alone: ranks are numerals, the fit is a number, the ramp has a legend
  with values, errors carry words.
- Targets at least 40 × 40 px (44 on phones).
- axe without serious violations stays a CI check (S2.7).

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v0.1 draft | 2026-11-26 | Blackletter wordmark dropped (Juju); the wordmark is the word "reach" in the text family | Juju's review of the prototype |
| v0.1 draft | 2026-11-26 | First design system: idea and references, rules R1–R10, colour tokens with measured contrast, two type pairings, scale, grid, components, map style with monochrome fit ramp, copy, patterns to replace | F1.1, decision QF6 *Atelier* |
