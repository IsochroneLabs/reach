# OSM tagging guide — reach

> **Status:** v1.1 draft (26 Nov 2026), informative. Which OpenStreetMap tags define each
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
| `gym` *(replaced by `sport`/`fitness`, §5)* | `leisure=fitness_centre` | yoga studios are tagged this way too | archive: 12 |
| `climbing` *(replaced by `sport`/`climbing`, §5)* | `leisure=sports_centre`, `leisure=pitch` | require `sport` = `climbing` (incl. bouldering) | [VERIFY] counts |
| `swimming` *(replaced by `sport`/`swimming`, §5)* | `leisure=sports_centre`, `leisure=water_park`, `leisure=swimming_pool` | require `sport=swimming` or a public pool: exclude `access` = `private`, `no`, `customers`; garden pools excluded | [VERIFY] counts |
| `sports_club` *(replaced by the `sport` categories, §5)* | `leisure=sports_centre` | exclude non-public `access` | archive: 75, unfiltered by sport |
| `music` *(replaced by `hobby`/`music`, §5)* | `amenity=music_school`, `amenity=music_venue` | | [VERIFY] counts |
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

## 5. Destination labels (F2.1, measured 26 Nov 2026)

Taxonomy in `config/config.yaml` → `destination_labels` (methodology §3.1, architecture O22),
decided by Juju on 26 Nov 2026. Counted on the routing-area extract of the T1 spike (Geofabrik
`tuebingen-regbez`, 21 Nov 2026, city + 4 km) with the exploration script on
`exp/juju-label-counts`. *Features* are OSM objects after the access filter; *destinations* are
what remains after clustering (same label within 75 m or inside the same
`leisure=sports_centre`). A node and a building outline of the same shop count as one destination.

### 5.1 Supermarkets: brand and group

Every `shop=supermarket` gets **a brand** (if it matches one) and **exactly one group**.

- **Brand:** `brand:wikidata` first, then a case-insensitive substring of `brand` or `name`
  (catches "Rewe"/"REWE", "Edeka"/"EDEKA", Lidl and Norma without a Wikidata id). Brands with
  fewer than `brand_min_stores` (2) stores are not offered on their own.
