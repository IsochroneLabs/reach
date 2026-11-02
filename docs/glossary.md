# Glossary

Project vocabulary used in code, docs, issues and prompts. People and roles ("you", "your human",
"the team") are defined in [`AGENTS.md`](../AGENTS.md).

| Term | Meaning |
|---|---|
| **Core / Stretch** | Core = required for the graded deliverable. Stretch = only after Core works and is validated (`architecture.md` §12). |
| **urban boundary** | Settlement area of Tübingen; only cells inside it are scored. |
| **routing buffer** | 4 km around the urban boundary; network and facilities are loaded from boundary + buffer. |
| **cell** | One populated Zensus 2022 100 m grid cell; the unit of analysis. `cell_id` = original EPSG:3035 ID. |
| **origin** | Routing start point of a cell (currently the cell centroid). |
| **facility** | A service location from OSM in one of the configured categories. |
| **category** | Facility type defined in `config/config.yaml` (e.g. grocery, pharmacy, school); see `methodology.md` §2. |
| **profile** | Travel mode with its settings: walking 3.39 km/h, walking 5.0 km/h, cycling, wheelchair. |
| **reach** | Maximum straight-line distance of a profile (speed × time budget); used as exact prefilter. |
| **count (A)** | Number of facilities of a category reachable from a cell within the time budget, via Valhalla matrix. |
| **class** | Lack / insufficient / sufficient per cell, category and profile (`methodology.md` §4). |
| **deficit (U)** | Population-weighted unmet need per cell (`methodology.md` §4). |
| **k_c** | Sufficiency threshold of category *c* (`methodology.md` §2). |
| **catchment** | Cells that reach a facility or candidate site within the time budget. |
| **reference weekday** | Regular Tuesday in the GTFS validity period used to count departures. |
| **matrix** | Valhalla `sources_to_targets`: travel times between many points; used for all counting. |
| **isochrone** | Valhalla polygon of the area reachable within a time; display only. |
| **expansion** | Valhalla list of reached street segments with times; visualisation only. |
| **run / `run_id`** | One complete pipeline execution on one data snapshot; results are published as DB schema `run_<id>`. |
| **stage** | One pipeline step: acquire, validate inputs, build tiles, count, score, recommend, validate results, publish, cleanup. |
| **manifest** | File written by each stage listing inputs, outputs, row counts and status. |
| **`current`** | DB views pointing to the latest validated run; the only schema the API reads. |
| **data contract** | Binding table and file schemas between pipeline and API (`docs/data_contract.md`). |
| **test clip** | Small OSM/GTFS/Zensus extract (~1 km²) used for integration tests. |
| **O-numbers (O1, …)** | Architecture decisions in `architecture.md` §13. |
| **M-numbers (M1, …)** | Open methodology questions in `methodology.md` §7. |
| **V-numbers (V1, …)** | Validation experiments in `methodology.md` §6. |
| **N-numbers (N1, …)** | Open points and future work in `notes.md`. |
| **gate G1** | Test whether slopes change walking times in Valhalla (Stretch). |
| **ask first** | Stop, describe what you want to do and why, and wait for an explicit "yes" from your human. |
