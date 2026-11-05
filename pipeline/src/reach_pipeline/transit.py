"""Scheduled departures per stop on the reference weekday (methodology §3, arch. §6.3)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from reach_pipeline.errors import StageValidationError

_READER = "read_csv(?, header=true, all_varchar=true)"


def _columns(con: duckdb.DuckDBPyConnection, path: Path) -> set[str]:
    return {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {_READER}", [str(path)]).fetchall()}


def departures_per_stop(gtfs_dir: Path, service_ids: set[str]) -> pd.DataFrame:
    """`stop_id`, `departures`: stop events of trips whose service runs on the reference day.

    Streams `stop_times.txt` with DuckDB (never loaded whole into pandas). An event counts as a
    departure unless boarding is impossible there (`pickup_type` 1, e.g. the last stop of a
    trip). Stops without departures are absent.
    """
    stop_times, trips = gtfs_dir / "stop_times.txt", gtfs_dir / "trips.txt"
    con = duckdb.connect()
    missing = {"trip_id", "stop_id"} - _columns(con, stop_times)
    missing |= {f"trips.txt:{c}" for c in {"trip_id", "service_id"} - _columns(con, trips)}
    if missing:
        raise StageValidationError(f"GTFS: missing columns {sorted(missing)}")
    boards = (
        "coalesce(st.pickup_type, '') <> '1'"
        if "pickup_type" in _columns(con, stop_times)
        else "true"
    )
    con.register("active", pd.DataFrame({"service_id": sorted(service_ids)}, dtype=str))
    return con.execute(
        f"""
        SELECT st.stop_id, count(*)::INTEGER AS departures
        FROM {_READER} AS st
        JOIN {_READER} AS t USING (trip_id)
        JOIN active USING (service_id)
        WHERE {boards}
        GROUP BY st.stop_id
        ORDER BY st.stop_id
        """,
        [str(stop_times), str(trips)],
    ).df()
