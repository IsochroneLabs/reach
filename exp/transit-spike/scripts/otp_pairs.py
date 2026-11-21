"""Run the plausibility pairs (config/plausibility_pairs.csv) against the local OTP server:
once from the exact address and once from the home cell centroid. Stdlib only.
Usage: python3 -I otp_pairs.py <pairs.csv> <out.csv> [--url http://localhost:18080/otp/gtfs/v1]"""

import csv
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from otp_batch import plan  # noqa: E402

url = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:18080/otp/gtfs/v1"
rows = []
for p in csv.DictReader(open(sys.argv[1], encoding="utf-8")):
    when = f"{p['date']}T{p['time'][:5]}+01:00"
    arrive = p["rule"] == "arrive_by"
    night = p["trip_window"] == "night_return"
    for variant in ("address", "cell"):
        f_lon, f_lat, t_lon, t_lat = p["from_lon"], p["from_lat"], p["to_lon"], p["to_lat"]
        if variant == "cell":
            if night:
                t_lon, t_lat = p["home_cell_lon"], p["home_cell_lat"]
            else:
                f_lon, f_lat = p["home_cell_lon"], p["home_cell_lat"]
        pair = {"from_id": p["pair_id"], "to_id": variant, "from_lon": f_lon, "from_lat": f_lat,
                "to_lon": t_lon, "to_lat": t_lat}
        r = plan(url, pair, when, arrive, "WALK")
        legs = json.loads(r["legs"]) if r["legs"] else []
        r["summary"] = " | ".join(
            f"{leg['mode']}{' ' + leg['route']['shortName'] if leg.get('route') else ''} "
            f"{leg['start']['scheduledTime'][11:16]}-{leg['end']['scheduledTime'][11:16]}"
            for leg in legs)
        r["minutes"] = round(r["duration_s"] / 60, 1) if r["duration_s"] != "" else ""
        rows.append({k: r[k] for k in ("from_id", "to_id", "minutes", "start", "end",
                                       "transfers", "summary", "ms", "errors")})
with open(sys.argv[2], "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
for r in rows:
    print(r["from_id"], r["to_id"], r["minutes"], r["start"][11:16], r["end"][11:16], r["summary"], r["errors"])
