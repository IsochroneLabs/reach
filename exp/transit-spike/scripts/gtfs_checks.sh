#!/usr/bin/env bash
# Runs the GTFS checks of the T1 spike with the duckdb CLI; output goes to results/.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
cat exp/transit-spike/sql/gtfs_service.sql exp/transit-spike/sql/gtfs_night.sql \
  | duckdb 2>/dev/null | tee exp/transit-spike/results/gtfs_checks.txt
