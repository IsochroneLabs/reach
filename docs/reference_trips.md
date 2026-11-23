# Reference trips for V1

> **Status:** collection sheet ready (23 Nov 2026, plan S1.0). The team fills it **between 1 and
> 12 Dec 2026**; the filled sheet is committed as a fixture and used for V1 (methodology §10) in
> S1.11. Tests and the pipeline never query a journey planner (AGENTS.md rule 8).

## What and why

V1 compares reach's travel times with an external reference: **30 cell × destination pairs**, each
for walk, bike and transit (methodology V1 asks for ≥ 25 per mode). The result is the median and
the 90th-percentile deviation per mode, reported in `docs/validation.md`.

The sheet is [`pipeline/tests/fixtures/reference_trips.csv`](../pipeline/tests/fixtures/reference_trips.csv):
one row per pair, the left columns are fixed, the right columns are filled by hand.

## How the pairs were chosen

- **Origins:** for each district or Teilort used, its most populated Zensus 2022 cell (ties: lower
  `cell_id`), from the validated cell layer (1,699 populated cells, the same set the city run of
  23 Nov 2026 published). `cell_lon`/`cell_lat` is the cell's origin point; `cell_address` is the
  nearest OSM address with street and house number (≤ 330 m away), only as an entry for journey
  planners that do not take coordinates.
- **Destinations:** the campus sites, Mensas and university sports ground of `config/campus.yaml`
  (coordinates still [VERIFY], S1.6), Tübingen Hauptbahnhof (9.0558, 48.5158) and the Marktplatz
  (9.0569, 48.5203) as the nightlife point.
- **Spread:** 20 districts and Teilorte (centre, valleys, hills, outer villages), straight-line
  distance 0.9–7.6 km (median 2.6 km), every trip window of `config/config.yaml` and its typical
  destination type:

| Trip window | Pairs | Destination type | Date and time | Kind |
|---|---|---|---|---|
| `morning_lecture` | P01–P12 | campus site | Tue 15 Dec 2026, arrive by 08:10 | arrive-by |
| `midday` | P13–P16 | Mensa | Tue 15 Dec 2026, 12:00 | depart-at |
| `evening` | P17–P20 | university sports | Tue 15 Dec 2026, 18:00 | depart-at |
| `weekend_station` | P21–P26 | main station | Sat 19 Dec 2026, 10:00 | depart-at |
| `night_return` | P27–P30 | home, from the Marktplatz (`direction` = back) | Sat 19 Dec 2026, 00:30 (night Fri → Sat) | depart-at |

**Why these dates:** the naldo feed of today ends on 12 Dec 2026 (notes N14); the timetable from
13 Dec 2026 is the one the first production data (S1.11) will use. Tue 15 and Sat 19 Dec are normal
lecture/weekend days before the Christmas break (no public or school holiday). Journey planners
usually show the new timetable weeks ahead; if one does not yet, note it in `notes` and collect
again later.

## How to fill a row

For **`direction` = to**, the trip goes from the cell to the destination; for **back**, from the
destination (Marktplatz) to the cell.

| Column | What to enter |
|---|---|
| `walk_min` | Walking time in whole minutes from a routing website (e.g. Google Maps "walk", openstreetmap.org "foot") between the two coordinates, or a measured walk |
| `walk_source` | The site or `measured` (e.g. `google_maps`, `osm_graphhopper`, `measured`) |
| `bike_min` | Cycling time in whole minutes (e.g. Google Maps "bicycle", brouter-web "trekking"), or a measured ride; hills matter, so prefer a source that uses elevation |
| `bike_source` | As above |
| `transit_departure` | Time you **leave home** (HH:MM, from the planner's first walking leg), see below |
| `transit_arrival` | Time you **arrive** at the destination (HH:MM, after the last walking leg) |
| `transit_transfers` | Number of changes (0 for a direct bus) |
| `transit_first_route` | Line of the first bus or train, e.g. `5`, `N93`; `walk` if the planner suggests walking only |
| `transit_source` | `naldo` (naldo.de planner) or `db` (bahn.de / DB Navigator) |
| `collected_by`, `collected_on` | Your team name and the date (YYYY-MM-DD) |
| `notes` | Anything odd: address used instead of coordinates, new timetable not yet shown, planner offered a much faster option one minute later, … |

**Which connection to take (methodology §4, M6: the wait at home counts):**

- **depart-at** windows: set the planner to *departure* at the window time and take the connection
  that **arrives first**. reach's time is `transit_arrival − time`, so waiting at home for a later
  bus is included.
- **arrive-by** (`morning_lecture`): set the planner to *arrival* 08:10 and take the connection
  that **leaves home latest** and still arrives by 08:10. reach's time is
  `time − transit_departure`.
- `night_return` at 00:30 on Sat 19 Dec means the night **from Friday 18 to Saturday 19 Dec**.

Do not compute minutes for transit; the comparison code does that from the stored times.

## Who collects

| Pairs | Team member |
|---|---|
| P01–P10 | Rico |
| P11–P20 | Socke |
| P21–P30 | Juju |

Proposal; swap freely, but keep the `collected_by` column honest. Commit the filled rows on a
`data/<name>-reference-trips` branch, or send them to whoever commits; one PR at the end is fine.

## How V1 uses it (S1.11)

reach's times for the same pairs come from the published run: the cell's stored time to the
nearest matched destination, or a live route to exactly these coordinates where the matched OSM
feature differs (the comparison script states which). Transit is compared at the **same dates**
as the sheet (15 and 19 Dec 2026), so the V1 run pins its reference dates to them instead of
the automatic choice (methodology §5). Deviation = reach − reference, in minutes
and in percent, per mode; median and 90th percentile go into `docs/validation.md`.
