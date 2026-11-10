"""Housing potential (methodology §5b): unpopulated grid cells as candidates for new homes.

A candidate is a 100 m Zensus grid cell that is not in `cells` (no residents in the 2022 census),
whose centre lies inside the urban boundary grown by `housing.edge_buffer_m` and outside
excluded land use. It is counted like a resident cell (matrix from its centre to the facilities),
so the result is directly comparable with `access_counts`.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from reach_pipeline import recommend as rec
from reach_pipeline.zensus import METRIC_CRS

COLUMNS = ["cell_id", "district_id"]


def candidate_cells(
    area: gpd.GeoSeries | object,
    populated_ids: np.ndarray,
    polygons: gpd.GeoSeries,
    districts: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
    """Unpopulated grid cells in `area` (EPSG:25832) outside `polygons`, sorted by id.

    Returns `cell_id`, `district_id` (district containing the centre, null outside), the cell
    polygon as geometry and the centre as `origin_geom` (all EPSG:25832), plus statistics.
    """
    grid = rec.candidate_grid(area, 100)
    populated = grid["candidate_id"].isin(populated_ids).to_numpy()
    free = grid[~populated]
    keep = rec.outside(free.geometry, polygons)
    out = free[keep].sort_values("candidate_id").reset_index(drop=True)
    joined = gpd.sjoin(
        gpd.GeoDataFrame(geometry=out.geometry, crs=METRIC_CRS),
        districts[["district_id", "geometry"]],
        how="left",
        predicate="within",
    )
    district = joined[~joined.index.duplicated()]["district_id"].reindex(out.index)
    frame = gpd.GeoDataFrame(
        {
            "cell_id": out["candidate_id"].to_numpy(),
            "district_id": district.to_numpy(),
            "origin_geom": gpd.GeoSeries(out.geometry.values, crs=METRIC_CRS),
        },
        geometry=gpd.GeoSeries(out["zone_geom"].values, crs=METRIC_CRS),
        crs=METRIC_CRS,
    )
    stats = {
        "grid_in_area": len(grid),
        "populated": int(populated.sum()),
        "excluded_landuse": int((~keep).sum()),
        "kept": len(frame),
    }
    return frame, stats


def no_cells() -> gpd.GeoDataFrame:
    """Empty frame with the columns of `candidate_cells`."""
    return gpd.GeoDataFrame(
        {
            "cell_id": pd.Series(dtype=object),
            "district_id": pd.Series(dtype=object),
            "origin_geom": gpd.GeoSeries(crs=METRIC_CRS),
        },
        geometry=gpd.GeoSeries(crs=METRIC_CRS),
        crs=METRIC_CRS,
    )
