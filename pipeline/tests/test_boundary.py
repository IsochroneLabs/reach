"""Urban boundary (O17a), routing area, admin boundary lookup and district coverage."""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from reach_pipeline import boundary
from reach_pipeline.config import UrbanBoundary
from reach_pipeline.errors import StageValidationError

CRS = "EPSG:25832"
CITY = box(0, 0, 2000, 1000)
CFG = UrbanBoundary(landuse=["residential"], closing_m=50, min_part_area_m2=10_000)


def _landuse(*geoms) -> gpd.GeoSeries:
    return gpd.GeoSeries(list(geoms), crs=CRS)


def test_closing_merges_small_gaps_and_keeps_teilorte_apart() -> None:
    # two blocks 60 m apart merge (gap < 2 × 50 m); a third block 500 m away stays a part
    landuse = _landuse(box(0, 0, 200, 200), box(260, 0, 460, 200), box(960, 0, 1160, 200))
    urban = boundary.urban_boundary(landuse, CITY, CFG)
    assert list(urban["part_id"]) == [1, 2]
    assert urban.geometry.iloc[0].contains(box(200, 50, 260, 150))  # gap closed
    assert urban.geometry.iloc[1].area == pytest.approx(200 * 200, rel=1e-3)
    assert (urban.geom_type == "MultiPolygon").all()


def test_small_parts_dropped_and_clipped_to_city() -> None:
    landuse = _landuse(box(0, 0, 200, 200), box(1500, 500, 1550, 550), box(1900, 0, 2100, 200))
    urban = boundary.urban_boundary(landuse, CITY, CFG)
    assert len(urban) == 2  # the 50 × 50 m block is below 10,000 m²
    assert urban.union_all().within(CITY.buffer(1e-6))


def test_routing_area_buffers_union() -> None:
    urban = boundary.urban_boundary(_landuse(box(0, 0, 200, 200)), CITY, CFG)
    area = boundary.routing_area(urban, 4000).geometry.iloc[0]
    assert area.contains(box(-3900, -3900, 4100, 4100).centroid)
    assert not area.contains(box(4300, 100, 4301, 101))


def _admin() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "osm_id": ["r1", "r2", "r3", "r4", "r5"],
            "name": ["City", "West", "East", "Overlap", "Elsewhere"],
            "admin_level": ["8", "9", "11", "10", "9"],
            boundary.AGS_TAG: ["123", None, None, None, None],
        },
        geometry=[
            CITY,
            box(0, 0, 1000, 1000),
            box(1000, 0, 2000, 1000),
            box(500, 0, 1500, 1000),
            box(5000, 0, 6000, 1000),
        ],
        crs=CRS,
    )


def test_admin_boundary_by_level_and_ags() -> None:
    assert boundary.admin_boundary(_admin(), 8, "123").equals(CITY)
    with pytest.raises(StageValidationError, match="found 0"):
        boundary.admin_boundary(_admin(), 8, "999")


def test_districts_mixed_levels_cover_city() -> None:
    districts = boundary.districts(_admin(), CITY, [9, 11])
    assert list(districts["district_id"]) == ["r2", "r3"]  # r5 lies outside the city
    assert districts["admin_level"].tolist() == [9, 11]
    assert boundary.coverage(districts, CITY) == pytest.approx((0.0, 0.0))


def test_coverage_reports_overlap_and_gap() -> None:
    overlapping = boundary.districts(_admin(), CITY, [9, 10, 11])
    gap, overlap = boundary.coverage(overlapping, CITY)
    assert gap == pytest.approx(0) and overlap == pytest.approx(0.5)
    only_west = boundary.districts(_admin(), CITY, [9])
    assert boundary.coverage(only_west, CITY)[0] == pytest.approx(0.5)
