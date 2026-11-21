"""Build destinations.csv and the candidate pairs per origin for the spike (stdlib only).

Destinations: OSM types as in count_destinations.py (parks by centroid, not access points) plus the
campus.yaml points. Candidates per origin and type: the 2*k nearest by straight line within
search_radius (k from config: campus/university_sports all, main_station 1, others 3), mirroring
"prefilter by straight line, pick nearest k by travel time" (review finding 18).
Usage: python3 -I gen_pairs.py <dest.geojsonseq> <origins.csv> <outdir>
"""

import csv
import json
import math
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from count_destinations import RULES  # noqa: E402

CAMPUS = {  # config/campus.yaml points corrected to the OSM buildings (review finding 7)
    "campus_site": [("tal", 9.0581, 48.5247), ("morgenstelle", 9.0352, 48.5371),
                    ("sand", 9.0712, 48.5349), ("schnarrenberg", 9.0375, 48.5303)],
    "mensa": [("wilhelmstrasse", 9.0609, 48.5259), ("morgenstelle", 9.0359, 48.5355),
              ("prinz_karl", 9.0561, 48.5210), ("shedhalle", 9.0655, 48.5273)],
    "university_sports": [("sports_institute", 9.0727, 48.5293)],
}
K = {"campus_site": None, "mensa": 3, "university_sports": None, "main_station": 1}
RADIUS_M = 6000


def dist(a, b):
    kx = 111320 * math.cos(math.radians(48.52))
    return math.hypot((a[0] - b[0]) * kx, (a[1] - b[1]) * 110540)


def centre(geom):
    c = geom["coordinates"]
    if geom["type"] == "Point":
        return c[0], c[1]
    ring = {"LineString": c, "Polygon": c[0]}.get(geom["type"]) or c[0][0]
    return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)


dests = [(f"{t}:{n}", t, lon, lat) for t, pts in CAMPUS.items() for n, lon, lat in pts]
for i, line in enumerate(open(sys.argv[1], encoding="utf-8")):
    f = json.loads(line.lstrip("\x1e"))
    p = f["properties"]
    if p.get("access") in ("private", "no"):
        continue
    for t, (anyof, req) in RULES.items():
        if any(p.get(k) == v for k, v in anyof):
            if req and req[1] not in str(p.get(req[0], "")).split(";"):
                if not (t == "main_station" and str(p.get("name", "")).startswith("Tübingen Hauptbahnhof")):
                    continue
            lon, lat = centre(f["geometry"])
            dests.append((f"{t}:{i}", t, lon, lat))
origins = list(csv.DictReader(open(sys.argv[2], encoding="utf-8")))
out = sys.argv[3]
with open(f"{out}/destinations.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "type", "lon", "lat"])
    w.writerows(dests)
with open(f"{out}/origins_r5.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "lon", "lat", "kind"])
    w.writerows((o["cell_id"], o["lon"], o["lat"], o["kind"]) for o in origins)
by_type = {}
for d in dests:
    by_type.setdefault(d[1], []).append(d)
n_pairs = 0
with open(f"{out}/pairs_all.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["from_id", "from_lon", "from_lat", "to_id", "to_lon", "to_lat", "type"])
    for o in origins:
        op = (float(o["lon"]), float(o["lat"]))
        for t, ds in by_type.items():
            k = K.get(t, 3)
            near = sorted(((dist(op, (d[2], d[3])), d) for d in ds))
            near = [x for x in near if x[0] <= RADIUS_M] or near[:1]
            cand = near if k is None else near[: 2 * k]
            for _, d in cand:
                w.writerow([o["cell_id"], o["lon"], o["lat"], d[0], d[2], d[3], t])
                n_pairs += 1
print(json.dumps({"origins": len(origins), "destinations": len(dests),
                  "types": {t: len(v) for t, v in sorted(by_type.items())},
                  "candidate_pairs": n_pairs, "pairs_per_origin": round(n_pairs / len(origins), 1)}))
