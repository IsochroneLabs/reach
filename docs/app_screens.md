# App screens — reach web app

> **Status:** v0.1 draft (24 Nov 2026), step S2.1. Proposal, waiting for the team's yes.
> Built from `docs/product.md` v1.1 (binding) and the API proposal of S1.4 in
> `docs/data_contract.md` (on `docs/juju-fit-formula`, not yet in `dev`). Where this page needs
> something those documents do not have, it says so in [§9 Open points](#9-open-points); nothing
> here changes them.

The app has one student profile and two modes. It opens on *Find* with the default profile; the
search field for *Check* is always in the header. Every change to the profile recolours the map at
once.

## 1. Screens

Breakpoints (mobile first): **S** < 768 px (phone), **M** 768–1199 px (tablet, small laptop),
**L** ≥ 1200 px (desktop). Wireframes show L and S; M is L with the profile panel as a drawer that
the **Profile** button in the header opens.

### 1.1 Find — desktop (L)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ reach   [ Find | Check ]        [ Search an address in Tübingen…        ]   EN/DE  ⓘ  │
├───────────────────────┬──────────────────────────────────────────┬───────────────────┤
│ YOUR PROFILE          │                                          │ BEST AREAS FOR YOU│
│ ┌───────────────────┐ │                                          │ ┌───────────────┐ │
│ │! Select your      │ │          map: 100 m cells coloured       │ │1 Wanne     87 │ │
│ │  programme for    │ │          by fit 0–100                    │ │ • Morgenstelle│ │
│ │  results that fit │ │                                          │ │   9 min walk  │ │
│ │  you  [ ▾ ]       │ │                                          │ │   Tue 8:10    │ │
│ └───────────────────┘ │                                          │ │ • …           │ │
│ Getting around        │                                          │ │ ≈ 4 h 50/week │ │
│ [walk][bike][bus]     │                                          │ │ [Check here →]│ │
│ Destinations          │                                          │ └───────────────┘ │
│  Campus     ●●●● ▸    │                                          │ 2 Österberg  84   │
│  Mensa      ●●●○ ▸    │                                          │ 3 Lustnau    79   │
│  Supermarket●●●○ ▸    │ ┌Fit for you ─────────┐                  │                   │
│  Main stat. ●●●○ ▸    │ │0 ▁▂▃▄▅▆▇█ 100 ▨ none│                  │ Data: OSM 20 Nov, │
│ [+ Add destination]   │ └─────────────────────┘    © OSM · naldo │ timetable to 12 Dec│
│ Example profiles ▾    │                                          │                   │
└───────────────────────┴──────────────────────────────────────────┴───────────────────┘
```

- **Left (360 px):** profile panel (§2.2). Scrolls on its own.
- **Centre:** map. Legend bottom left, attribution bottom right, "updating…" chip top centre while
  a fit request runs.
- **Right (340 px):** the three best areas, each with 2–4 reasons, the area fit, the weekly travel
  time and **Check here** (opens *Check* at the area's best cell). Below: data date and sources.
- **Map click on a cell:** small popup "Fit 82 · ≈ 5 h/week · [Check this place]".

### 1.2 Find — mobile (S) with bottom sheet

```
┌──────────────────────────────┐
│ reach  [Find|Check]  🔍  EN ⓘ│   🔍 opens the full-width search field
├──────────────────────────────┤
│                              │
│      map: cells by fit       │
│                              │
│ ┌Fit 0▁▃▅▇█100┐   © OSM · …  │
├══════════════════════════════┤ ← sheet, peek height (≈ 30 % of the screen)
│            ───               │   drag handle (also a button: "Expand")
│ [ Results ]  [ Profile • ]   │   dot on Profile while no programme is set
│ ! Select your programme  [▾] │   programme hint (only while empty)
│ 1 Wanne 87 · Morgenstelle 9… │
│ 2 Österberg 84 · …           │
└──────────────────────────────┘
```

- Sheet snap points: **peek** (≈ 30 %), **half** (≈ 60 %), **full** (≈ 92 %, map still visible
  above). Drag, or tap the handle / tabs. `Esc` and the handle collapse it to peek.
- Two tabs: **Results** (area cards, as on desktop) and **Profile** (profile panel). The
  programme hint sits above both tabs until a programme is chosen.
- Changing the profile in the sheet recolours the map behind it at once (no "apply" button).

### 1.3 Check — one place

Desktop: the right column shows the place card; the profile panel stays on the left; the map
shows a pin and highlights the place's cell. Mobile: the sheet opens at half height on the
**Results** tab with the place card.

```
┌ PLACE CARD ──────────────────────────────────────┐
│ Hechinger Str. 12            [✎ name] [✕ remove] │
│                                                  │
│   82  / 100        Fit for your profile           │
│   Better than 80 % of places in Tübingen          │
│   ≈ 5 h 10 min per week on the way                │
│                                                  │
│ Rent per month (optional) [ € 450 ]  only stored │
│                                  in this browser │
│ ┌ Trips ─────────────────────────────────────────┐ │
│ │ Destination      Walk   Bike   Bus    When     │ │
│ │ Campus (Morg.)   34     12     18 ★   Tue 8:10 │ │
│ │ Mensa            11 ★   5      9      Tue 12:00│ │
│ │ Supermarket      6 ★    3      –      Tue 18:00│ │
│ │ Main station     25     9 ★    14     Sat 10:00│ │
│ │ share of the fit ▓▓▓▓▓▓▓░ (per row, bar)       │ │
│ └────────────────────────────────────────────────┘ │
│ ★ = fastest of your modes, used for the fit       │
│ [+ Compare another place]  [Better places nearby →]│
│ Data: OSM 20 Nov 2026 · timetable naldo to 12 Dec │
└──────────────────────────────────────────────────┘
```

- **Fit** large; under it the **rank in the city** (computed in the browser, §4.4); under that the
  **weekly travel time**. Each row of the trips table shows the destination name, minutes per
  mode, the trip window and the row's share of the fit; times in modes the student did not choose
  are shown greyed with "not in your modes".
- **Bus details** (expand a bus cell): walk to stop · wait · ride · transfers, first stop and line,
  "last bus home 00:47" for the night window (from `legs` and reasons).
- **Rent** is optional, typed per place, stored only in the browser; it never changes the fit.
- **Better places nearby** switches to *Find*, centred on this place, and outlines the cells
  within the nearby radius whose fit is higher (§4.5).

### 1.4 Check — compare (2–3 places)

Desktop: the right column widens to a comparison table over the map (≈ 720 px); mobile: a table
with the place names as sticky column headers, scrolled horizontally, inside the full sheet.

```
┌ COMPARE ───────────────────────────────────────────────────────────────┐
│ In short                                                               │
│ • Place 2 fits your profile better (82 vs. 71).                         │
│ • Place 2 costs €80 more per month but saves about 25 min per week.    │
│ • Place 1 is 15 min closer to the climbing gym by bike.                 │
│                                                                        │
│                     A Hechinger Str. 12   B Wanne 7       C (pin)       │
│ Fit                 71                    82 ★            64            │
│ Rank in the city    top 45 %              top 20 % ★      top 60 %      │
│ Weekly travel time  ≈ 5 h 35              ≈ 5 h 10 ★      ≈ 6 h 20      │
│ Rent per month      €370                  €450            –  [add]      │
│ Campus (Tue 8:10)   18 bus                12 bike ★       22 bus        │
│ Mensa (Tue 12:00)   …                     …               …             │
│ [Copy link to this comparison]                                         │
└────────────────────────────────────────────────────────────────────────┘
```

- Up to three places; a fourth is refused with a message, never silently dropped.
- "In short" is generated in the browser from the numbers (§6, keys `compare.*`): fit, weekly
  time, rent vs. weekly time (only when both rents are set), the 1–2 largest per-destination
  differences.
- **Copy link** copies the current URL (profile and places are in the hash, §3.2); the rents are
  part of it only if the student ticks "include rents in the link" (default off).

### 1.5 States

| State | Where | What the student sees |
|---|---|---|
| First load | map | Basemap at once; cells fade in when the first fit arrives; skeleton cards on the right / in the sheet |
| Updating (profile changed) | map + cards | Previous colours stay; "Updating…" chip; cards dimmed (`aria-busy`) |
| No programme | profile panel | Highlighted programme field with the hint; results use the default campus mix and say so on the campus row: "Campus: mix of Tal and Morgenstelle (no programme chosen)" |
| All destinations "not important" | map + cards | Grey map, message "Mark at least one destination as important to see where you fit" |
| No mode selected | profile panel | The last selected mode cannot be switched off (toggle disabled, tooltip "Choose at least one way of getting around") |
| Address search: < 3 characters | search | Hint "Type at least 3 characters" |
| Address search: no hit | search | "No address found in Tübingen. Try the street only, or drop a pin on the map." |
| Pin outside the city / cell without data | Check | Card with "No data for this place — we only cover the city of Tübingen" and no fit |
| Unreachable destination (`time_s` null) | trips table | "not reachable" in that cell, never 0, never hidden |
| Fit request fails (5xx, network) | banner over map | "Can't reach the server. Showing the results for your previous profile." + **Retry**; with no previous result: empty map + same banner |
| Rate limit (429) | banner | "Too many changes at once — updating in N s" (counts down from `Retry-After`, then retries once) |
| API unreachable on load | full panel | Map and profile panel still work; results area shows "The reach server is not reachable right now. Try again in a few minutes." + **Retry**; status of `/api/health` in the ⓘ dialog |
| Invalid link (bad hash) | toast | "Part of this link could not be read; we used the defaults for it." Valid parts are kept |
| `localStorage` blocked | none visible | Works for the session; ⓘ dialog says "Your browser blocks storage; your profile is kept only in the link" |
| Fixture mode | header badge | "Demo data" badge, the ⓘ dialog explains that numbers are hand-made examples |

The ⓘ dialog ("About these numbers") holds: data date per source (OSM extract, timetable validity,
Zensus 2022), the trip windows with their reference dates, the fit in one paragraph, the privacy
statement, build SHA and API status (replaces the placeholder page's fields).

## 2. Components

### 2.1 Tree

```
<App>                                  providers: I18n, Store (profile, places, ui), Api
├── <Header>
│   ├── <Logo>
│   ├── <ModeSwitch>                   Find | Check (tablist; changes the path)
│   ├── <AddressSearch>                combobox with suggestions (ARIA 1.2 pattern)
│   ├── <ProfileButton>                M only: opens the drawer
│   ├── <LanguageSwitch>               EN | DE
│   └── <AboutButton> → <AboutDialog>  data dates, trip windows, privacy, build, API status
├── <Layout>                           L: 3 columns · M: drawer + 2 columns · S: map + <BottomSheet>
│   ├── <ProfilePanel>
│   │   ├── <ProgrammeField>           hint while empty
│   │   ├── <ModeToggles>              walk, bike, bus (+ bike + bus if the API lists it)
│   │   ├── <DestinationList>
│   │   │   └── <DestinationRow>       name, <ImportancePicker> (4 levels), expand:
│   │   │       ├── <TripsPerWeekInput>
│   │   │       ├── <FineTimeSlider>
│   │   │       └── <TripWindowLabel>  read only ("Tuesday, arrive by 8:10")
│   │   ├── <AddDestinationMenu>
│   │   ├── <ExampleProfiles>          personas; picking one replaces the profile (undo toast)
│   │   └── <ResetProfileButton>
│   ├── <MapView>                      MapLibre, lazy-loaded
│   │   ├── <CellLayer>                fill layer from fit response + cell geometry (§4.3)
│   │   ├── <PlacePins>                Check: A/B/C pins, click-to-pin
│   │   ├── <NearbyOutline>            after "better places nearby"
│   │   ├── <CellPopup>                Find: fit, weekly time, "Check this place"
│   │   ├── <FitLegend>
│   │   └── <Attribution>              OSM, naldo GTFS, Zensus 2022, basemap
│   ├── <FindResults>
│   │   └── <AreaCard> ×3              <ReasonList>, fit, weekly time, "Check here"
│   ├── <CheckResults>
│   │   ├── <PlaceCard> ×1             <FitBadge>, <CityRank>, <WeeklyTime>, <RentInput>,
│   │   │                              <TripsTable> (<BusLegs>), "Better places nearby"
│   │   └── <CompareTable>             2–3 places, <CompareSummary> ("In short"), <ShareLink>
│   └── <DataNote>                     data date and sources under every result block
├── <StatusBanner>                     errors, 429 countdown, offline
└── <Toast>                            undo, invalid link
```

Shared leaf components: `<Minutes value mode window>` (every travel time renders through it, so
mode icon + window are never missing), `<ModeIcon>`, `<Importance>`, `<VisuallyHidden>`.

### 2.2 Profile panel defaults

From `docs/product.md` and `GET /api/destination-types`: programme none (default campus mix);
modes walk, bike, bus; destinations campus (very important), Mensa, supermarket, main station
(important); trips per week and fine time from the destination type. The panel lists the chosen
destinations first; **Add destination** offers the others from `GET /api/destination-types`.

## 3. State model

### 3.1 Shape

```ts
type Importance = 0 | 1 | 2 | 3            // not important · nice · important · very important
type Mode = 'walk' | 'bike' | 'transit' | 'bike_transit'

interface StudentProfile {                  // what POST /api/fit and POST /api/cell take
  programme: string | null                  // null → default campus mix (N16)
  campusDays?: Record<string, number>       // site_id → days per week (M7), optional
  modes: Mode[]                             // ≥ 1
  destinations: Record<string, {            // destination_type →
    importance: Importance
    fineTimeMin?: number                    // absent = type default
    tripsPerWeek?: number                   // absent = type default
  }>
}

interface Place {                           // Check, ≤ 3
  id: 'A' | 'B' | 'C'
  point: [number, number]                   // [lon, lat]
  cellId: string
  label: string | null                      // address label, or null for a pin
  rentEur: number | null                    // listing rent per month, browser only
}

interface UiState {                         // not persisted, except lang
  mode: 'find' | 'check'
  lang: 'en' | 'de'
  sheet: 'peek' | 'half' | 'full'
  nearbyOf: Place['id'] | null
}
```

Server data (reference lists, fit response, cell details) is **not** app state; it lives in a
small request cache keyed by the request (§4).

### 3.2 Where state lives

| State | URL | `localStorage` | Sent to the API |
|---|---|---|---|
| Mode (Find/Check) | path: `/` = Find, `/check` = Check | – | – |
| Profile | hash `p=` | `reach.v1.profile` | body of `POST /api/fit`, `POST /api/cell/{id}` |
| Places (point, label) | hash `pl=` | `reach.v1.places` | `cell_id` in the path of `POST /api/cell/{id}` |
| Listing rents | hash `r=` only if "include rents in the link" is ticked | `reach.v1.places` | never |
| Language | – | `reach.v1.lang` | – |
| Sheet height, popups | – | – | – |

- **Hash, not query string.** The browser never sends the part after `#` to a server, so the
  profile, places and rents do not reach Cloudflare's or the API's access logs when someone opens
  a shared link. Only the mode is in the path (not personal; the Worker serves the app for any
  path, tested by the smoke test).
- **Encoding** (readable, versioned, short):
  `#v=1&p=prog:biology;m:wbt;d:campus_site.3,mensa.2,grocery.2,climbing.2..2,main_station.1&pl=9.0461,48.5251,Hechinger%20Str.%2012|9.03,48.53`
  — `m:` letters `w` walk, `b` bike, `t` transit, `x` bike + transit; destinations as
  `type.importance.fine.trips` with empty parts = default. Points rounded to 5 decimals (≈ 1 m).
- **Precedence on load:** hash → `localStorage` → default profile. A valid hash also overwrites
  `localStorage`, so an opened link becomes the student's profile; the previous profile is offered
  back with an undo toast.
- **Writes:** every change updates the hash with `history.replaceState` (no history entry per
  slider step) and `localStorage` (wrapped in `try/catch`; on failure the app keeps working from
  memory and the URL). Mode changes use `pushState`, so Back returns to the other mode.
- **Unknown values** (programme or destination type not in the reference lists, importance out of
  range) are dropped with the "invalid link" toast; the rest of the link is kept.

## 4. Request flow

### 4.1 Reference data on load

`GET /api/destination-types`, `GET /api/campus-sites` (and the data-date endpoint, §9 Q4) in
parallel, cached for the session and revalidated with the run's `ETag`. The profile panel renders
with the defaults from these lists; until they arrive it shows skeleton rows.

### 4.2 Fit request (Find, and the rank in Check)

```
profile change ──► normalise (drop defaults, sort keys) ──► key = JSON string
     │
     ├─ key in memory cache (last 10 responses)? ──► render at once, done
     │
     └─ debounce 300 ms (restarts on every change)
            │
            ▼
        abort the in-flight request (AbortController)
        seq += 1; send POST /api/fit {profile}            "Updating…" on, old colours kept
            │
            ├─ 200, seq is still the latest ──► cache, recolour cells, area cards, "Updating…" off
            ├─ 200, seq is stale            ──► ignore
            ├─ AbortError                   ──► ignore (a newer request is coming)
            ├─ 422                          ──► banner "This profile could not be scored"; log the
            │                                   field to the console; keep old result
            ├─ 429                          ──► countdown from Retry-After, then resend once
            └─ network / 5xx / timeout 10 s ──► banner + Retry; keep old result
```

- Debounce 300 ms and cache size 10 are frontend settings in `web/src/settings.ts`, next to the
  nearby radius (§4.5); they are not part of `config/config.yaml` because the API never reads them.
- The cache is in memory only, cleared on reload; nothing personal is written anywhere else.
- Sliders send on release (`change`), not on every `input` event; the debounce catches keyboard
  arrows.

### 4.3 Cell geometry

The fit response carries `cells: {cell_id: [fit, weekly_min]}` and no geometry. A `cell_id`
(`CRS3035RES100mN<northing>E<easting>`) already encodes the lower-left corner of the 100 m square in
EPSG:3035. The app turns it into a polygon with a small inverse Lambert azimuthal equal-area
function (ETRS89-LAEA, ≈ 40 lines, no dependency), tested against corner points that PostGIS
computes for the fixture cells (`ST_Transform`). The square becomes a 4-corner polygon in
EPSG:4326; with 100 m cells the distortion is far below a pixel. The same function in the forward
direction maps a pin to its `cell_id`. Architecture rule 3 is kept: no distances are computed in
degrees; the browser only draws.

### 4.4 Rank in the city (Check)

`rank = share of populated cells with a fit strictly below the place's fit`, shown as "Better than
80 % of places in Tübingen" (rounded down to whole percent; above 95 % "Among the best 5 % of
places"). Computed from the cells of the current fit response; therefore *Check* also sends the
fit request (same cache as *Find*). Needs `origin_kind` per cell (§9 Q4).

### 4.5 Check requests

- Per place `POST /api/cell/{cell_id}` with the profile as body; up to three in parallel, each with
  its own AbortController; the same debounce on profile changes.
- **Better places nearby:** no extra request; the app takes the cells of the fit response within
  the nearby radius (1.5 km, measured in EPSG:3035 metres from the cell ids) whose fit is higher,
  switches to *Find* and outlines them.
- **Address search:** suggestions after 3 characters, 250 ms debounce, abort on each keystroke,
  up to 10 hits; arrow keys + Enter; picking a hit adds a place (or replaces the active one).

## 5. Map

- MapLibre GL JS, loaded with a dynamic `import()` after the shell renders, so the header, panel
  and search are usable before the map code arrives.
- Start view: city of Tübingen (bounds from the fixtures/API, not hard-coded), max bounds = routing
  area plus a margin.
- Cell colours: sequential, colour-blind safe ramp (viridis-like, 7 steps of 0–100); cells with
  no fit hatched grey, labelled "no data" in the legend. Opacity 0.65 so streets stay readable.
- The map is not the only way in: everything on the map is also reachable as a list (area cards,
  address search, place cards), so keyboard and screen-reader users never need the canvas.

### 5.1 Basemap (D5) — comparison, recommendation, not decided

Criterion (A6): **no user data to third parties.** Tile requests reveal the student's IP and the
part of the city they look at, so any tile host other than our own counts as a third party.

| | (a) Self-hosted vector tiles (PMTiles) | (b) Free hosted style (e.g. OpenFreeMap) | (c) No basemap, own layers only |
|---|---|---|---|
| Third parties | none: one file on our own origin | tile host sees IP + viewed area on every pan | none |
| What the student sees | streets, names, river, rail, buildings (OSM) | the same, polished | cells, district borders, stops, destinations only — no street names |
| Size / cost | Tübingen extract ≈ 5–15 MB **[VERIFY]**, fonts ≈ 0.4 MB; free within Cloudflare limits (25 MiB per file) | 0 MB, free, no SLA | 0 MB |
| Work | extract with `pmtiles extract` (bbox of the routing area, z ≤ 15) from a Protomaps build; a small hand-written style; self-hosted glyphs (Noto Sans, OFL); attribution OSM + Protomaps | a style URL | GeoJSON layers from the API |
| Dependency | `pmtiles` (protocol for MapLibre) | none | none |
| Risks | Cloudflare static assets must answer HTTP `Range` requests **[VERIFY]**; fallback: unpack to a `z/x/y.pbf` folder (a few thousand files, under the 20,000-file limit) | breaks A6; host may change or vanish | students new to the city cannot find streets or orient themselves; fails the product's first question |

**Recommendation: (a)** served from the frontend's own origin. The file is produced at build time
in CI (`pmtiles extract` from the public Protomaps build, never committed, never fetched at
runtime) and shipped with `dist/`. This needs one yes beyond the dependency: the root rule "data
never passes through GitHub or Cloudflare" was written for pipeline data; a basemap extract would
pass through the CI runner and Cloudflare. Alternative inside the rule: build it on the server and
serve it under `api.<domain>/tiles/` through the tunnel (slower first paint, more server load).

## 6. Texts (EN first, DE second)

All visible strings live in `web/src/i18n/en.ts` and `web/src/i18n/de.ts`; `de.ts` is typed
`satisfies Record<keyof typeof en, …>`, so a missing German key fails the build. Placeholders in
`{braces}`; numbers, minutes and euros through `Intl.NumberFormat` and `Intl.PluralRules` of the
current language. Destination, programme and campus names come from the API (`label.en` /
`label.de`), not from these files. "Bus" is the visible word for the mode `transit`.

| Key | EN | DE |
|---|---|---|
| `app.name` | reach | reach |
| `app.tagline` | Find where to live in Tübingen | Finde heraus, wo du in Tübingen wohnen willst |
| `mode.find` | Find | Finden |
| `mode.check` | Check | Prüfen |
| `mode.switch.label` | Mode | Modus |
| `search.placeholder` | Search an address in Tübingen… | Adresse in Tübingen suchen… |
| `search.label` | Address search | Adresssuche |
| `search.tooShort` | Type at least 3 characters | Mindestens 3 Zeichen eingeben |
| `search.noHit` | No address found in Tübingen. Try the street only, or drop a pin on the map. | Keine Adresse in Tübingen gefunden. Versuch es nur mit der Straße oder setze eine Markierung auf der Karte. |
| `search.loading` | Searching… | Suche… |
| `lang.switch` | Deutsch | English |
| `about.open` | About these numbers | Über diese Zahlen |
| `about.title` | About these numbers | Über diese Zahlen |
| `about.fit` | The fit (0–100) shows how well a place matches your profile: how long your trips take compared with the time that feels fine to you, weighted by how important each destination is. | Der Fit (0–100) zeigt, wie gut ein Ort zu deinem Profil passt: wie lange deine Wege dauern, verglichen mit der Zeit, die für dich in Ordnung ist, gewichtet nach der Wichtigkeit jedes Ziels. |
| `about.privacy` | Your profile, places and rents stay in this browser and in the link. Nothing is stored on our server; no tracking. | Dein Profil, deine Orte und Mieten bleiben in diesem Browser und im Link. Auf unserem Server wird nichts gespeichert; kein Tracking. |
| `about.sources` | Sources | Quellen |
| `about.build` | Build {sha} | Build {sha} |
| `about.api` | Server: {status} | Server: {status} |
| `about.storageBlocked` | Your browser blocks storage; your profile is kept only in the link. | Dein Browser blockiert den Speicher; dein Profil steht nur im Link. |
| `profile.title` | Your profile | Dein Profil |
| `profile.open` | Profile | Profil |
| `profile.programme` | Programme | Studiengang |
| `profile.programme.hint` | Select your programme for results that fit you | Wähle deinen Studiengang für passende Ergebnisse |
| `profile.programme.none` | No programme chosen | Kein Studiengang gewählt |
| `profile.campusMix` | Campus: mix of {sites} (no programme chosen) | Campus: Mischung aus {sites} (kein Studiengang gewählt) |
| `profile.modes` | Getting around | Unterwegs mit |
| `profile.modes.min` | Choose at least one way of getting around | Wähle mindestens ein Verkehrsmittel |
| `mode.walk` | Walk | Zu Fuß |
| `mode.bike` | Bike | Rad |
| `mode.transit` | Bus | Bus |
| `mode.bike_transit` | Bike + bus | Rad + Bus |
| `profile.destinations` | Destinations | Ziele |
| `profile.destinations.add` | Add destination | Ziel hinzufügen |
| `profile.destinations.remove` | Remove {name} | {name} entfernen |
| `importance.label` | How important? | Wie wichtig? |
| `importance.0` | Not important | Unwichtig |
| `importance.1` | Nice | Schön |
| `importance.2` | Important | Wichtig |
| `importance.3` | Very important | Sehr wichtig |
| `profile.tripsPerWeek` | Trips per week | Wege pro Woche |
| `profile.fineTime` | Feels fine up to | In Ordnung bis |
| `profile.fineTime.value` | {min} min | {min} Min. |
| `profile.when` | When | Wann |
| `profile.examples` | Example profiles | Beispielprofile |
| `profile.examples.applied` | Using the example profile "{name}". | Beispielprofil „{name}“ übernommen. |
| `profile.reset` | Back to the default profile | Zurück zum Standardprofil |
| `profile.undo` | Undo | Rückgängig |
| `window.weekday.tuesday` | Tue | Di |
| `window.weekday.saturday` | Sat | Sa |
| `window.arrive_by` | {day}, arrive by {time} | {day}, Ankunft bis {time} |
| `window.depart_at` | {day}, leave at {time} | {day}, Abfahrt {time} |
| `window.back` | {day}, way home at {time} | {day}, Heimweg um {time} |
| `find.results` | Best areas for you | Die besten Gegenden für dich |
| `find.tab.results` | Results | Ergebnisse |
| `find.tab.profile` | Profile | Profil |
| `find.area.rank` | {n}. {name} | {n}. {name} |
| `find.area.check` | Check here | Hier prüfen |
| `find.cell.check` | Check this place | Diesen Ort prüfen |
| `find.noneImportant` | Mark at least one destination as important to see where you fit | Markiere mindestens ein Ziel als wichtig, um zu sehen, wo du hinpasst |
| `find.nearby` | Better places near {place} | Bessere Orte in der Nähe von {place} |
| `reason.strength` | {name} {min} min {mode}, {window} | {name} {min} Min. {mode}, {window} |
| `reason.weakness` | {name} is {min} min away {mode} | {name} ist {min} Min. entfernt ({mode}) |
| `reason.reliability.last` | Last bus home {time} | Letzter Bus heim {time} |
| `reason.reliability.perHour` | {n} buses per hour | {n} Busse pro Stunde |
| `fit.label` | Fit for your profile | Fit für dein Profil |
| `fit.outOf` | {fit} / 100 | {fit} / 100 |
| `fit.legend` | Fit for you | Fit für dich |
| `fit.legend.none` | No data | Keine Daten |
| `rank.better` | Better than {pct} % of places in Tübingen | Besser als {pct} % der Orte in Tübingen |
| `rank.top` | Among the best 5 % of places in Tübingen | Unter den besten 5 % der Orte in Tübingen |
| `weekly.label` | About {time} per week on the way | Etwa {time} pro Woche unterwegs |
| `weekly.short` | ≈ {time}/week | ≈ {time}/Woche |
| `time.min` | {min} min | {min} Min. |
| `time.hmin` | {h} h {min} min | {h} Std. {min} Min. |
| `check.empty` | Search an address or tap the map to check a place. | Suche eine Adresse oder tippe auf die Karte, um einen Ort zu prüfen. |
| `check.pin` | Dropped pin | Markierter Ort |
| `check.place` | Place {id} | Ort {id} |
| `check.rename` | Rename | Umbenennen |
| `check.remove` | Remove place | Ort entfernen |
| `check.add` | Compare another place | Weiteren Ort vergleichen |
| `check.max` | You can compare up to 3 places. Remove one first. | Du kannst bis zu 3 Orte vergleichen. Entferne zuerst einen. |
| `check.nearby` | Better places nearby | Bessere Orte in der Nähe |
| `check.noData` | No data for this place — we only cover the city of Tübingen. | Keine Daten für diesen Ort – wir decken nur die Stadt Tübingen ab. |
| `rent.label` | Rent per month (optional) | Miete pro Monat (optional) |
| `rent.hint` | Only stored in this browser. Not part of the fit. | Nur in diesem Browser gespeichert. Nicht Teil des Fits. |
| `rent.value` | €{eur} | {eur} € |
| `rent.add` | Add rent | Miete eintragen |
| `trips.title` | Trips | Wege |
| `trips.destination` | Destination | Ziel |
| `trips.when` | When | Wann |
| `trips.share` | Share of the fit | Anteil am Fit |
| `trips.fastest` | Fastest of your modes, used for the fit | Schnellstes deiner Verkehrsmittel, zählt für den Fit |
| `trips.notYourMode` | Not in your modes | Nicht in deinen Verkehrsmitteln |
| `trips.unreachable` | Not reachable | Nicht erreichbar |
| `trips.notComputed` | Not computed | Nicht berechnet |
| `legs.walkToStop` | Walk to the stop {min} min | Fußweg zur Haltestelle {min} Min. |
| `legs.wait` | Wait {min} min | Warten {min} Min. |
| `legs.ride` | Ride {min} min ({line}) | Fahrt {min} Min. ({line}) |
| `legs.transfers` | {n, plural, one {# transfer} other {# transfers}} | {n, plural, one {# Umstieg} other {# Umstiege}} |
| `legs.walkFromStop` | Walk from the stop {min} min | Fußweg von der Haltestelle {min} Min. |
| `compare.title` | Compare | Vergleich |
| `compare.inShort` | In short | Kurz gesagt |
| `compare.fitBetter` | {a} fits your profile better ({fa} vs. {fb}). | {a} passt besser zu deinem Profil ({fa} gegenüber {fb}). |
| `compare.fitEqual` | {a} and {b} fit your profile about equally well. | {a} und {b} passen etwa gleich gut zu deinem Profil. |
| `compare.rentVsTime` | {a} costs €{eur} more per month but saves about {min} min per week. | {a} kostet {eur} € mehr im Monat, spart aber etwa {min} Min. pro Woche. |
| `compare.rentAndTime` | {a} costs €{eur} less per month and saves about {min} min per week. | {a} kostet {eur} € weniger im Monat und spart etwa {min} Min. pro Woche. |
| `compare.destDiff` | {a} is {min} min closer to {dest} {mode}. | {a} ist {min} Min. näher an {dest} ({mode}). |
| `compare.share` | Copy link to this comparison | Link zu diesem Vergleich kopieren |
| `compare.shareRents` | Include rents in the link | Mieten in den Link aufnehmen |
| `compare.copied` | Link copied | Link kopiert |
| `data.note` | Data: OSM {osmDate} · timetable {gtfsFrom}–{gtfsTo} · Zensus 2022 | Daten: OSM {osmDate} · Fahrplan {gtfsFrom}–{gtfsTo} · Zensus 2022 |
| `data.demo` | Demo data | Demodaten |
| `data.demo.explain` | The numbers are hand-made examples, not real travel times. | Die Zahlen sind ausgedachte Beispiele, keine echten Reisezeiten. |
| `status.updating` | Updating… | Wird aktualisiert… |
| `status.loading` | Loading… | Lädt… |
| `error.server` | Can't reach the server. Showing the results for your previous profile. | Server nicht erreichbar. Angezeigt werden die Ergebnisse für dein vorheriges Profil. |
| `error.serverNoResult` | The reach server is not reachable right now. Try again in a few minutes. | Der reach-Server ist gerade nicht erreichbar. Versuch es in ein paar Minuten noch einmal. |
| `error.rateLimit` | Too many changes at once — updating in {s} s | Zu viele Änderungen auf einmal – Aktualisierung in {s} s |
| `error.invalidProfile` | This profile could not be scored. | Dieses Profil konnte nicht bewertet werden. |
| `error.badLink` | Part of this link could not be read; we used the defaults for it. | Ein Teil dieses Links war nicht lesbar; dafür wurden die Standardwerte genommen. |
| `error.retry` | Retry | Erneut versuchen |
| `sheet.expand` | Expand | Aufklappen |
| `sheet.collapse` | Collapse | Einklappen |
| `map.label` | Map of Tübingen coloured by fit | Karte von Tübingen, eingefärbt nach Fit |
| `map.attribution` | © OpenStreetMap contributors · naldo timetable · Zensus 2022 | © OpenStreetMap-Mitwirkende · naldo-Fahrplan · Zensus 2022 |
| `footer.course` | DS500 course project, University of Tübingen | DS500-Kursprojekt, Universität Tübingen |
| `footer.source` | Source on GitHub | Quellcode auf GitHub |

Plural forms use a tiny formatter over `Intl.PluralRules` (the `{n, plural, …}` notation above is
the only syntax it understands); no i18n library.

## 7. Default campus mix without a programme (N16) — proposal, not decided

Without a programme the campus row uses a mix of sites. The mechanism already exists in the S1.4
proposal: `campus_days` (M7) weights the sites; the default is a fixed `campus_days`.

| Option | Sites and weights | For | Against |
|---|---|---|---|
| **(1) Tal + Morgenstelle, equal** | tal 1, morgenstelle 1 | The two sites almost every programme in `config/campus.yaml` uses (13 of 14); easy to say on screen: "mix of Tal and Morgenstelle" | Ignores Sand (computer science) and Schnarrenberg (medicine) |
| (2) All four sites, equal | tal, morgenstelle, sand, schnarrenberg 1 each | No site preferred | Sand and Schnarrenberg serve few programmes; pulls the map north-west for everyone |
| (3) Weighted by students per site | e.g. by enrolment numbers | Closest to "an average student" | Needs a source we do not have yet **[VERIFY]**; hard to explain |

**Recommendation: (1)**, stored as `campus.default_mix` in `config/campus.yaml` (new key, read by
the API) and returned by `GET /api/campus-sites` so the app can name the sites. The campus row and
the profile panel always say that a mix is used.

## 8. Dependencies — ask first, nothing installed

| Package | Kind | Size (approx.) | Why | Alternative considered |
|---|---|---|---|---|
| `maplibre-gl` | dependency | ≈ 800 KB min / ≈ 230 KB gzip JS + 60 KB CSS **[VERIFY at install]**, lazy-loaded | Named in architecture §10; vector map, fill layers for 2,200 cells, no key | Leaflet + canvas: weaker with vector tiles, would need a second plugin |
| `pmtiles` | dependency | ≈ 30 KB min / ≈ 10 KB gzip **[VERIFY]** | Reads the self-hosted basemap with HTTP Range requests (D5 option a) | Unpacked `z/x/y.pbf` folder: no dependency, thousands of files per deploy |
| `@axe-core/playwright` | devDependency (Phase E) | not shipped; ≈ 3 MB in `node_modules` | "axe without serious violations" (product quality goal, S2.7) | – |

**Without a library:** i18n (typed dictionaries + `Intl`), state (React `useReducer` + context),
routing (two paths, `history` API), URL encoding (§3.2), bottom sheet (CSS + pointer events),
projection (§4.3), basemap style (hand-written JSON, ≈ 200 lines), fonts (static glyph PBFs,
Noto Sans, OFL, self-hosted; no third-party fonts).

## 9. Open points

Questions for the team are marked **Q**; they are also in the S2.1 report.

1. **Q1 — D5 basemap:** (a) self-hosted PMTiles recommended (§5.1), incl. the build-time exception
   to "data never passes through GitHub or Cloudflare".
2. **Q2 — default campus mix:** option (1) Tal + Morgenstelle, equal (§7).
3. **Q3 — dependencies:** `maplibre-gl`, `pmtiles`, later `@axe-core/playwright` (§8).
4. **Q4 — gaps in the S1.4 API proposal** (data-contract changes on the Juju stack, need a yes):
   - **Data date:** no response carries the OSM date, the timetable validity or the reference date
     per trip window, but every number must show them. Proposal: `GET /api/meta` →
     `{run_id, sources: [{source, retrieved_at, valid_from?, valid_to?}], trip_windows:
     [{trip_window, weekday, time, kind, direction, reference_date}]}`.
   - **Rank against populated cells** (A1, N16 point 3): `cells` in `POST /api/fit` does not say
     which cells are populated. Proposal: a third tuple element, `[fit, weekly_min, populated]`.
   - **Address search sends the typed address as a query string** (`GET /api/addresses?q=`), which
     access logs keep; a listing address next to an IP is close to personal. Proposal:
     `POST /api/addresses/search {q}` (same response).
   - **Programme optional** and **default mix in `GET /api/campus-sites`** (N16 point 1, §7).
   - **Weekly travel time for a place:** taken from the fit response's `cells`, so no change to
     `POST /api/cell/{id}` is needed.
5. Product wording: "Every number shows mode, trip window and data date next to it". This page puts
   mode and window inline at every number (`<Minutes>`) and the data date once per result block
   (`<DataNote>`); a data date at each single number would crowd the trips table.
6. Defaults from the user interviews (S2.0) are not in yet; texts and defaults here are drafts to
   be checked there.

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| v0.1 draft | 2026-11-24 | First screen plan: screens, components, state model, request flow, texts EN/DE, D5 comparison, default campus mix, dependencies | Plan S2.1, product v1.1 |
