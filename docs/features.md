# Product Features & Functional Requirements

This document outlines the user-facing capabilities, analytical models, and feature roadmap for the 15-Minute City Platform.

---

## 1. Interactive Isochrone Explorer (Micro View)

*Target User: Citizens, home seekers, local residents*

* **Address Search & Free Pin-Drop:** Search any location in Germany or click directly on the map.
* **True Pedestrian Isochrones:** Compute dynamic 5-, 10-, and 15-minute walking catchment boundaries along actual footpaths, stairs, crossings, and terrain (powered by Valhalla).
* **Amenity Inventory:** List and filter POIs inside the reachable polygon across key 15-minute categories:
  * **Daily Essentials:** Supermarkets, bakeries, convenience stores, pharmacies.
  * **Healthcare:** General practitioners, clinics, pharmacies, hospitals.
  * **Education & Family:** Daycares/kindergartens, primary/secondary schools, libraries.
  * **Leisure & Well-being:** Parks, playgrounds, sports facilities, community centers.
* **Localized Scorecard:** Display an instant 0–100 score showing which categories are covered and which require travel beyond 15 minutes.

---

## 2. Citywide Accessibility & Heatmaps (Macro View)

*Target User: Urban researchers, municipal planners, real estate analysts*

* **Uber H3 Hexagonal Grid:** Tessellate target cities into discrete hexagonal cells (Resolution 8/9, ~100m–400m across) to aggregate spatial metrics without arbitrary administrative boundaries.
* **Category Layer Toggles:** Switch between composite 15-minute scores and individual sub-domain heatmaps (e.g., only "Primary Care Access" or "Fresh Food Access").
* **Time-Threshold Slider:** Adjust the walk-time tolerance (5, 10, or 15 minutes) to watch citywide reachability expand or contract.

---

## 3. Census-Weighted "Amenity Desert" Analysis (The Deficit Metric)

*Target User: Policy makers, equity analysts, city administrators*

* **Destatis Zensus 100m Grid Integration:** Layer German census population counts (`Einwohnerzahl`) and demographic attributes directly onto the spatial grid.
* **Unsatisfied Demand Index (Deficit Scoring):**
  $$\text{Deficit}_{i, c} = P_i \cdot (1 - A_{i, c})$$
  *(Where $P_i$ is cell population and $A_{i, c}$ is 15-minute accessibility to category $c$).*
  * Accurately distinguishes uninhabited areas (e.g., parks, industrial parks) from densely populated residential neighborhoods lacking critical infrastructure.
* **Vulnerability & Demographic Weighting:**
  * Weight kindergarten/school deficits by child density ($<6$ and $<18$ years).
  * Weight pharmacy/doctor deficits by senior population ($>65$ years).

---

## 4. Optimal Amenity Placement & Recommendation Engine (The Core USP)

*Target User: Urban planners, municipal councils, commercial developers*

* **Algorithmic Opportunity Discovery:**
  * Uses a greedy covering algorithm (Maximal Covering Location Problem / p-Median) to identify candidate locations where introducing a new facility maximizes the citywide population-weighted score.
* **Amenity Type Suggestion:**
  * Identifies which specific amenity category yields the highest marginal improvement for an underserved district.
* **"What-If" Simulation Sandbox:**
  * Allow users to manually drop a hypothetical amenity pin (e.g., a planned medical clinic) onto the map and immediately preview the before/after accessibility score delta.
* **Impact Cards:**
  * Generate human-readable scenario summaries (e.g., *"Placing a bakery/grocery in Hexagon #891f... serves 3,200 previously unserved residents within a 15-minute walk, improving district baseline coverage by +4.2%"*).

---

## 5. Feature Implementation Phasing

| Phase       | Milestone                 | Included Scope                                                                                                                 |
| ----------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| **Phase 1** | **MVP**                   | Interactive address search + pin-drop pedestrian isochrones + POI extraction within polygon + basic single-city H3 score grid. |
| **Phase 2** | **Deficit Layer**         | Destatis 100m Zensus import + population-weighted scoring + citywide "amenity desert" heatmap.                                 |
| **Phase 3** | **Recommendation Engine** | Algorithmic amenity placement solver + "What-If" interactive simulation tool + exportable summary reports.                     |
