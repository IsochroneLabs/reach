"""T1 spike: batch transit trips against a local OTP 2.x server (GTFS GraphQL API).

Stdlib only; runs on the host against http://localhost:8080 (the OTP container of this spike,
never a public journey planner). Input CSV columns: from_id, from_lon, from_lat, to_id, to_lon,
to_lat. Output CSV: one row per pair with the duration of the earliest-arriving itinerary
(depart) or the latest-departing one that arrives in time (arrive), and its legs as JSON.
Usage: python3 -I otp_batch.py pairs.csv out.csv --time 2026-11-24T08:10+01:00 --arrive-by
       [--access WALK|BICYCLE_PARKING] [--workers 4]
"""

import argparse
import concurrent.futures as cf
import csv
import json
import statistics
import sys
import time
import urllib.request

QUERY = """
query($o: PlanCoordinateInput!, $d: PlanCoordinateInput!, $dt: PlanDateTimeInput!,
      $access: [PlanAccessMode!]) {
  planConnection(origin: {location: {coordinate: $o}}, destination: {location: {coordinate: $d}},
                 dateTime: $dt, first: 3,
                 modes: {direct: [WALK], transit: {access: $access, egress: [WALK], transfer: [WALK]}}) {
    edges { node {
      start end duration waitingTime walkTime numberOfTransfers
      legs { mode duration distance start { scheduledTime } end { scheduledTime }
             from { name } to { name } route { shortName } }
    } }
  }
}"""


def plan(url: str, pair: dict, when: str, arrive_by: bool, access: str) -> dict:
    variables = {
        "o": {"latitude": float(pair["from_lat"]), "longitude": float(pair["from_lon"])},
        "d": {"latitude": float(pair["to_lat"]), "longitude": float(pair["to_lon"])},
        "dt": {"latestArrival" if arrive_by else "earliestDeparture": when},
        "access": [access],
    }
    body = json.dumps({"query": QUERY, "variables": variables}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    ms = (time.perf_counter() - t0) * 1000
    edges = ((data.get("data") or {}).get("planConnection") or {}).get("edges") or []
    its = [e["node"] for e in edges]
    best = None
    if its:
        # depart: earliest arrival; arrive-by: latest departure (both = shortest wait at home)
        best = max(its, key=lambda i: i["start"]) if arrive_by else min(its, key=lambda i: i["end"])
    return {
        "from_id": pair["from_id"], "to_id": pair["to_id"], "ms": round(ms, 1),
        "duration_s": best["duration"] if best else "", "start": best["start"] if best else "",
        "end": best["end"] if best else "", "transfers": best["numberOfTransfers"] if best else "",
        "legs": json.dumps(best["legs"], ensure_ascii=False) if best else "",
        "errors": json.dumps(data.get("errors"))[:300] if data.get("errors") else "",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs")
    ap.add_argument("out")
    ap.add_argument("--time", required=True)
    ap.add_argument("--arrive-by", action="store_true")
    ap.add_argument("--access", default="WALK")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--url", default="http://localhost:8080/otp/gtfs/v1")
    a = ap.parse_args()
    pairs = list(csv.DictReader(open(a.pairs, encoding="utf-8")))
    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(lambda p: plan(a.url, p, a.time, a.arrive_by, a.access), pairs))
    wall = time.perf_counter() - t0
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    ms = [r["ms"] for r in rows]
    found = sum(1 for r in rows if r["duration_s"] != "")
    print(json.dumps({
        "pairs": len(rows), "found": found, "workers": a.workers, "wall_s": round(wall, 1),
        "pairs_per_s": round(len(rows) / wall, 1), "ms_median": round(statistics.median(ms), 1),
        "ms_p90": round(sorted(ms)[int(0.9 * len(ms)) - 1], 1),
        "errors": sum(1 for r in rows if r["errors"]),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
