# OSM tagging guide — reach

> **Status:** v1.0 draft (21 Nov 2026), informative. Which OpenStreetMap tags define each
> destination type, and how the team improves the data in OSM. Binding definitions live in
> [`methodology.md`](methodology.md) §3 and `config/config.yaml`. Tag counts per type are measured
> in S1.6 and added here; counts quoted from the archive are marked.

reach reads OSM only from the Geofabrik extract (AGENTS.md rule 8). A destination counts only if
its tags match a destination type in the config, so the result is only as good as the tags.

## 1. How the pipeline reads tags

- `destination_types.<type>.tags` is a list of `key: value` pairs; a feature matching **any**
  pair belongs to the type (carried over from the archive's `facilities.match_categories`).
- Optional `require`: alternative conditions on further tags, at least one must hold (e.g.
  `sport=climbing`).
- Optional `exclude`: conditions that drop a feature (e.g. `access=private`).
- OSM values separated by `;` (`sport=climbing;bouldering`) match if any part matches.
- Polygons are represented by a point inside; parks by access points on their boundary.
- Campus sites, Mensa list and university sports come from `config/campus.yaml`, matched to OSM
  features by name and distance (V3).

## 2. Destination types

| Type | Defining tags | Refinements and rules | Notes |
|---|---|---|---|
| `campus_site` | – (`config/campus.yaml`) | matched to `amenity=university` / building names | team-checked table (notes N8) |
| `mensa` | – (`config/campus.yaml`) | matched to OSM by name; tagging in OSM varies (`amenity=canteen`, `restaurant`, `fast_food`) | check in S1.6 |
| `library` | `amenity=library` | university and institute libraries count (open to everybody) | archive: 30 in the routing area |
| `university_sports` | – (`config/campus.yaml`) | Hochschulsport sites | |
| `grocery` | `shop=supermarket` | incl. discounters and organic supermarkets; not `convenience`, `kiosk` | archive: 60 |
| `pharmacy` | `amenity=pharmacy` | drugstores (`shop=chemist`) are not pharmacies | archive: 30 |
| `doctor` | `amenity=doctors` | `healthcare:speciality=general` preferred where tagged (35 of 164 practices untagged in the archive run) | GP-only filter decided in S1.6 |
| `main_station` | `railway=station` + name Tübingen Hbf | or the GTFS stop of the main station | one destination |
| `park` | `leisure=park` | exclude `access` = `private`, `no`, `customers`; access points where paths cross the boundary | archive: 88 |
| `gym` | `leisure=fitness_centre` | yoga studios are tagged this way too | archive: 12 |
| `climbing` | `leisure=sports_centre`, `leisure=pitch` | require `sport` = `climbing` (incl. bouldering) | [VERIFY] counts |
| `swimming` | `leisure=sports_centre`, `leisure=water_park`, `leisure=swimming_pool` | require `sport=swimming` or a public pool: exclude `access` = `private`, `no`, `customers`; garden pools excluded | [VERIFY] counts |
| `sports_club` | `leisure=sports_centre` | exclude non-public `access` | archive: 75, unfiltered by sport |
| `music` | `amenity=music_school`, `amenity=music_venue` | | [VERIFY] counts |
| `nightlife` | `amenity=bar`, `amenity=pub`, `amenity=nightclub`, `amenity=biergarten` | | used with the night window |
| `cinema_theatre` | `amenity=cinema`, `amenity=theatre` | | |
| `place_of_worship` | `amenity=place_of_worship` | the student picks a `religion=*` (and optionally `denomination=*`) | [VERIFY] tag completeness |

## 3. Access: public or not

| Types | Excluded `access` values | Why |
|---|---|---|
| park, sports_club, swimming, climbing | `private`, `no`, `customers` | must be usable by the public |
| grocery, pharmacy, doctor, gym, nightlife | none | `customers` is normal for shops and businesses |

Validation reports the number of excluded features per type and value.

## 4. How we edit OSM

1. Personal OSM account; edit in iD or JOSM; follow the
   [Automated edits code of conduct](https://wiki.openstreetmap.org/wiki/Automated_edits_code_of_conduct):
   by hand, one feature at a time, no scripts or imports.
2. Only what you know or can see (survey, local knowledge); never copy from websites or lists
   without a compatible licence.
3. Small themed changesets with a clear comment, e.g. `Tübingen: add sport=climbing to bouldering gym`.
4. Find gaps with an Overpass query (for people, never for the pipeline), e.g. sports centres
   without `sport` in the city:

   ```text
   [out:json][timeout:60];
   area["de:amtlicher_gemeindeschluessel"="08416041"]->.city;
   nwr["leisure"="sports_centre"]["sport"!~"."](area.city);
   out center tags;
   ```

5. The change reaches reach with the next Geofabrik extract (daily) and `make refresh`.

## Sources

- [OSM wiki: Key:sport](https://wiki.openstreetmap.org/wiki/Key:sport)
- [OSM wiki: Tag:amenity=place_of_worship](https://wiki.openstreetmap.org/wiki/Tag:amenity%3Dplace_of_worship)
- [OSM wiki: Key:healthcare:speciality](https://wiki.openstreetmap.org/wiki/Key:healthcare:speciality)
- Archive tag counts: run `20261106T142630Z` (OSM 2026-11-01), archived `docs/osm_tagging.md`.
