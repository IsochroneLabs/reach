"""Build ``university.geojson`` from an ``osmium export`` stream (D5/N28).

Keeps university buildings of the Tübingen extract: ``amenity=university``,
``building=university``, operator Universität Tübingen / Universitätsklinikum Tübingen, or a
building whose name matches the campus patterns in ``config/campus.yaml`` and lies within 2.5 km
of a campus site. Each feature gets ``site`` = nearest campus site and ``name``.

Run with the pipeline environment:

    osmium tags-filter /tmp/tuebingen.osm.pbf -o /tmp/buildings.osm.pbf \\
        w/building w/amenity=university w/operator
    osmium export /tmp/buildings.osm.pbf -f geojsonseq -o /tmp/buildings.geojsonseq \\
        --geometry-types=polygon -a type,id
    uv run --package reach-pipeline python web/scripts/make-university.py \\
        --input /tmp/buildings.geojsonseq --output web/public/basemap/university.geojson
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml
from pyproj import Transformer
from shapely.geometry import shape

OPERATORS = ("universität tübingen", "universitätsklinikum tübingen")


def clean(coords, digits: int = 5) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for x, y in coords:
        point = (round(x, digits), round(y, digits))
        if not out or out[-1] != point:
            out.append(point)
    return out


def tidy(geom) -> dict | None:
    polygons = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    rings = []
    for polygon in polygons:
        shell = clean(polygon.exterior.coords)
        if len(shell) < 4:
            continue
        holes = [h for ring in polygon.interiors if len(h := clean(ring.coords)) >= 4]
        rings.append([shell, *holes])
    if not rings:
        return None
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": rings[0]}
    return {"type": "MultiPolygon", "coordinates": rings}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--config", type=Path, default=Path("config/campus.yaml"))
    ap.add_argument("--output", type=Path, default=Path("web/public/basemap/university.geojson"))
    args = ap.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    patterns = {
        site: [re.compile(p, re.I) for p in regexes]
        for site, regexes in cfg["alma"]["building_sites"].items()
    }
    to_metric = Transformer.from_crs(4326, 25832, always_xy=True)
    sites = {key: to_metric.transform(*value["point"]) for key, value in cfg["sites"].items()}

    def nearest(x: float, y: float) -> tuple[str, float]:
        site, (sx, sy) = min(
            sites.items(), key=lambda item: (item[1][0] - x) ** 2 + (item[1][1] - y) ** 2
        )
        return site, ((sx - x) ** 2 + (sy - y) ** 2) ** 0.5

    features = []
    counts: dict[str, int] = {}
    with args.input.open(encoding="utf-8") as f:
        for line in f:
            line = line.lstrip("\x1e").strip()
            if not line:
                continue
            item = json.loads(line)
            tags = item["properties"]
            name = (tags.get("name") or "").strip()
            operator = (tags.get("operator") or "").lower()
            tagged = (
                tags.get("amenity") == "university"
                or tags.get("building") == "university"
                or any(op in operator for op in OPERATORS)
            )
            matched = (
                any(rx.search(name) for regexes in patterns.values() for rx in regexes)
                if name
                else False
            )
            if not (tagged or matched) or "hochschule reutlingen" in name.lower():
                continue
            geom = shape(item["geometry"])
            if geom.is_empty:
                continue
            x, y = to_metric.transform(geom.centroid.x, geom.centroid.y)
            site, distance = nearest(x, y)
            if distance > 2500:
                continue
            geometry = tidy(geom.simplify(0.00002, preserve_topology=True))
            if geometry is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "site": site,
                        "name": name or tags.get("amenity") or "Universität",
                    },
                    "geometry": geometry,
                }
            )
            counts[site] = counts.get(site, 0) + 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"{len(features)} buildings, {args.output.stat().st_size / 1e6:.2f} MB: {counts}")


if __name__ == "__main__":
    main()
