"""Compare OTP and r5py transit times for the evening window (Tue 2026-11-24 18:00, depart at)
on the OTP candidate pairs. Runs in the r5py spike image (pandas). Two OTP readings:
  otp_duration = itinerary duration (OTP shifts the start to just catch the vehicle, so the wait
                 at home is NOT included),
  otp_from_1800 = end - 18:00 (includes the wait at home; comparable to R5's travel time, which
                 counts from the departure minute; R5 = median over 18:00-18:09).
Usage: python compare_engines.py <otp_full_evening.csv> <routing-evening.parquet> <out.json>"""

import json
import sys

import pandas as pd

otp = pd.read_csv(sys.argv[1], usecols=["from_id", "to_id", "duration_s", "start", "end", "transfers", "legs"])
otp = otp.dropna(subset=["duration_s"])
t0 = pd.Timestamp("2026-11-24T18:00:00+01:00")
otp["otp_duration"] = otp["duration_s"] / 60
otp["otp_from_1800"] = (pd.to_datetime(otp["end"]) - t0).dt.total_seconds() / 60
otp["walk_only"] = ~otp["legs"].str.contains('"transitLeg"|"BUS"|"RAIL"|"TRAM"', regex=True)
r5 = pd.read_parquet(sys.argv[2]).rename(columns={"travel_time": "r5"})
m = otp.merge(r5, on=["from_id", "to_id"], how="inner").dropna(subset=["r5"])
out = {"pairs_compared": int(len(m)), "otp_walk_only_share": round(float(otp["walk_only"].mean()), 3)}
for col in ("otp_from_1800", "otp_duration"):
    d = m["r5"] - m[col]
    out[col] = {
        "median_diff_min": round(float(d.median()), 2),
        "mean_abs_diff_min": round(float(d.abs().mean()), 2),
        "p90_abs_diff_min": round(float(d.abs().quantile(0.9)), 2),
        "share_within_3min": round(float((d.abs() <= 3).mean()), 3),
        "share_within_5min": round(float((d.abs() <= 5).mean()), 3),
    }
transit = m[~m["walk_only"]]
d = transit["r5"] - transit["otp_from_1800"]
out["transit_pairs_only"] = {"pairs": int(len(transit)), "median_diff_min": round(float(d.median()), 2),
                             "share_within_5min": round(float((d.abs() <= 5).mean()), 3)}
print(json.dumps(out, indent=2))
open(sys.argv[3], "w").write(json.dumps(out, indent=2))
