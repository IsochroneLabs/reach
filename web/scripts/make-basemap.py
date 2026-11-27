"""Build the simplified basemap GeoJSON from an `osmium export` stream (D5, N18).

The source is public OpenStreetMap data, never fetched at runtime. Extract and filter the PBF
first (the commands are in `web/public/basemap/README.md`), then:

    uv run --package reach-pipeline python web/scripts/make-basemap.py \
        --input /tmp/basemap/base.geojsonseq \
        --output web/public/basemap/tuebingen.geojson

Only roads, water, green spaces and rail are kept; coordinates are simplified and rounded, so the
file stays small enough for the static build.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import shape

MAJOR = {
    "motorway", "trunk", "primary", "secondary",
    "motorway_link", "trunk_link", "primary_link", "secondary_link",
}  # fmt: skip
MINOR = {"tertiary", "tertiary_link", "unclassified", "residential", "living_street", "pedestrian"}
GREEN = {"meadow", "grass", "orchard", "vineyard", "cemetery"}


def classify(tags: dict[str, str]) -> tuple[str, str] | None:
    highway = tags.get("highway")
    if highway:
        if highway in MAJOR:
            return "road", "major"
        if highway in MINOR:
            return "road", "minor"
        return None
    if tags.get("railway") in {"rail", "light_rail", "tram"}:
        return "rail", "rail"
    if tags.get("waterway"):
        return "waterway", tags["waterway"]
    if tags.get("natural") == "water" or tags.get("water") or tags.get("landuse") == "reservoir":
        return "water", "water"
    if tags.get("natural") == "wood" or tags.get("landuse") == "forest":
        return "forest", "forest"
    if tags.get("landuse") in GREEN or tags.get("leisure") in {"park", "garden", "playground"}:
        return "green", "green"
    return None


def clean(coords, digits: int = 5) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for x, y in coords:
        point = (round(x, digits), round(y, digits))
        if not out or out[-1] != point:
            out.append(point)
    return out


def tidy(geom) -> dict | None:
    if geom.is_empty:
        return None
    if geom.geom_type == "LineString":
        line = clean(geom.coords)
        return {"type": "LineString", "coordinates": line} if len(line) >= 2 else None
    if geom.geom_type == "MultiLineString":
        parts = [clean(g.coords) for g in geom.geoms]
        parts = [p for p in parts if len(p) >= 2]
        return {"type": "MultiLineString", "coordinates": parts} if parts else None
    polygons = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        return None
    rings = []
    for polygon in polygons:
        shell = clean(polygon.exterior.coords)
        if len(shell) < 4:
            continue
        holes = [h for ring in polygon.interiors if len(h := clean(ring.coords)) >= 4]
        rings.append([shell, *holes])
    if not rings:
        return None
    if geom.geom_type == "Polygon":
        return {"type": "Polygon", "coordinates": rings[0]}
    return {"type": "MultiPolygon", "coordinates": rings}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path, help="GeoJSONSeq from `osmium export`")
    ap.add_argument("--output", type=Path, default=Path("web/public/basemap/tuebingen.geojson"))
    args = ap.parse_args()

    features = []
    counts: dict[str, int] = {}
    with args.input.open(encoding="utf-8") as f:
        for line in f:
            line = line.lstrip("\x1e").strip()
            if not line:
                continue
            item = json.loads(line)
            kind = classify(item["properties"])
            if kind is None:
                continue
            name, sub = kind
            geom = shape(item["geometry"])
            if name in {"green", "forest"} and geom.area < 8e-8:  # < ~1000 m²
                continue
            tolerance = 0.00005 if name in {"water", "forest", "green"} else 0.00002
            geometry = tidy(geom.simplify(tolerance, preserve_topology=True))
            if geometry is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {"kind": name, "class": sub},
                    "geometry": geometry,
                }
            )
            counts[name] = counts.get(name, 0) + 1

    collection = {"type": "FeatureCollection", "features": features}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"{len(features)} features, {args.output.stat().st_size / 1e6:.1f} MB: {counts}")


if __name__ == "__main__":
    main()
