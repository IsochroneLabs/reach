"""City, urban boundary (decision O17a), routing area and districts, all in EPSG:25832."""

from __future__ import annotations

import geopandas as gpd
import shapely
from shapely.geometry.base import BaseGeometry

from reach_pipeline.config import UrbanBoundary
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


def urban_boundary(
    landuse: gpd.GeoSeries, city: BaseGeometry, cfg: UrbanBoundary
) -> gpd.GeoDataFrame:
    """Built-up land use inside the city: dissolved, gaps closed by buffering out and in, clipped
    to the city, parts below the minimum area dropped; parts (Teilorte) stay separate.

    Returns `part_id` (1 = largest), `name` (null) and a MultiPolygon per part.
    """
    merged = shapely.union_all(landuse.values)
    closed = merged.buffer(cfg.closing_m).buffer(-cfg.closing_m).intersection(city)
    parts = [p for p in shapely.get_parts(closed) if p.geom_type == "Polygon"]
    parts = sorted((p for p in parts if p.area >= cfg.min_part_area_m2), key=lambda p: -p.area)
    return gpd.GeoDataFrame(
        {"part_id": range(1, len(parts) + 1), "name": [None] * len(parts)},
        geometry=[shapely.MultiPolygon([p]) for p in parts],
        crs=METRIC_CRS,
    )


def routing_area(urban: gpd.GeoDataFrame, buffer_m: float) -> gpd.GeoDataFrame:
    """Urban boundary plus the routing buffer, as one (Multi)Polygon (arch. §4, O13)."""
    area = shapely.union_all(urban.geometry.values).buffer(buffer_m)
    return gpd.GeoDataFrame(geometry=[area], crs=METRIC_CRS)


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
