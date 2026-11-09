# OSM tagging guide — reach

> **Status:** v0.1 (9 Nov 2026), informative. How the facilities that `reach` counts are tagged in
> OpenStreetMap, which tags the pipeline reads (today and after the planned category work, see
> [`app_iteration_plan.md`](app_iteration_plan.md) W5 and W7), and how the team improves the data
> in OSM itself. Binding definitions of categories and `k` stay in
> [`methodology.md`](methodology.md) §2 and `config/config.yaml`.

**Why this matters.** `reach` reads OSM only from the Geofabrik extract (AGENTS.md rule 8). A
facility counts only if its tags match a category in `config/config.yaml`, so finer categories
(primary vs. secondary school, parks vs. playgrounds, public vs. private) are only as good as the
tags in OSM. Tags we add in OSM reach the pipeline with the next Geofabrik extract (updated daily)
and the next `make refresh`.

---

## 1. How the pipeline reads tags

- **Today:** `categories[].tags` in `config/config.yaml` is a list of `key: value` pairs; a feature
  that matches **any** pair belongs to the category (`facilities.match_categories`). Nothing else
  is read; in particular `access=*` is ignored (see §4).
- **Planned (W7):** each category can add
  - `require`: alternative conditions on further tags (a feature must match at least one), e.g.
    the school type;
  - `exclude`: conditions that drop a feature, e.g. `access` in `[private, no, customers]`.
  Values separated by `;` in OSM (`isced:level=1;2`) match if **any** part matches.
- **Planned (W5):** `facility_tags` lists the informative tags carried into the app (opening
  hours, wheelchair, address, …); they never change counts.

## 2. Status in Tübingen (run `20261106T142630Z`, OSM 2026-11-01)

Features with the main tag inside the routing area (city + 4 km), before de-duplication:

| Main tag | Features | Detail tag present |
|---|---|---|
| `shop=supermarket` | 60 | `brand` 45, `opening_hours` 60, `wheelchair` 51 |
| `amenity=pharmacy` | 30 | `healthcare=pharmacy` 26, `dispensing` 23, `opening_hours` 30, `wheelchair` 27 |
| `amenity=doctors` | 164 | `healthcare=doctor` 154, `healthcare:speciality` 129, `opening_hours` 125 |
| `amenity=kindergarten` | 157 | `preschool` 6, `min_age`/`max_age` 7/6, `nursery` 0, `after_school` 0 |
| `amenity=childcare` | 24 | `min_age`/`max_age` 1/1 |
| `amenity=school` | 73 | `isced:level` 1, `school=*` 0, `school:de` 0, `grades` 2 |
| `leisure=park` | 88 | `access` 4 (private 2, no 1) |
| `leisure=playground` | 349 | `access` 279: **private 65, customers 15**, permissive 15, yes 184 |

Two consequences: school types must be tagged before a primary-school category is possible (§3.5),
and 80 playgrounds that the public cannot use are counted today (§4).

## 3. Categories

For each category: the tag that defines it, the tags that refine it, and what we count.

### 3.1 Grocery — counted