- **Group,** first match wins: `organic` (`organic=only`, Alnatura, denn's) → `zero_waste`
  (`zero_waste=only`, `bulk_purchase=only`) → `international` (Mix Markt, name patterns such as
  *asia*, *türk*, *salam*, *schami*, *ikram*) → `discount` (ALDI SÜD, Lidl, PENNY, Netto, Norma) →
  `full_range` (EDEKA, REWE, Kaufland, Nahkauf) → `local` (name patterns *dorfladen*, *hofladen*,
  *marktladen*, *…-laden*) → `other`. Name patterns are regular expressions on `name`, `alt_name`
  and `short_name`; they are a curated list, checked by V10 spot checks.
- A student can pick brands, groups or both; the grocery term uses the union.

| label | features | destinations | examples |
|---|---|---|---|
| edeka | 16 | 11 | E-Center Haid, EDEKA, EDEKA Schöck, Edeka |
| aldi_sued | 11 | 8 | Aldi Süd |
| penny | 8 | 6 | PENNY, Penny |
| lidl | 8 | 5 | Lidl |
| rewe | 6 | 5 | REWE, Rewe |
| netto | 6 | 4 | Netto Marken-Discount |
| kaufland | 4 | 3 | Kaufland |
| alnatura | 2 | 2 | Alnatura Super Natur Markt |
| denns | 2 | 2 | Denns BioMarkt |
| norma | 4 | 2 | Norma |
| mix_markt | 1 | 1 | Mix Markt |
| nahkauf | 1 | 1 | Nahkauf Hummel |

| label | features | destinations | examples |
|---|---|---|---|
| discount | 37 | 25 | Aldi Süd, Lidl, Netto Marken-Discount, Norma |
| full_range | 27 | 20 | E-Center Haid, EDEKA, EDEKA Schöck, Edeka |
| organic | 11 | 10 | Alnatura Super Natur Markt, Bioladen Reusten, Biomarkt West, Denns BioMarkt |
| international | 4 | 4 | Früchtehaus Al Schami, Ikram Supermarkt, Loretto Markt Salam, Mix Markt |
| other | 4 | 4 | Bonus, Emmiy, Schmackes |
| local | 3 | 3 | Dorfladen Pfrondorf, Löwen-Laden, Schmackes Alte Zimmerei |
| zero_waste | 1 | 1 | Speicher Umgedacht |

`other` holds Bonus (2), Emmiy and Schmackes (Wanne): no tag or name says what kind of shop they
are. A tag in OSM (e.g. `organic=only`) moves a shop into its group with the next extract (§4).

### 5.2 Sport categories

Candidates: `leisure` = `sports_centre`, `pitch`, `fitness_centre`, `swimming_pool`, `track`,
`sports_hall`, `water_park`, `ice_rink`, `golf_course`, `horse_riding`, `dance`, and `club=sport`.
The category comes from `sport=*` (`;` values split); **only if no sport value maps** does the
`leisure` value decide (a fitness centre tagged `sport=yoga` is yoga, a track with `sport=bmx` is
skate). `leisure=swimming_pool` counts only with `access=yes|public` (garden pools are untagged).
`sport` = `multi`, `mixed`, `unknown` is ignored. Every category with at least one destination is
offered (decision "everything in"); below 3 the app says "few places mapped".

| label | features | destinations | examples |
|---|---|---|---|
| football | 369 | 144 | Affenkäfig Feuerhägle, Alter Lustnauer Sportplatz, Bolzplatz, Bolzplatz Gartenstraße |
| table_tennis | 94 | 55 |  |
| basketball | 112 | 53 | Affenkäfig Feuerhägle, Basketballkorb, Freilufthalle Holderfeld, Panzerhalle |
| tennis | 270 | 41 | TC Nehren, TC Unterjesingen, TSG Tübingen, Tennisclub Dettenhausen |
| athletics | 86 | 34 | Finnenbahn, SV-Bahn, Turnhalle Feuerhägle |
| equestrian | 88 | 33 | Abreiteplatz und Geländestrecke Reit- und Fahrverein Lustnau e.V., Erlenhof, Immenhof, Kehrerhof |
| volleyball | 73 | 33 | TSG Tübingen |
| boules | 35 | 18 | Boule Platz, Hufeisenplatz SV Gniebel |
| shooting_archery | 47 | 18 | Ammerbucher Sportschützen, Bogenschießplatz, Castle Archers, KKSV Ohmenhausen e.V. |
| fitness | 19 | 15 | 3 in One Bewegungspark, Anytime Gym, Cabriolo, Clever fit |
| skate | 26 | 13 | 3 in One Bewegungspark, Dirtpark Wurmlingen, Fun-Park "Madach-Hägle", Halfpipe |
| swimming | 19 | 11 | Freibad, Freibad Entringen, Freibad Mössingen, Hallenbad |
| motor_model | 14 | 8 | Flugmodellsport-Club Reutlingen e.V., Flugsportverein Ammerbuch e.V., MFC Kusterdingen e.V., Modellflugplatz |
| cycling | 15 | 7 | 3 in One Bewegungspark, BMX-Bahn TSV Betzingen, Bikepark Gomaringen, Dirtpark Wurmlingen |
| handball | 12 | 6 |  |
| other_team | 12 | 6 | Multifunktionssportplatz für Hockey und Fußblall |
| climbing | 11 | 5 | B12 – DAV Boulderzentrum Tübingen, Clip'n'Climb, DAV Kletteranlage, Jump Area |
| dance | 7 | 5 | Danzon, Rainbow Dance Factory, Tanzschule Olaf S., Tanzschule Salsamara |
| golf | 6 | 5 | Golfclub Schloss Kressbach, Golfclub Schönbuch, Kleiner Schlossplatz |
| martial_arts | 3 | 3 | JSV Tübingen e.V., Kampfkunstzentrum Rottenburg, Taekwondo Creti |
| yoga | 3 | 3 | Der Yogasalon, Namasté, Yoga Circle Tübingen |
| racket_indoor | 4 | 2 | Cabriolo, Squashinsel |
| bowling | 1 | 1 | Bowlingcenter Rottenburg |
| water_sports | 1 | 1 | Ruderverein Fidelia |

Caveats: `table_tennis` and many `basketball` destinations are outdoor tables and hoops in parks
and school yards; `football` includes small pitches (Bolzplätze); school pitches often carry no
`access` tag and count as public. Indoor sports (badminton, martial arts, yoga, rowing clubs) are
under-mapped (notes N23).

### 5.3 Hobby categories

| Category | Tags |
|---|---|
| `music` | `amenity=music_school`, `club=music` |
| `arts` | `amenity=arts_centre` |
| `makerspace` | `leisure=hackerspace` |
| `chess` | `sport=chess`, `club=chess` |

`amenity=community_centre` (106 features) is not a hobby category: it says nothing about the
activity.

| label | features | destinations | examples |
|---|---|---|---|
| music | 15 | 13 | Kla4schule im Französischen Viertel, Massimiliano d’Antonio, Musikinsel bei der Ölmühle, Musikschule Ammerbuch |
| arts | 9 | 7 | Club Voltaire, Epplehaus, Kulturhalle, Kulturzentrum beim Klosterhof |
| chess | 10 | 6 |  |
| makerspace | 3 | 3 | FabLab, KI-Makerspace, iconet Foundation |

`chess` destinations are mostly outdoor chess boards without a name; clubs are rarely mapped.

### 5.4 Religion

| label | features | destinations | examples |
|---|---|---|---|
| christian | 256 | 131 | .Heilig-Kreuz- und Wendelinskirche, Adventgemeinde, Albert-Schweitzer-Kirche, Altstadtkapelle |
| muslim | 3 | 3 | DITIB Moschee, Fatih Camii, IGMG Moschee Tübingen |
| buddhist | 2 | 1 | Chùa Viên Quang Pagode |
| unknown | 2 | 1 |  |

## Sources

- [OSM wiki: Key:sport](https://wiki.openstreetmap.org/wiki/Key:sport)
- [OSM wiki: Tag:amenity=place_of_worship](https://wiki.openstreetmap.org/wiki/Tag:amenity%3Dplace_of_worship)
- [OSM wiki: Key:healthcare:speciality](https://wiki.openstreetmap.org/wiki/Key:healthcare:speciality)
- [OSM wiki: Key:brand:wikidata](https://wiki.openstreetmap.org/wiki/Key:brand:wikidata), [Key:organic](https://wiki.openstreetmap.org/wiki/Key:organic), [Key:zero_waste](https://wiki.openstreetmap.org/wiki/Key:zero_waste)
- Archive tag counts: run `20261106T142630Z` (OSM 2026-11-01), archived `docs/osm_tagging.md`.
