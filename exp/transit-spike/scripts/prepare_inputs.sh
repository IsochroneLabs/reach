#!/usr/bin/env bash
# Clip OSM (osmium) and GTFS (duckdb) to the spike areas in config/areas.json.
# Usage: prepare_inputs.sh <area>   (area = routing | test_clip). Output: data/spike/<area>/.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
AREA=$1
RAW=data/spike/raw/20261121
OUT=data/spike/$AREA
mkdir -p "$OUT/gtfs"
read -r MINX MINY MAXX MAXY < <(python3 -I -c "import json;print(*json.load(open('exp/transit-spike/config/areas.json'))['$AREA'])")
/usr/bin/time -l osmium extract -O -s smart -b "$MINX,$MINY,$MAXX,$MAXY" -o "$OUT/osm.pbf" "$RAW/tuebingen-regbez-latest.osm.pbf" 2>&1 \
  | grep -E 'real|maximum resident' || true
printf "SET VARIABLE src='data/spike/gtfs'; SET VARIABLE dst='%s';
SET VARIABLE min_lon=%s; SET VARIABLE min_lat=%s; SET VARIABLE max_lon=%s; SET VARIABLE max_lat=%s;
.read exp/transit-spike/sql/gtfs_clip.sql
" "$OUT/gtfs" "$MINX" "$MINY" "$MAXX" "$MAXY" | duckdb 2>/dev/null
(cd "$OUT/gtfs" && rm -f ../gtfs.zip && zip -q -j ../gtfs.zip ./*.txt)
ls -la "$OUT"