| Tag | Use |
|---|---|
| `shop=supermarket` | **Defines the category.** Full-range food stores incl. discounters and organic supermarkets (Alnatura, denn's). |
| `brand=*`, `brand:wikidata=*` | Chain; the only reliable way to tell discounters apart (Aldi, Lidl, Penny, Netto, Norma). No separate discounter tag exists. |
| `opening_hours=*` | Shown in the app (W5). |
| `wheelchair=yes\|limited\|no` | Shown in the app. |

Not counted: `shop=convenience`, `shop=kiosk`, `shop=bakery`, `shop=greengrocer` (no full range).
A small organic or village shop that is tagged `shop=convenience` but has a full range should be
re-tagged `shop=supermarket` only if that is true on the ground.

### 3.2 Pharmacy — counted

| Tag | Use |
|---|---|
| `amenity=pharmacy` | **Defines the category.** |
| `healthcare=pharmacy` | Recommended companion tag. |
| `dispensing=yes` | Dispenses prescription drugs (every German *Apotheke*). Missing on 7 of 30. |
| `opening_hours=*`, `wheelchair=*` | Shown in the app. |

Drugstores (`shop=chemist`, dm, Rossmann) are not pharmacies.

### 3.3 Doctors — counted

| Tag | Use |
|---|---|
| `amenity=doctors` | **Defines the category.** One feature per practice. |
| `healthcare=doctor` | Recommended companion tag. |
| `healthcare:speciality=*` | Speciality; several values separated by `;` **without spaces** (`general;internal`). Values: `general` (GP, *Hausarzt*), `paediatrics` (*Kinderarzt*), `internal`, `gynaecology`, `ophthalmology`, `psychiatry`, … (British spelling). |
| `opening_hours=*`, `wheelchair=*` | Shown in the app. |

Status: 35 of 164 practices have no speciality, and 3 values start with a space (`; allergology`),
which a strict reader would miss. A GP category (decision E4) waits until most practices carry a
speciality. Dentists are `amenity=dentist` and not counted.

### 3.4 Childcare — counted

| Tag | Use |
|---|---|
| `amenity=kindergarten` | **Defines the category.** In Germany the umbrella for every *Kita* (Krippe, Kindergarten, Hort). |
| `nursery=yes` | Has places for children under 3 (*Krippe*). |
| `preschool=yes` | Kindergarten group (about 3–6). |
| `after_school=yes` | *Hort* for primary-school children. |
| `min_age=*`, `max_age=*` | Age range in years. |
| `amenity=childcare` | Rarely used, not clearly defined; meant for occasional care without registration (e.g. in a shopping centre). Counted today; see the open question below. |

Open question for the team: `amenity=childcare` features (24) may include occasional care that is
not a *Kita*; check them and either re-tag real *Kitas* as `amenity=kindergarten` or drop
`amenity=childcare` from the category (an existing config value, ask first).

### 3.5 School — counted; split planned (decision E3)

| Tag | Use |
|---|---|
| `amenity=school` | **Defines the category.** One feature per school site (the grounds polygon). |
| `school=primary\|secondary` | **Planned main type tag** (broad type, OSM-wide convention). |
| `school:de=*` | German school form. Values: `Grundschule`, `Gymnasium`, `Realschule`, `Gemeinschaftsschule`, `Werkrealschule`, `Hauptschule`, `SBBZ` (*Sonderpädagogisches Bildungs- und Beratungszentrum*), `Berufliche Schule`. |
| `isced:level=*` | International level: `1` primary, `2` lower secondary, `3` upper secondary, `4`+ post-secondary; several values `1;2`. Documented in the German wiki and read as a fallback. |
| `grades=*` | Grades taught, e.g. `1-4`, `5-13`. Optional. |

There is no consensus in the German OSM community between `school=*`, `school:de=*` (also spelled
`school:DE`) and `isced:level` (forum thread, 2023). To stay robust the pipeline will accept all
three; we tag **`school=*` + `school:de=*`**, plus `isced:level` where we know it:

| School form | `school` | `school:de` | `isced:level` | Counted as |
|---|---|---|---|---|
| Grundschule | `primary` | `Grundschule` | `1` | primary school |
| Grund- und Gemeinschaftsschule (same site) | `primary;secondary` | `Grundschule;Gemeinschaftsschule` | `1;2;3` | both |
| Gemeinschaftsschule, Werkrealschule, Realschule | `secondary` | as named | `2` (or `2;3`) | secondary school |
| Gymnasium | `secondary` | `Gymnasium` | `2;3` | secondary school |
| SBBZ (*Förderschule*) | – | `SBBZ` | as applicable | not counted (special catchment) |
| Berufliche Schule, Berufskolleg | – | `Berufliche Schule` | `3;4` | not counted (not 15-minute provision) |

A school with several forms on one site gets all values (`;`). A school with two sites gets the
tags on each site.

### 3.6 Parks — counted; split from playgrounds planned (W7)

| Tag | Use |
|---|---|
| `leisure=park` | **Defines the category.** Public green space for recreation; the polygon is needed. |
| `access=*` | `private`/`no` = not public (§4). |
| `name=*` | Shown in the app; 42 of 88 parks have one. |

**How parks are reached** (methodology §2): a park counts once if any **access point** is reachable;
access points are where walkable ways (`highway=footway|path|…`) cross the park boundary, else a
point every 50 m on the boundary (at most 20 per park). Mapping the paths that lead into a park
(and gates, `barrier=gate` on the boundary) therefore makes park times more realistic. A fenced
park whose only entrance is not mapped is reached at the wrong place.

### 3.7 Playgrounds — counted with parks today; own category planned (W7)

| Tag | Use |
|---|---|
| `leisure=playground` | **Defines the category.** |
| `access=yes\|permissive` | Public: counted. |
| `access=private\|customers\|no` | Not public (housing estates, restaurants, *Kitas*): **excluded after W7** (§4). |
| `min_age=*`, `max_age=*`, `surface=*`, `wheelchair=*` | Informative. |

### 3.8 Public transport — not from OSM

Stops and departures come from the NVBW GTFS feed (methodology §3), not from OSM. OSM bus stops
are not used, so tagging them changes nothing in `reach`.

## 4. Access: public or not

Today every feature counts regardless of `access`. That is wrong for green space: 65 private and 15
customer-only playgrounds (plus 3 parks) are counted as reachable. Rule planned in W7 (methodology
§2, ask first):

| Category | Excluded `access` values | Why |
|---|---|---|
| Parks, playgrounds | `private`, `no`, `customers` | Must be usable by the public. |
| School, childcare | none | `access=private` describes the grounds, not who may enrol. |
| Grocery, pharmacy, doctors | none | `customers` is normal for shops and practices. |

Validation reports the number of excluded features per category and value.

## 5. Informative tags shown in the app (W5)

`opening_hours`, `wheelchair`, `website` / `contact:website`, `phone` / `contact:phone`,
`addr:street`, `addr:housenumber`, `addr:postcode`, `brand`, `operator`,
`healthcare:speciality`. They are displayed as stored (no parsing of `opening_hours` in v1) and
never change counts. Adding them in OSM improves the app directly.

## 6. How we edit OSM

1. **Account and tools.** Personal OSM account; edit in the browser editor iD
   (openstreetmap.org → *Edit*) or JOSM. Read the
   [Automated edits code of conduct](https://wiki.openstreetmap.org/wiki/Automated_edits_code_of_conduct):
   every change is made by hand, one feature at a time; no scripts, no bulk imports.
2. **Sources.** Only what you know or can see: signs, the school's name, your own visit. Do not
   copy lists or details from the city's web pages or other databases; their licence is not
   compatible with OSM (notes N13). Set the changeset tag `source=survey` or `local knowledge`.
3. **Changesets.** Small and themed, with a clear comment, e.g.
   `Tübingen: add school type (school, school:de, isced:level) to 6 schools`.
4. **Check.** Find features still missing a tag with an Overpass query (for people, not for the
   pipeline), e.g. schools without a type in the city of Tübingen:

   ```text
   [out:json][timeout:60];
   area["de:amtlicher_gemeindeschluessel"="08416041"]->.city;
   nwr["amenity"="school"]["school"!~"."]["isced:level"!~"."](area.city);
   out center tags;
   ```

   Same pattern for playgrounds without `access`
   (`nwr["leisure"="playground"]["access"!~"."](area.city);`) or practices without speciality
   (`nwr["amenity"="doctors"]["healthcare:speciality"!~"."](area.city);`).
5. **Pick up.** The change reaches `reach` after the next Geofabrik extract (daily) and
   `make refresh`; the validation report (W7 check `facility_subtypes_complete`) shows the
   remaining gaps.

**Gate for the school split (W7):** start it when at least 95 % of the schools in the city carry a
type tag; until then the category stays `school`.

## 7. Config sketch after W7

Illustrative; the confirmed schema is defined in W7 and `docs/data_contract.md`.

```yaml
categories:
  - id: primary_school
    name: Primary school
    group: education
    k: 1
    tags: [{amenity: school}]
    require:
      - {school: primary}
      - {"school:de": Grundschule}
      - {"isced:level": "1"}
    location: point
  - id: playgrounds
    name: Playgrounds
    group: green
    k: 1
    tags: [{leisure: playground}]
    exclude: [{access: private}, {access: no}, {access: customers}]
    location: access_points
```

## Sources

- [OSM community forum: Art der Schulen über `isced:level`, `school` oder `school:DE`](https://community.openstreetmap.org/t/art-der-schulen-uber-isced-level-school-oder-school-de/104643) (no consensus; proposed `school` + `school:DE`)
- [OSM wiki: DE:Tag:amenity=kindergarten](https://wiki.openstreetmap.org/wiki/DE:Tag:amenity%3Dkindergarten) (Kita umbrella, `nursery`, `preschool`, `after_school`, `min_age`/`max_age`, `amenity=childcare`)
- [OSM wiki: Key:healthcare:speciality](https://wiki.openstreetmap.org/wiki/Key:healthcare:speciality) (values, `;` separator, dentists separate)
- [OSM wiki: DE:Key:isced:level](https://wiki.openstreetmap.org/wiki/DE:Key:isced:level)
- Tag counts: local run `20261106T142630Z` (`data/runs/<run>/validate/osm/facilities.geojsonseq`), counted 9 Nov 2026.
