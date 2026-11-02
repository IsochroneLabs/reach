"""Facility mapping, node + area de-duplication and park access points (meth. §2)."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point, box

from reach_pipeline import facilities
from reach_pipeline.config import AccessPoints, Category

CRS = "EPSG:25832"
CATS = [
    Category(id="grocery", name="Grocery", k=2, tags=[{"shop": "supermarket"}], location="point"),
    Category(
        id="childcare",
        name="Childcare",
        k=2,
        tags=[{"amenity": "kindergarten"}, {"amenity": "childcare"}],
        location="point",
    ),
    Category(
        id="parks",
        name="Parks",
        k=1,
        tags=[{"leisure": "park"}, {"leisure": "playground"}],
        location="access_points",
    ),
]
AP = AccessPoints(spacing_m=50, max_points=20, walkable_highways=["footway"])


def _features(rows: list[tuple[str, dict[str, str], object]]) -> gpd.GeoDataFrame:
    data = [{"osm_id": osm_id, **tags} for osm_id, tags, _ in rows]
    return gpd.GeoDataFrame(data, geometry=[g for *_, g in rows], crs=CRS)


def _ways(*lines: LineString) -> gpd.GeoSeries:
    return gpd.GeoSeries(list(lines), crs=CRS)


def test_mapping_dedupe_and_kinds() -> None:
    feats = _features(
        [
            ("n1", {"shop": "supermarket", "name": "Node"}, Point(50, 50)),
            ("w2", {"shop": "supermarket", "name": "Building"}, box(0, 0, 100, 100)),
            ("w3", {"shop": "supermarket"}, box(500, 0, 600, 100)),
            ("n4", {"amenity": "kindergarten", "name": "Kita"}, Point(900, 900)),
            ("n5", {"leisure": "park"}, Point(1050, 50)),  # park node inside park area
            ("w6", {"leisure": "park"}, box(1000, 0, 1100, 100)),
            ("n7", {"leisure": "playground"}, Point(1060, 60)),  # other tag: own facility
            ("n8", {"amenity": "bench"}, Point(5, 5)),
        ]
    )
    fac, points = facilities.build(feats, _ways(), CATS, AP)
    assert sorted(fac["facility_id"]) == ["n1", "n4", "n7", "w3", "w6"]
    assert fac.set_index("facility_id").loc["n4", "category"] == "childcare"
    assert (fac.geom_type == "Point").all()
    kinds = points.groupby("facility_id")["kind"].first().to_dict()
    assert kinds == {
        "n1": "node",
        "n4": "node",
        "n7": "node",
        "w3": "representative",
        "w6": "access",
    }
    # the area without crossing ways gets fallback points every 50 m along its 400 m boundary
    assert (points["facility_id"] == "w6").sum() == 8
    assert points.groupby("facility_id")["point_id"].apply(list)["w6"] == list(range(8))


def test_one_facility_with_two_tags_of_one_category() -> None:
    feats = _features([("n1", {"amenity": "childcare", "leisure": "playground"}, Point(0, 0))])
    fac, _ = facilities.build(feats, _ways(), CATS, AP)
    assert sorted(fac["category"]) == ["childcare", "parks"]


def test_access_points_from_crossings_and_shared_stretches() -> None:
    park = gpd.GeoDataFrame({"facility_id": ["w1"]}, geometry=[box(0, 0, 100, 100)], crs=CRS)
    ways = _ways(
        LineString([(50, -20), (50, 120)]),  # crosses twice: (50, 0) and (50, 100)
        LineString([(-10, 30), (0, 30), (0, 70)]),  # runs along the west edge from y=30 to 70
        LineString([(300, 300), (400, 400)]),  # far away
    )
    pts = facilities.access_points(park, ways, AP)
    coords = sorted((round(p.x), round(p.y)) for p in pts.geometry)
    assert coords == [(0, 30), (0, 70), (50, 0), (50, 100)]


def test_access_points_capped_evenly() -> None:
    park = gpd.GeoDataFrame({"facility_id": ["w1"]}, geometry=[box(0, 0, 1000, 1000)], crs=CRS)
    ring_length = 4000
    for m in (4, 5, 7):
        cfg = AccessPoints(spacing_m=50, max_points=m, walkable_highways=["footway"])
        pts = facilities.access_points(park, _ways(), cfg)  # 80 fallback points → m
        assert len(pts) == m
        ring = park.geometry.iloc[0].exterior
        pos = np.sort([ring.project(p) for p in pts.geometry])
        gaps = np.append(np.diff(pos), ring_length - pos[-1] + pos[0])  # incl. wrap-around
        # every gap, also across the start of the ring, is the ideal spacing ± one 50 m step
        assert gaps.min() >= ring_length / m - 50 and gaps.max() <= ring_length / m + 50, gaps


def test_tiny_playground_gets_one_point() -> None:
    area = gpd.GeoDataFrame({"facility_id": ["w1"]}, geometry=[box(0, 0, 10, 10)], crs=CRS)
    assert len(facilities.access_points(area, _ways(), AP)) == 1
