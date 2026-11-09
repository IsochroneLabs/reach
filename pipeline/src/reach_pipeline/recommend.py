"""Recommender (methodology §5, arch. §6.4, §6.5 rule 7): candidates, catchments, greedy.

Candidates are 100 m Zensus grid cells (populated or not) whose centre lies inside the urban
boundary and outside excluded land use. The catchment of a candidate is the set of scored cells
whose origin reaches the candidate's centre within the facility budget (matrix: cells as
sources, candidates as targets). The greedy selection adds one facility at a time where it
reduces the deficit sum most:

    gain(x) = sum_{i in C(x)} P_i * [min(1, (A_i + 1) / k) - min(1, A_i / k)]

which is ΔW of methodology §5 (the reduction of U = P * max(0, 1 - A / k)); after each pick
A_i += 1 for the cells of its catchment. Each candidate is picked at most once.
"""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from reach_pipeline.zensus import CELL_SIZE_M, GRID_CRS, METRIC_CRS


def grid_id(north: np.ndarray, east: np.ndarray) -> np.ndarray:
    """Zensus grid ids from the lower-left corners (EPSG:3035, whole metres)."""
    n = pd.Series(np.asarray(north, dtype=np.int64)).astype(str)
    e = pd.Series(np.asarray(east, dtype=np.int64)).astype(str)
    return ("CRS3035RES100mN" + n + "E" + e).to_numpy(dtype=object)


def candidate_grid(area: shapely.Geometry, spacing_m: int) -> gpd.GeoDataFrame:
    """Grid cells (every `spacing_m` on the 100 m Zensus grid) whose centre lies in `area`.

    `area` is in EPSG:25832. Returns `candidate_id` (grid id), the centre as `geometry` and the
    100 m cell polygon as `zone_geom`, both EPSG:25832.
    """
    area_3035 = gpd.GeoSeries([area], crs=METRIC_CRS).to_crs(GRID_CRS)
    x0, y0, x1, y1 = area_3035.total_bounds
    xs = np.arange(np.floor(x0 / spacing_m) * spacing_m, x1 + 1, spacing_m)
    ys = np.arange(np.floor(y0 / spacing_m) * spacing_m, y1 + 1, spacing_m)
    east, north = (a.reshape(-1) for a in np.meshgrid(xs, ys))
    half = CELL_SIZE_M / 2
    centres = gpd.GeoSeries(
        shapely.points(np.column_stack([east + half, north + half])), crs=GRID_CRS
    ).to_crs(METRIC_CRS)
    inside = shapely.contains_xy(area, centres.x.to_numpy(), centres.y.to_numpy())
    east, north = east[inside], north[inside]
    zones = gpd.GeoSeries(
        shapely.box(east, north, east + CELL_SIZE_M, north + CELL_SIZE_M), crs=GRID_CRS
    ).to_crs(METRIC_CRS)
    return gpd.GeoDataFrame(
        {"candidate_id": grid_id(north, east), "zone_geom": zones.values},
        geometry=centres[inside].values,
        crs=METRIC_CRS,
    )


def on_spacing(candidate_ids: np.ndarray, spacing_m: int) -> np.ndarray:
    """Mask of candidates whose grid-id corner lies on a `spacing_m` grid (EPSG:3035)."""
    parts = pd.Series(candidate_ids).str.removeprefix("CRS3035RES100mN").str.split("E", expand=True)
    corners = parts.to_numpy(dtype=np.int64)
    return (corners % spacing_m == 0).all(axis=1)


def no_candidates() -> gpd.GeoDataFrame:
    """Empty candidate frame with the columns of `candidate_grid`."""
    return gpd.GeoDataFrame(
        {"candidate_id": pd.Series(dtype=object), "zone_geom": gpd.GeoSeries(crs=METRIC_CRS)},
        geometry=gpd.GeoSeries(crs=METRIC_CRS),
        crs=METRIC_CRS,
    )


PROTECTED = ("boundary", "protected_area")


def exclusions(
    polygons: gpd.GeoDataFrame, tags: list[dict[str, str]], protect_classes: list[str]
) -> tuple[gpd.GeoSeries, dict[str, object]]:
    """Excluded polygons from an osmium export (tag columns): every polygon matching one of
    `tags`, plus `boundary=protected_area` polygons whose `protect_class` is listed. Returns
    them and statistics of the protected areas that stay allowed (by class, `none` = no class):
    count and area in km²."""

    def col(name: str) -> pd.Series:
        if name in polygons:
            return polygons[name].astype("string")
        return pd.Series(pd.NA, index=polygons.index, dtype="string")

    by_tag = np.zeros(len(polygons), dtype=bool)
    for tag in tags:
        ((key, value),) = tag.items()
        by_tag |= (col(key) == value).fillna(False).to_numpy()
    protected = (col(PROTECTED[0]) == PROTECTED[1]).fillna(False).to_numpy()
    cls = col("protect_class").str.strip()
    listed = cls.isin(protect_classes).fillna(False).to_numpy()
    excluded = by_tag | (protected & listed)
    kept = polygons[protected & ~excluded]
    kept_cls = cls[protected & ~excluded].fillna("none")
    area = kept.geometry.area / 1e6
    stats = {
        str(c): {
            "count": int((kept_cls == c).sum()),
            "area_km2": round(float(area[kept_cls == c].sum()), 2),
        }
        for c in sorted(set(kept_cls))
    }
    return polygons.geometry[excluded], {"protected_area_not_excluded": stats}


