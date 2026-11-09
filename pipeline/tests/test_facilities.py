"""Facility mapping, node + area de-duplication and park access points (meth. §2)."""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point, box

from reach_pipeline import facilities
from reach_pipeline.config import AccessPoints, Category

CRS = "EPSG:25832"
CATS = [
    Category(
        id="grocery",
        name="Grocery",
        group="food",
        k=2,
        tags=[{"shop": "supermarket"}],
        location="point",
    ),
    Category(
        id="childcare",
        name="Childcare",
        group="education",
        k=2,
        tags=[{"amenity": "kindergarten"}, {"amenity": "childcare"}],
        location="point",
    ),
    Category(
        id="parks",
        name="Parks",
        group="green",
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


def test_informative_tags_and_area_outline() -> None:
    feats = _features(
        [
            (
                "n1",
                {
                    "shop": "supermarket",
                    "name": "Node",
                    "opening_hours": "Mo-Sa 08:00-20:00",
                    "wheelchair": "yes",
                    "note": "not listed",
                },
                Point(50, 50),
            ),
            ("w3", {"leisure": "park", "name": "Park"}, box(0, 500, 100, 600)),
            ("n4", {"amenity": "kindergarten"}, Point(900, 900)),
        ]
    )
    fac, _ = facilities.build(feats, _ways(), CATS, AP, ["opening_hours", "wheelchair", "phone"])
    by_id = fac.set_index("facility_id")
    # only the listed keys that are set, as JSON text; no tags at all gives {}
    assert json.loads(by_id.loc["n1", "tags"]) == {
        "opening_hours": "Mo-Sa 08:00-20:00",
        "wheelchair": "yes",
    }
    assert by_id.loc["n4", "tags"] == "{}"
    # areas keep a simplified MultiPolygon outline, points none
    outline = by_id["area_geometry"]
    assert outline.loc["w3"].geom_type == "MultiPolygon"
    assert outline.loc["w3"].area == 10_000
    assert outline.loc["n1"] is None
    # without `tag_keys` nothing is kept
    plain, _ = facilities.build(feats, _ways(), CATS, AP)
    assert (plain["tags"] == "{}").all()


def test_tag_values_are_cleaned_for_jsonb() -> None:
    long = "x" * 400
    feats = _features(
        [
            (
                "n1",
                {"shop": "supermarket", "opening_hours": "Mo\x00-Fr\n08:00", "phone": long},
                Point(50, 50),
            ),
        ]
    )
    fac, _ = facilities.build(feats, _ways(), CATS, AP, ["opening_hours", "phone"])
    tags = json.loads(fac.set_index("facility_id").loc["n1", "tags"])
    assert tags["opening_hours"] == "Mo -Fr 08:00"  # NUL and newline replaced, never raw
    assert len(tags["phone"]) == facilities.MAX_TAG_LEN


PLAY = Category(
    id="playgrounds",
    name="Playgrounds",
    group="green",
    k=1,
    tags=[{"leisure": "playground"}],
    location="access_points",
    exclude=[{"access": "private"}, {"access": "no"}, {"access": "customers"}],
)
SECONDARY = Category(
    id="secondary_school",
    name="Secondary school",
    group="education",
    k=1,
    tags=[{"amenity": "school"}],
    location="point",
    require=[{"school": "secondary"}, {"school:de": "Gymnasium"}, {"isced:level": "3"}],
)


def test_exclude_drops_non_public_features_and_counts_them() -> None:
    feats = _features(
        [
            ("w1", {"leisure": "playground", "access": "yes"}, box(0, 0, 10, 10)),
            ("w2", {"leisure": "playground"}, box(100, 0, 110, 10)),
            ("w3", {"leisure": "playground", "access": "private"}, box(200, 0, 210, 10)),
            ("w4", {"leisure": "playground", "access": "customers"}, box(300, 0, 310, 10)),
            ("w5", {"leisure": "playground", "access": "no"}, box(400, 0, 410, 10)),
            ("w6", {"leisure": "playground", "access": "private;yes"}, box(500, 0, 510, 10)),
        ]
    )
    fac, _ = facilities.build(feats, _ways(), [PLAY], AP)
    assert sorted(fac["facility_id"]) == ["w1", "w2"]
    stats = facilities.exclusion_stats(feats, [PLAY])
    assert stats == {
        "playgrounds": {
            "excluded": 4,
            "access=private": 2,
            "access=no": 1,
            "access=customers": 1,
        }
    }
    assert facilities.exclusion_stats(feats, CATS) == {}  # no exclude conditions configured


def test_require_accepts_any_alternative_and_semicolon_values() -> None:
    feats = _features(
        [
            ("n1", {"amenity": "school", "school": "secondary"}, Point(0, 0)),
            ("n2", {"amenity": "school", "school:de": "Grundschule;Gymnasium"}, Point(10, 0)),
            ("n3", {"amenity": "school", "isced:level": "1; 3"}, Point(20, 0)),
            ("n4", {"amenity": "school", "school": "primary", "isced:level": "1"}, Point(30, 0)),
            ("n5", {"amenity": "school"}, Point(40, 0)),
            ("n6", {"amenity": "school", "isced:level": "13"}, Point(50, 0)),
        ]
    )
    fac, _ = facilities.build(feats, _ways(), [SECONDARY], AP)
    assert sorted(fac["facility_id"]) == ["n1", "n2", "n3"]


def test_subtype_gap_lists_schools_without_a_type_tag() -> None:
    feats = _features(
        [
            ("n1", {"amenity": "school", "name": "A", "school": "primary"}, Point(0, 0)),
            ("n2", {"amenity": "school", "name": "B"}, Point(10, 0)),
            ("n3", {"amenity": "school", "school:de": " "}, Point(20, 0)),
            ("n4", {"amenity": "pharmacy"}, Point(30, 0)),
        ]
    )
    total, missing = facilities.subtype_gap(
        feats, {"amenity": "school"}, ["school", "school:de", "isced:level"]
    )
    assert total == 3 and missing == ["B", "n3"]
    assert facilities.subtype_gap(feats, {"amenity": "x"}, ["school"]) == (0, [])
