"""Rough destination counts per type in the routing area (sizing only; ignores the clip polygon,
access points and name matching). Stdlib only. Usage: python3 -I count_destinations.py in.geojsonseq"""

import json
import sys
from collections import Counter

RULES = {  # type: (any of these key=value, required key=value or None, excluded access values)
    "library": ([("amenity", "library")], None),
    "grocery": ([("shop", "supermarket")], None),
    "pharmacy": ([("amenity", "pharmacy")], None),
    "doctor": ([("amenity", "doctors")], None),
    "main_station": ([("railway", "station")], ("name", "Tübingen Hbf")),
    "park": ([("leisure", "park")], None),
    "gym": ([("leisure", "fitness_centre")], None),
    "climbing": ([("leisure", "sports_centre"), ("leisure", "pitch")], ("sport", "climbing")),
    "swimming": ([("leisure", "sports_centre"), ("leisure", "water_park"),
                  ("leisure", "swimming_pool")], ("sport", "swimming")),
    "sports_club": ([("leisure", "sports_centre")], None),
    "music": ([("amenity", "music_school"), ("amenity", "music_venue")], None),
    "nightlife": ([("amenity", v) for v in ("bar", "pub", "nightclub", "biergarten")], None),
    "cinema_theatre": ([("amenity", "cinema"), ("amenity", "theatre")], None),
    "place_of_worship": ([("amenity", "place_of_worship")], None),
}
counts = Counter()
for line in open(sys.argv[1], encoding="utf-8"):
    p = json.loads(line.lstrip("\x1e"))["properties"]
    if p.get("access") in ("private", "no"):
        continue
    for name, (anyof, req) in RULES.items():
        if any(p.get(k) == v for k, v in anyof):
            if req and req[1] not in str(p.get(req[0], "")).split(";") and not (
                    req[0] == "name" and str(p.get("name", "")).startswith("Tübingen Hauptbahnhof")):
                continue
            counts[name] += 1
for name in RULES:
    print(f"{name:18s} {counts[name]:5d}")
print(f"{'total (OSM types)':18s} {sum(counts.values()):5d}")
