# Product — reach

> **Status:** v1.1 draft (24 Nov 2026). Binding for who the product is for and what it does.
> Everything else (architecture, methodology, app) is designed from this page.
> v1.1 replaces the use cases U1–U3 with two modes (*Find*, *Check*), drops the onboarding
> questionnaire for a map with defaults, moves rent to a per-listing input and makes English the
> primary language (team decisions E1–E5 of 24 Nov 2026, change log at the end).

reach helps students who are new to Tübingen decide where to live, based on what matters to them:
their campus, their hobbies, their way of getting around. In *Find* mode it shows which parts of
the city fit their preferences best, so they know where to look for a room; in *Check* mode it
scores a specific flat's location and compares it with others. Every score is explained with the
actual travel times on foot, by bike and by bus, at the times the student really travels.

## User

Students moving to Tübingen who do not know the city: first-semester students, master's students
and exchange students. They look for a room (often a WG) from far away or in a hurry, compare
listings in districts whose names mean nothing to them, and do not know the hills, the bus
network or where the campus sites are. There is no second user group.

Not users: long-time residents, commuters from the region, families, city planners.

## The questions they have

1. "How long to my campus for the first lecture, and is the bus reliable at that time?"
2. "Can I get home at night after going out?"
3. "Where are the places for my sport or hobby?"
4. "Is grocery shopping, the Mensa, a doctor, the station for trips home easy?"
5. "Bike or bus? Tübingen is hilly."
6. "Is this flat worth its rent compared with the other one?" (rent entered by the student)

Every feature must help answer one of these. A feature that does not is out of scope.

## Product line: one profile, two modes

Both modes use the same student profile and the same fit. The profile starts with defaults and is
edited live next to the map; every change recolours the map at once.

| Mode | Replaces | Situation | Input | Result | Decision it supports |
|---|---|---|---|---|---|
| **Find** | U1 | No flat in view yet, often not in Tübingen | Student profile | Map of cell fits; the three best areas, each with 2–4 reasons, e.g. "Morgenstelle 12 min by bus at 8:00, climbing gym 8 min by bike, last bus home after midnight" | Where to apply for rooms |
| **Check** | U2 + U3 | A listing (WG-Gesucht, Kleinanzeigen, …) before writing or visiting | Address search or pin, up to three places; optional rent per listing; same profile | Per place: fit 0–100, its rank in the city for this profile, trips per destination by mode and trip window, weekly travel time; for 2–3 places side by side with the differences in plain language, including rent ("Flat 2 costs €80 more per month but saves 25 min on the bus per week") | Whether to write to a listing; which of two or three to take |

**Transitions:** clicking an area in *Find* opens *Check* at that point; *Check* links to
"better places for you nearby" in *Find*.

**Cut order** if time runs short: (1) bike + transit as a fourth mode, (2) rent input in
*Check*, (3) comparing several places in *Check*. *Find*, *Check* for one place and the automatic
deployment are never cut.

## Entry: the map with defaults

There is no questionnaire and no question before the first result. The app opens on the map of
*Find* with the default profile; the search field for *Check* is in the header.

- **Profile panel** next to the map (bottom sheet on mobile). It holds the preferences below and
  the personas as "example profiles".
- **Programme first:** while no programme is chosen, the programme field is highlighted at the top
  of the panel ("Select your programme for results that fit you"). It is a hint, not a gate.
- **Default campus:** without a programme the fit uses a mix of the central campus sites
  **[OPEN]** (which sites, which weights; notes N16).

| # | Preference | Choice | Default |
|---|---|---|---|
| 1 | Programme | list → campus site(s) (`config/campus.yaml`) | none; default campus mix |
| 2 | Getting around | walk, bike, bus (multi-select; bike + bus if available) | all |
| 3 | Destinations | Mensa, grocery, main station, library, climbing, gym, swimming, sports club, going out, culture, place of worship, doctor, … | Mensa, grocery, main station |
| 4 | Importance per destination | not important / nice / important / very important | campus very important, others important |
| 5 | Trips per week | per destination | per destination type (`config/config.yaml`) |
| 6 | Fine time | slider per destination | per destination type (`config/config.yaml`) |
| 7 | Times of day | from the destination type's trip window | from `config/config.yaml` |

Rent is not part of the profile; it is entered per listing in *Check*.

## How results are shown

- **Fit 0–100** large; below it the rank in the city ("better than 80 % of places for your
  profile"); below that each destination with its travel time and its share of the fit; the
  weekly travel time as the second, intuitive number.
- **Find** colours the 100 m cells and ranks areas (districts and Teilorte) with reasons.
- **Check** compares up to three places; they are kept in the URL, so a comparison can be shared.
- **Rent** typed in by the student is shown and compared with travel time; it never enters the fit.

## Non-goals

No city-planning view, no facility recommender, no fixed time threshold ("15 minutes"), no car
mode, no user accounts, no scraping of listing sites, no tracking or analytics, no live delay
data. Nothing personal is stored on a server: the student profile and the rents typed in live in
the browser (URL and `localStorage`), so they can be shared as a link and are gone when the user
clears them.

## Quality goals

- Mobile-first; English first, German second; accessible contrast (axe without serious
  violations).
- A first result without any input: the map with defaults appears on load.
- An answer in under a second for the whole city (fit request < 500 ms on the server).
- Every number on screen can be explained: data date, trip window, mode and source are shown next
  to it; uncertain or missing values are labelled, never hidden.

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v1.1-draft | 2026-11-24 | Two modes *Find* (was U1) and *Check* (was U2 + U3); map with defaults and a profile panel instead of the onboarding questionnaire; rent entered per listing in *Check*, never in the fit; English first; non-users named; cut order adapted | Team decisions E1–E5 of 24 Nov 2026 (Rico) |
| v1.0-draft | 2026-11-21 | Product for the student rebuild: user, questions, U1–U3, non-goals, onboarding draft | Rebuild brief of 21 Nov 2026 |
