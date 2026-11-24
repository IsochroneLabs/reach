"""City boundary, routing area, districts and origin cells, all in EPSG:25832."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

from reach_pipeline.errors import StageValidationError

METRIC_CRS = "EPSG:25832"
AGS_TAG = "de:amtlicher_gemeindeschluessel"


def admin_boundary(admin: gpd.GeoDataFrame, admin_level: int, ags: str) -> BaseGeometry:
    """The one `boundary=administrative` area with this admin level and municipality key."""
    if AGS_TAG not in admin.columns:
        raise StageValidationError(f"no {AGS_TAG} tag on any administrative boundary")
    match = admin[(admin["admin_level"] == str(admin_level)) & (admin[AGS_TAG] == ags)]
    if len(match) != 1:
        raise StageValidationError(
            f"expected one admin boundary with admin_level {admin_level} and AGS {ags}, "
            f"found {len(match)}"
        )
    return match.geometry.iloc[0]


def routing_area(scope: BaseGeometry, buffer_m: float) -> gpd.GeoDataFrame:
    """Study area (the city) plus the routing buffer, as one (Multi)Polygon (arch. §5.2)."""
    return gpd.GeoDataFrame(geometry=[scope.buffer(buffer_m)], crs=METRIC_CRS)


def districts(
    admin: gpd.GeoDataFrame, city: BaseGeometry, admin_levels: list[int]
) -> gpd.GeoDataFrame:
    """Administrative areas of the given levels whose representative point lies in the city."""
    levels = [str(level) for level in admin_levels]
    cand = admin[admin["admin_level"].isin(levels) & admin.representative_point().within(city)]
    return gpd.GeoDataFrame(
        {
            "district_id": cand["osm_id"].to_numpy(),
            "name": cand["name"].to_numpy(),
            "admin_level": cand["admin_level"].astype("int16").to_numpy(),
        },
        geometry=[shapely.MultiPolygon(shapely.get_parts(g)) for g in cand.geometry],
        crs=METRIC_CRS,
    ).sort_values("district_id", ignore_index=True)


def coverage(districts: gpd.GeoDataFrame, city: BaseGeometry) -> tuple[float, float]:
    """Gap and overlap area of the districts, each as share of the city area (0..1)."""
    union = shapely.union_all(districts.geometry.values)
    gap = city.difference(union).area
    overlap = max(0.0, districts.area.sum() - union.area)  # float noise can make it negative
    return gap / city.area, overlap / city.area


def largest_overlap(cells: gpd.GeoSeries, districts: gpd.GeoDataFrame) -> pd.Series:
    """`district_id` with the largest area overlap per cell polygon (index of `cells`), NaN if
    a cell touches no district."""
    left, right = shapely.STRtree(districts.geometry.values).query(
        cells.values, predicate="intersects"
    )
    pairs = pd.DataFrame(
        {
            "cell": cells.index.to_numpy()[left],
            "district_id": districts["district_id"].to_numpy()[right],
            "area": shapely.area(
                shapely.intersection(cells.values[left], districts.geometry.values[right])
            ),
        }
    )
    best = pairs.sort_values("area", ascending=False).drop_duplicates("cell")
    return best.set_index("cell")["district_id"].reindex(cells.index)


def scoring_scope(
    cells: gpd.GeoDataFrame, scope: BaseGeometry, districts: gpd.GeoDataFrame
) -> tuple[gpd.GeoDataFrame, dict[str, int], int]:
    """Split cells by the study area (meth. §2): a cell is an origin if its centre
    (`origin_geom`) lies inside `scope`; the coverage base is every cell whose polygon touches
    `scope`.

    Returns the origin cells, excluded residents per district name (largest overlap,
    descending) and the residents of all touching cells.
    """
    touching = cells[cells.intersects(scope)]
    inside = touching.set_geometry("origin_geom").within(scope).to_numpy()
    excluded = touching[~inside]
    names = districts.set_index("district_id")["name"]
    owner = largest_overlap(excluded.geometry, districts).map(names).fillna("(no district)")
    by_district = excluded.groupby(owner)["population"].sum().sort_values(ascending=False)
    return (
        touching[inside].reset_index(drop=True),
        {str(k): int(v) for k, v in by_district.items()},
        int(touching["population"].sum()),
    )
