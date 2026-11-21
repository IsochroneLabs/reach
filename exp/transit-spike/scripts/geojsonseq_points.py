"""Convert an osmium GeoJSON-sequence export to a CSV of points (lon, lat); polygons -> mean of
the outer ring. Stdlib only. Usage: python3 -I geojsonseq_points.py in.geojsonseq out.csv"""

import csv
import json
import sys


def point(geom: dict) -> tuple[float, float]:
    c = geom["coordinates"]
    if geom["type"] == "Point":
        return c[0], c[1]
    ring = c[0] if geom["type"] == "Polygon" else c[0][0]
    return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)


with open(sys.argv[1], encoding="utf-8") as src, open(sys.argv[2], "w", newline="") as dst:
    out = csv.writer(dst)
    out.writerow(["lon", "lat"])
    for line in src:
        out.writerow(point(json.loads(line.lstrip("\x1e"))["geometry"]))
