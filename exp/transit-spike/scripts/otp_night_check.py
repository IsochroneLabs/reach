"""Night check against the local OTP: transit-only itineraries for P4 (Sat 00:30, i.e. GTFS
service day Friday with times >= 24:00). Stdlib only."""

import json
import urllib.request

Q = """{ planConnection(origin: {location: {coordinate: {latitude: 48.51936, longitude: 9.05859}}},
  destination: {location: {coordinate: {latitude: 48.54249, longitude: 9.06474}}},
  dateTime: {earliestDeparture: "%s"}, first: 4,
  modes: {transitOnly: true, transit: {access: [WALK], egress: [WALK], transfer: [WALK]}}) {
  edges { node { start end duration legs { mode route { shortName }
    start { scheduledTime } end { scheduledTime } from { name } } } } } }"""
for when in ("2026-11-28T00:30+01:00", "2026-11-28T01:30+01:00", "2026-11-25T00:30+01:00"):
    req = urllib.request.Request("http://localhost:18080/otp/gtfs/v1",
                                 json.dumps({"query": Q % when}).encode(),
                                 {"Content-Type": "application/json"})
    data = json.load(urllib.request.urlopen(req, timeout=60))
    print("==", when)
    for e in data["data"]["planConnection"]["edges"]:
        n = e["node"]
        legs = [f"{x['mode']} {x['route']['shortName'] if x['route'] else ''} "
                f"{x['start']['scheduledTime'][11:16]} ({x['from']['name']})"
                for x in n["legs"] if x["mode"] != "WALK"]
        print(f"  {n['start'][11:16]}-{n['end'][11:16]} {round(n['duration'] / 60)} min: {legs}")
