"""osmium wrappers on a tiny OSM XML fixture (needs the osmium-tool binary, see README)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reach_pipeline import osm
from reach_pipeline.errors import ExternalError

FIXTURE = Path(__file__).parent / "fixtures" / "tiny.osm"


def test_filter_export_read(tmp_path: Path) -> None:
    exprs = [*osm.tag_expressions([{"shop": "supermarket"}, {"leisure": "park"}]), "w/highway"]
    filtered = osm.tags_filter(FIXTURE, tmp_path / "f.osm.pbf", exprs)
    feats = osm.read_export(osm.export(filtered, tmp_path / "f.geojsonseq", ["point", "polygon"]))
    assert sorted(feats["osm_id"]) == ["n5", "r20", "w10"]
    assert feats.crs.to_string() == "EPSG:25832"
    lines = osm.read_export(
        osm.export(filtered, tmp_path / "l.geojsonseq", ["linestring"]),
        where="highway IN ('footway')",
    )
    assert list(lines["osm_id"]) == ["w11"]


def test_extract_polygon(tmp_path: Path) -> None:
    polygon = tmp_path / "area.geojson"
    ring = [[9.0495, 48.5195], [9.0515, 48.5195], [9.0515, 48.5215], [9.0495, 48.5215]]
    geom = {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}
    polygon.write_text(json.dumps({"type": "Feature", "geometry": geom, "properties": {}}))
    clipped = osm.extract_polygon(FIXTURE, tmp_path / "c.osm.pbf", polygon)
    feats = osm.read_export(osm.export(clipped, tmp_path / "c.geojsonseq", ["point"]))
    assert list(feats["osm_id"]) == ["n5"]  # n9 lies outside the polygon


def test_osmium_error_is_external(tmp_path: Path) -> None:
    with pytest.raises(ExternalError, match="osmium tags-filter failed"):
        osm.tags_filter(tmp_path / "missing.pbf", tmp_path / "out.pbf", ["n/shop"])


def test_empty_export(tmp_path: Path) -> None:
    filtered = osm.tags_filter(FIXTURE, tmp_path / "f.osm.pbf", ["n/amenity=pharmacy"])
    assert osm.read_export(osm.export(filtered, tmp_path / "e.geojsonseq", ["point"])).empty
