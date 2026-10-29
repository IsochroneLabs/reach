# 15-Minute City Analyzer: System Architecture & Roadmap

## 1. Project Objective & Core Concept

Evaluate urban accessibility across Germany using the 15-minute city principle.
Rather than just visualizing access, our platform will identify **accessibility deficits** and solve an **optimal facility placement problem**: recommending where a new amenity should go and what type it should be to maximize a city-wide population-weighted score function.

---

## 2. Key Data Sources

- **Street & Footpath Graph:** OpenStreetMap (OSM) via Geofabrik (`germany-latest.osm.pbf`).
- **Amenity POIs:** Extracted OSM tags (food, healthcare, education, leisure).
- **Demographics:** Federal Statistical Office (Destatis) Zensus data on standardized 100m × 100m grid cells (`Einwohnerzahl` + age breakdowns).

---

## 3. Recommended Tech Stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| **Routing / Isochrones** | Valhalla (Docker / Apptainer) | Pedestrian-costed routing and dynamic isochrone polygons. |
| **Spatial Database** | PostgreSQL 16 + PostGIS 3.4 | Amenity indexing (`GiST`), spatial joins, and containment queries. |
| **Tessellation Grid** | Uber H3 (Res 8 / 9) | Hexagonal spatial units for aggregation and scoring. |
| **Vector Tile Server** | Martin (Rust) | High-speed MVT streaming directly from PostGIS. |
| **Backend API** | FastAPI (Python) | Routing orchestration, scoring endpoints, placement solver. |
| **Frontend Map** | MapLibre GL JS + Deck.gl | Hardware-accelerated basemaps and hexagonal deficit layers. |

---

## 4. Hardware & Deployment Strategy ($20 Budget)

Running all of Germany on a budget server (~€12–€20/mo, 8–16 GB RAM) is feasible by decoupling compilation from runtime:

1. **Cluster Batch Job (HPC / bwUniCluster):**
   - Use Apptainer/Singularity to build Valhalla routing tiles (`valhalla_tiles.tar`, ~5 GB) using 32 GB RAM / 8 cores.
   - Filter Germany's OSM POIs using `osmium-tool` (~2 min runtime).
2. **Production Server:**
   - Host runtime Valhalla (via `mmap`, ~2 GB RAM footprint) and PostGIS (~1.5 GB RAM footprint).
   - Only code and configs live in Git; raw data artifacts are transferred directly via `rsync`.

---

## 5. Scoring & Optimization Model

1. **Hex Score ($S_i$):** Average accessibility across amenity categories for cell $i$.
2. **Deficit ($U_{i,c}$):** Population $\times$ $(1 - \text{Access})$, highlighting populated amenity deserts.
3. **Placement Optimization:** A greedy heuristic (p-Median / MCLP) selecting candidate locations that yield the highest marginal gain in population-weighted access:
   $$\Delta W = \sum_{\text{reachable } i} P_i \cdot (\text{New Access} - \text{Old Access})$$

---

## 6. Proposed Phases

- **Phase 1:** Docker stack setup (PostGIS + Valhalla) + basic single-city ingestion.
- **Phase 2:** MapLibre/Deck.gl UI showing H3 hex accessibility scores.
- **Phase 3:** HPC batch script for nationwide Germany tiles + Destatis Zensus overlay.
- **Phase 4:** Greedy placement solver and UI recommendation cards.
