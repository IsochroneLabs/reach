"""Split pairs_all.csv by trip window (config/config.yaml destination_types.*.trip_window);
night_return pairs are reversed (destination -> home). Stdlib only.
Usage: python3 -I split_pairs.py <pairs_all.csv> <outdir>"""

import collections
import csv
import json
import sys

WINDOW = {"campus_site": "morning_lecture", "mensa": "midday", "library": "midday",
          "pharmacy": "midday", "doctor": "midday", "main_station": "weekend_station",
          "place_of_worship": "weekend_station", "nightlife": "night_return"}
rows = collections.defaultdict(list)
for r in csv.DictReader(open(sys.argv[1], encoding="utf-8")):
    w = WINDOW.get(r["type"], "evening")
    if w == "night_return":
        r = {"from_id": r["to_id"], "from_lon": r["to_lon"], "from_lat": r["to_lat"],
             "to_id": r["from_id"], "to_lon": r["from_lon"], "to_lat": r["from_lat"],
             "type": r["type"]}
    rows[w].append(r)
for w, rs in rows.items():
    with open(f"{sys.argv[2]}/pairs_{w}.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rs[0]))
        wr.writeheader()
        wr.writerows(rs)
print(json.dumps({w: len(rs) for w, rs in rows.items()}))
