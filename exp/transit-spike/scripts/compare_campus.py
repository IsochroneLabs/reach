"""Compare arrive-by 08:10 (Tue 2026-11-24) campus times: OTP latestArrival vs r5py emulation.
Both as "minutes before 08:10 the student must leave home". Runs in the r5py spike image.
Usage: python compare_campus.py <otp_full_morning_lecture.csv> <routing-campus_arrive.parquet> <out.json>"""

import json
import sys

import pandas as pd

otp = pd.read_csv(sys.argv[1], usecols=["from_id", "to_id", "start"]).dropna()
t = pd.Timestamp("2026-11-24T08:10:00+01:00")
otp["otp"] = (t - pd.to_datetime(otp["start"])).dt.total_seconds() / 60
r5 = pd.read_parquet(sys.argv[2]).rename(columns={"time_to_arrival_min": "r5"})
m = otp.merge(r5, on=["from_id", "to_id"])
d = m["r5"] - m["otp"]
out = {"pairs": int(len(m)), "median_diff_min": round(float(d.median()), 2),
       "mean_abs_diff_min": round(float(d.abs().mean()), 2),
       "p90_abs_diff_min": round(float(d.abs().quantile(0.9)), 2),
       "share_within_3min": round(float((d.abs() <= 3).mean()), 3),
       "share_within_5min": round(float((d.abs() <= 5).mean()), 3),
       "median_otp_min": round(float(m["otp"].median()), 1), "median_r5_min": round(float(m["r5"].median()), 1)}
print(json.dumps(out, indent=2))
open(sys.argv[3], "w").write(json.dumps(out, indent=2))
