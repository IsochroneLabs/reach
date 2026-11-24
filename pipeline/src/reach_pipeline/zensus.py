"""Zensus 2022 100 m population grid: streaming read filtered by bbox, cell geometries in 25832."""

from __future__ import annotations

from pathlib import Path

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from reach_pipeline.errors import StageValidationError

GRID_CRS = "EPSG:3035"
METRIC_CRS = "EPSG:25832"
CELL_SIZE_M = 100
# Columns of Zensus2022_Bevoelkerungszahl_100m-Gitter.csv (checked 2 Nov 2026): grid id and
# cell-centre coordinates in EPSG:3035, residents.
ID_COL, X_COL, Y_COL, POP_COL = "GITTER_ID_100m", "x_mp_100m", "y_mp_100m", "Einwohner"


def read_grid(csv: Path, bounds_3035: tuple[float, float, float, float]) -> pd.DataFrame:
    """Cells whose centre lies in the bbox (EPSG:3035), filtered while reading.

    Returns `cell_id`, `x`, `y` (cell centre, EPSG:3035) and `population`.
    """
    con = duckdb.connect()
    reader = "read_csv(?, sep=';', header=true)"
    columns = {
        row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {reader}", [str(csv)]).fetchall()
    }
    missing = {ID_COL, X_COL, Y_COL, POP_COL} - columns
    if missing:
        raise StageValidationError(f"{csv.name}: missing columns {sorted(missing)}")
    minx, miny, maxx, maxy = bounds_3035
    df = con.execute(
        f"""
        SELECT {ID_COL} AS cell_id, {X_COL} AS x, {Y_COL} AS y, {POP_COL} AS population
        FROM {reader}
        WHERE {X_COL} BETWEEN ? AND ? AND {Y_COL} BETWEEN ? AND ?
        """,
        [str(csv), minx, maxx, miny, maxy],
    ).df()
    if df["population"].isna().any() or (df["population"] < 0).any():
        raise StageValidationError(f"{csv.name}: empty or negative population values")
    return df.astype({"cell_id": str, "population": "int64"})


def cell_geometries(grid: pd.DataFrame) -> gpd.GeoDataFrame:
    """100 m cell polygon (geometry) and cell-centre origin (`origin_geom`), both in EPSG:25832."""
    x, y = grid["x"].to_numpy(float), grid["y"].to_numpy(float)
    half = CELL_SIZE_M / 2
    polys = gpd.GeoSeries(shapely.box(x - half, y - half, x + half, y + half), crs=GRID_CRS)
    origins = gpd.GeoSeries(shapely.points(np.column_stack([x, y])), crs=GRID_CRS)
    return gpd.GeoDataFrame(
        {
            "cell_id": grid["cell_id"].to_numpy(),
            "population": grid["population"].to_numpy(),
            "origin_geom": origins.to_crs(METRIC_CRS).values,
        },
        geometry=polys.to_crs(METRIC_CRS).values,
        crs=METRIC_CRS,
    )
