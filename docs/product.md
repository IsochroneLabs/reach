# Product — reach

> **Status:** v1.0 draft (21 Nov 2026). Binding for who the product is for and what it does.
> Everything else (architecture, methodology, app) is designed from this page.

reach helps students who are new to Tübingen decide where to live, by showing how long their own
everyday trips take from each part of the city on foot, by bike (with hills) and by bus, and
explaining the differences in plain language.

## User

Students moving to Tübingen who do not know the city: first-semester students, master's students
and exchange students. They look for a room (often a WG) from far away or in a hurry, compare
listings in districts whose names mean nothing to them, and do not know the hills, the bus
network or where the campus sites are. There is no second user group.

## The questions they have

1. "How long to my campus for the first lecture, and is the bus reliable at that time?"
2. "Can I get home at night after going out?"
3. "Where are the places for my sport or hobby?"
4. "Is grocery shopping, the Mensa, a doctor, the station for trips home easy?"
5. "Bike or bus? Tübingen is hilly."
6. "What would it cost?" (only where a legal rent source exists)

Every feature must help answer one of these. A feature that does not is out of scope.

## Use cases

| # | Use case | Flow | Result |
|---|---|---|---|
| U1 | **Explore** | Answer a few questions (or pick a persona) → map | The areas that fit best, each with 2–4 reasons, e.g. "Morgenstelle 12 min by bus at 8:00, climbing gym 8 min by bike, last bus home after midnight" |
| U2 | **Check a place** | Address search or pin (e.g. a WG listing) | Their trips from there by walk, bike and bus, per trip window, with times, transit details and how well the place fits their profile |
| U3 | **Compare** | Two or three places | Trips and fit side by side, with the differences in plain language |

**Cut order** if time runs short: (1) bike + transit as a fourth mode, (2) budget/rent, (3) U3.
U1, U2 and the automatic deployment are never cut.

## Non-goals

No city-planning view, no facility recommender, no fixed time threshold ("15 minutes"), no car
mode, no user accounts, no scraping of listing sites, no tracking or analytics, no live delay
data. Nothing personal is stored on a server: the student profile lives in the browser (URL and
`localStorage`), so it can be shared as a link and is gone when the user clears it.

## Onboarding questions (draft)

Short, skippable, 5–7 questions; personas (`config/personas.yaml`) as a quick start. Wording is
tested with students in user-test round 1 (S2.0) before the screens are built.

| # | Question | Answer type | Feeds |
|---|---|---|---|
| 1 | What do you study? | programme list (→ campus sites, `config/campus.yaml`); "not sure yet" | campus destinations |
| 2 | How do you get around? | multi-select: walk, bike, bus (bike + bus if available) | allowed modes |
| 3 | What do you do in your free time? | multi-select: climbing, gym, swimming, team sport, music, going out, cinema/theatre, religious community, … | hobby destination types |
| 4 | How often do you go there? | per chosen item: times per week (default per type) | weekly travel time |
| 5 | What matters how much? | per destination type: not important / nice / important / very important | importance |
| 6 | What travel time feels fine? | per destination type a slider, default prefilled (e.g. 15 min to campus) | fine time |
| 7 | Budget (optional) | max. net cold rent per m² or skip | rent filter, only where data exists |

## Quality goals

- Mobile-first, German and English, accessible contrast (axe without serious violations).
- An answer in under a second for the whole city (fit request < 500 ms on the server).
- Every number on screen can be explained: data date, trip window, mode and source are shown next
  to it; uncertain or missing values are labelled, never hidden.
