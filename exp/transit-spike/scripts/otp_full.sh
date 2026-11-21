#!/usr/bin/env bash
# Full-city OTP run: every candidate pair in its trip window (reference dates of 21 Nov 2026).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
W=data/spike/work; R=exp/transit-spike/results; WORKERS=${WORKERS:-4}
URL=http://localhost:18080/otp/gtfs/v1
python3 -I exp/transit-spike/scripts/split_pairs.py $W/pairs_all.csv $W
exp/transit-spike/scripts/memwatch.sh otp-serve $R/otp_full_mem.txt >/dev/null & MW=$!
run() { printf "%s " "$1"; python3 -I exp/transit-spike/scripts/otp_batch.py "$W/pairs_$1.csv" "$W/otp_full_$1.csv" --time "$2" $3 --workers "$WORKERS" --url $URL; }
{
run morning_lecture 2026-11-24T08:10+01:00 --arrive-by
run midday          2026-11-24T12:00+01:00 ""
run evening         2026-11-24T18:00+01:00 ""
run night_return    2026-11-28T00:30+01:00 ""
run weekend_station 2026-11-28T10:00+01:00 ""
} | tee $R/otp_full.txt
kill $MW; wait $MW 2>/dev/null || true
cat $R/otp_full_mem.txt
