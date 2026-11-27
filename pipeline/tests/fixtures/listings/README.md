# Listing fixtures (F4.2)

Five anonymised WG-Gesucht ad pages and the parser output expected for each (`<name>.json`), shared
by the Python parser (`reach_pipeline.listings.parse`) and the browser parser of F4.3.

| Fixture | Kind | Size | Covers | Field coverage |
|---|---|---|---|---|
| `wg_minimal` | WG room | 6.5 KB | short page: no flatmate ages, one object item, street without number | 100 % |
| `wg_rich` | WG room | 9.8 KB | all WG fields, house number, features list, **contact data in the free text** (fake) | 100 % |
| `wg_medium` | WG room | 8.9 KB | age range, wanted age range, "schlechte Parkmöglichkeiten" (no parking feature) | 100 % |
| `studio` | 1-room flat | 6.6 KB | "Größe" instead of "Zimmergröße", absolute "Online" date | 100 % |
| `flat` | flat | 6.5 KB | rooms, "frei bis", barrier-free | 100 % |

Built with `make_fixtures.py` from pages fetched by hand on 27 Nov 2026 (notes N20). The script
keeps the original markup of the panels the parser reads and replaces ad numbers (9000000x),
image URLs, house numbers, the free text (synthetic), single-person ages and the map marker
(rounded to ~100 m); contact boxes, profile pictures, initials and scripts are dropped, and it
fails if an original identifier survives. Raw pages stay in `data/` and are never committed.
After a parser change, regenerate the JSON only after checking the difference by hand.
