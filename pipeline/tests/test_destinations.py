"""Destinations per type, park access points, campus points and the address index (S1.6)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from reach_pipeline import campus, destinations, zensus
from reach_pipeline.config import load_config
from reach_pipeline.errors import ConfigError

REPO = Path(__file__).resolve().parents[2]
CRS = "EPSG:25832"
X0, Y0 = 500_000, 5_375_000  # inside Tübingen in EPSG:25832


@pytest.fixture
def cfg():
    return load_config(REPO / "config" / "config.yaml")


def _features() -> gpd.GeoDataFrame:
    rows = [
        # osm_id, tags, geometry
        ("n1", {"shop": "supermarket", "name": "Markt A"}, Point(X0, Y0)),
        ("w2", {"railway": "station", "name": "Tübingen Hbf"}, box(X0, Y0, X0 + 80, Y0 + 30)),
        ("n3", {"railway": "station", "name": "Tübingen Hbf"}, Point(X0 + 40, Y0 + 15)),
        ("n4", {"railway": "station", "name": "Lustnau"}, Point(X0 + 3000, Y0)),
        ("w5", {"leisure": "park", "name": "Alter Park"}, box(X0 + 1000, Y0, X0 + 1200, Y0 + 200)),
        ("w6", {"leisure": "park", "access": "private"}, box(X0 + 2000, Y0, X0 + 2100, Y0 + 100)),
        ("w7", {"highway": "footway"}, LineString([(X0 + 900, Y0 + 100), (X0 + 1300, Y0 + 100)])),
        ("w8", {"highway": "motorway"}, LineString([(X0 + 1100, Y0 - 50), (X0 + 1100, Y0 + 250)])),
        (
            "w9",
            {"addr:street": "Wilhelmstraße", "addr:housenumber": "5", "addr:postcode": "72074"},
            box(X0 + 10, Y0 + 10, X0 + 20, Y0 + 20),
        ),
        ("n10", {"addr:street": "Wilhelmstraße", "addr:housenumber": "5"}, Point(X0 + 15, Y0 + 15)),
        ("n11", {"amenity": "pharmacy", "name": "Apotheke"}, Point(X0 + 50_000, Y0)),
    ]
    keys = sorted({k for _, tags, _ in rows for k in tags})
    data = {"osm_id": [r[0] for r in rows]}
    data |= {k: [r[1].get(k) for r in rows] for k in keys}
    return gpd.GeoDataFrame(data, geometry=[r[2] for r in rows], crs=CRS)


def test_types_access_points_and_merging(cfg) -> None:
    # wide enough for all four campus sites (Sand is ≈ 5.3 km east of X0)
    area = box(X0 - 6000, Y0 - 6000, X0 + 6000, Y0 + 6000)
    dest = destinations.build(_features(), campus.load_campus(REPO / "config" / "x"), cfg, area)
    per_type = dest.groupby("destination_type")["destination_id"].nunique().to_dict()
    assert per_type["grocery"] == 1
    # node and area of the main station merge; Lustnau fails `require`
    assert per_type["main_station"] == 1
    assert dest.loc[dest["destination_type"] == "main_station", "osm_id"].item() == "w2"
    park = dest[dest["destination_type"] == "park"]
    # the footway crosses the public park twice; the motorway is not walkable; private excluded
    assert set(park["destination_id"]) == {"park:w5"}
    assert len(park) == 2 and park["point_id"].is_unique
    assert "pharmacy" not in per_type  # outside the routing area
    assert per_type["campus_site"] == 4 and per_type["mensa"] >= 1
    assert destinations.counts(dest, cfg)["library"] == 0
    assert "sport" not in destinations.counts(dest, cfg)  # containers have no own destinations


def test_addresses_dedupe_and_label(cfg) -> None:
    area = box(X0 - 5000, Y0 - 5000, X0 + 5000, Y0 + 5000)
    feats = _features()
    shop = feats.iloc[[0]].assign(
        osm_id="n12", **{"addr:street": "Neckarhalde", "addr:housenumber": "2"}
    )
    feats = gpd.GeoDataFrame(pd.concat([feats, shop], ignore_index=True), crs=CRS)
    addr = destinations.addresses(feats, area, cfg)
    assert len(addr) == 3  # building with postcode, the bare node, the shop
    assert addr.set_index("street")["residential"].to_dict()["Neckarhalde"] == np.False_
    assert "Wilhelmstraße 5, 72074" in set(addr["label"])
    assert addr["address_id"].is_unique


def test_campus_file_and_match(tmp_path: Path) -> None:
    c = campus.load_campus(REPO / "config" / "config.yaml")
    dest = campus.destinations(c)
    assert dest.crs.to_string() == CRS
    assert set(dest["destination_type"]) == {"campus_site", "mensa", "university_sports"}
    uni = gpd.GeoDataFrame(geometry=[dest.geometry.iloc[0].buffer(10)], crs=CRS)
    dist = campus.match_osm(dest, uni)
    assert dist[0] == 0 and np.isfinite(dist).all()
    assert np.isinf(campus.match_osm(dest, uni.iloc[:0])).all()
    with pytest.raises(ConfigError, match="not found"):
        campus.load_campus(tmp_path / "config.yaml")
    (tmp_path / "campus.yaml").write_text(
        "match_radius_m: 1\nsites: {a: {name: A, point: [9, 48]}}\ndefault_mix: {b: 1}\n"
        "programmes: {p: {label: {en: P}, sites: [a]}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown sites"):
        campus.load_campus(tmp_path / "config.yaml")


def test_address_cells_use_the_zensus_ids() -> None:
    grid = pd.DataFrame({"cell_id": ["CRS3035RES100mN2822800E4250900"]})
    # centre of that cell, and a point in the next cell to the east
    pts = gpd.GeoSeries([Point(4250950, 2822850), Point(4251050, 2822850)], crs="EPSG:3035").to_crs(
        CRS
    )
    assert zensus.cell_ids(pts)["cell_id"].tolist() == [
        "CRS3035RES100mN2822800E4250900",
        "CRS3035RES100mN2822800E4251000",
    ]
    extra = zensus.address_cells(grid, pts)
    assert extra.to_dict("records") == [
        {
            "cell_id": "CRS3035RES100mN2822800E4251000",
            "x": 4251050.0,
            "y": 2822850.0,
            "population": 0,
        }
    ]
