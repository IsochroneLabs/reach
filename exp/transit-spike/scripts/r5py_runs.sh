#!/usr/bin/env bash
# r5py measurements in the spike image, container limited to 4 GB (budget next to PostGIS,
# Valhalla idle and the API under A4). Usage: r5py_runs.sh <area> <run> ; see case below.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
AREA=$1; RUN=$2; R=exp/transit-spike/results; OUT=data/spike/r5py; mkdir -p $OUT
NAME=r5py-$AREA-$RUN${TAG:-}
args=(--osm /data/$AREA/osm.pbf --gtfs /data/$AREA/gtfs.zip
      --origins /data/work/${ORIGINS:-origins_r5.csv} --destinations /data/work/${DESTS:-destinations.csv})
case $RUN in
  evening)  extra=(--mode depart --time 2026-11-24T18:00 --window-min 10 --percentiles 50) ;;
  window60) extra=(--mode depart --time 2026-11-24T07:10 --window-min 60 --percentiles 25,50,75) ;;
  campus_arrive) extra=(--mode arrive --time 2026-11-24T08:10 --lookback-min 60) ;;
  night)    extra=(--mode depart --time ${TIME:-2026-11-28T00:30} --window-min 1 --percentiles 50) ;;
  bike)     extra=(--mode depart --time 2026-11-24T18:00 --window-min 10 --percentiles 50 --access BICYCLE) ;;
  legs)     extra=(--mode legs --time 2026-11-24T18:00 --window-min 10 --max-pairs ${MAXPAIRS:-500}) ;;
esac
docker rm -f $NAME >/dev/null 2>&1 || true
START=$(date +%s)
docker run -d --name $NAME --memory 4g -v "$PWD/data/spike:/data" -v "$PWD/exp/transit-spike/r5py:/app:ro" \
  reach-spike-r5py:1.1.7 python /app/r5py_matrix.py "${args[@]}" "${extra[@]}" --out /data/r5py/$AREA-$RUN${TAG:-}.parquet >/dev/null
exp/transit-spike/scripts/memwatch.sh $NAME $R/r5py_${AREA}_${RUN}${TAG:-}_mem.txt >/dev/null & MW=$!
CODE=$(docker wait $NAME); END=$(date +%s)
kill $MW 2>/dev/null; wait $MW 2>/dev/null || true
docker logs $NAME > $R/r5py_${AREA}_${RUN}${TAG:-}.log 2>&1
echo "{\"area\": \"$AREA\", \"run\": \"$RUN\", \"exit\": $CODE, \"wall_s\": $((END-START))}" | tee -a $R/r5py_runs.jsonl
grep -E 'stats|Error|Exception' $R/r5py_${AREA}_${RUN}${TAG:-}.log | tail -3 | cut -c1-600
cat $R/r5py_${AREA}_${RUN}${TAG:-}_mem.txt
docker rm $NAME >/dev/null