def outside(points: gpd.GeoSeries, polygons: gpd.GeoSeries) -> np.ndarray:
    """True for points not inside any of the polygons (vectorised, spatial index)."""
    keep = np.ones(len(points), dtype=bool)
    if len(points) and len(polygons):
        hit, _ = shapely.STRtree(polygons.values).query(points.values, predicate="within")
        keep[np.unique(hit)] = False
    return keep


def near_any(xy: np.ndarray, others: np.ndarray, reach_m: float) -> np.ndarray:
    """True for points of `xy` within `reach_m` (straight line) of any point of `others`."""
    near = np.zeros(len(xy), dtype=bool)
    if len(xy) and len(others):
        hit, _ = shapely.STRtree(shapely.points(others)).query(
            shapely.points(xy), predicate="dwithin", distance=reach_m
        )
        near[np.unique(hit)] = True
    return near


def catchment_pairs(times: np.ndarray, budget_s: float) -> pd.DataFrame:
    """Pairs within the budget of one group matrix (sources = cells, targets = candidates):
    `source`, `target` (row/column index), `time_s` (whole seconds, int16)."""
    src, tgt = np.nonzero(times <= budget_s)  # NaN (unreachable) compares False
    return pd.DataFrame(
        {
            "source": src,
            "target": tgt,
            "time_s": np.rint(times[src, tgt]).astype(np.int16),
        }
    )


@dataclass(frozen=True)
class Pick:
    """One greedy step: candidate index and what the new facility changes in its catchment."""

    rank: int
    candidate: int
    population_gain: float  # ΔW (residents, deficit reduction)
    residents_gaining_access: int  # residents of cells with A = 0 before (class leaves "lack")
    residents_to_sufficient: int  # residents of cells with A < k <= A + 1
    catchment_residents: int
    catchment_cells: int


def gain_weights(population: np.ndarray, counts: np.ndarray, k: int) -> np.ndarray:
    """Per cell: deficit reduction if one more facility is reachable (ΔU of methodology §4)."""
    a = counts.astype(float)
    return population * (np.minimum(1.0, (a + 1) / k) - np.minimum(1.0, a / k))


def greedy(
    cover: np.ndarray,
    population: np.ndarray,
    counts: np.ndarray,
    k: int,
    top_n: int,
    min_gain: float,
) -> list[Pick]:
    """Greedy selection of up to `top_n` candidates (methodology §5).

    `cover` (candidates × cells, bool) marks the catchments; `counts` are the cells' current
    A_{i,c}. Stops early when the best remaining gain is below `min_gain`. Ties go to the lower
    candidate index (candidates are sorted by id, so the result is deterministic).
    """
    pop = population.astype(float)
    a = counts.astype(np.int64).copy()
    cover_f = cover.astype(float)
    used = np.zeros(len(cover), dtype=bool)
    picks: list[Pick] = []
    for rank in range(1, top_n + 1):
        if used.all():
            break
        gains = cover_f @ gain_weights(pop, a, k)
        gains[used] = -np.inf
        x = int(np.argmax(gains))
        if gains[x] <= 0 or gains[x] < min_gain:  # nothing left to gain (also min_gain 0)
            break
        m = cover[x]
        picks.append(
            Pick(
                rank=rank,
                candidate=x,
                population_gain=round(float(gains[x]), 2),
                residents_gaining_access=int(pop[m & (a == 0)].sum()),
                residents_to_sufficient=int(pop[m & (a < k) & (a + 1 >= k)].sum()),
                catchment_residents=int(pop[m].sum()),
                catchment_cells=int(m.sum()),
            )
        )
        a[m] += 1
        used[x] = True
    return picks


def replay(
    catchments: list[np.ndarray], population: np.ndarray, counts: np.ndarray, k: int
) -> list[tuple[float, int, int]]:
    """Recompute (gain, residents gaining access, residents to sufficient) of a ranked list of
    catchments (cell index arrays) from the counts, adding one facility after the other; the
    check of `validate_results`."""
    pop = population.astype(float)
    a = counts.astype(np.int64).copy()
    out = []
    for cells in catchments:
        m = np.zeros(len(a), dtype=bool)
        m[cells] = True
        out.append(
            (
                round(float(gain_weights(pop[m], a[m], k).sum()), 2),
                int(pop[m & (a == 0)].sum()),
                int(pop[m & (a < k) & (a + 1 >= k)].sum()),
            )
        )
        a[m] += 1
    return out
