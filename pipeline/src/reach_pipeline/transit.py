"""Scheduled departures per stop on a reference date (meth. §4 reliability; used from S1.6)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from reach_pipeline.errors import StageValidationError

_READER = "read_csv(?, header=true, all_varchar=true)"


def _columns(con: duckdb.DuckDBPyConnection, path: Path) -> set[str]:
    return {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {_READER}", [str(path)]).fetchall()}


def departures_per_stop(gtfs_dir: Path, service_ids: set[str]) -> pd.DataFrame:
    """`stop_id`, `departures`: stop events of trips whose service runs on the reference date.

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


def _seconds(sql_col: str) -> str:
    """GTFS `HH:MM:SS` (hours may exceed 23) as seconds after midnight of the service day."""
    return (
        f"(split_part({sql_col}, ':', 1)::INTEGER * 3600"
        f" + split_part({sql_col}, ':', 2)::INTEGER * 60"
        f" + split_part({sql_col}, ':', 3)::INTEGER)"
    )


def departures_in_window(
    gtfs_dir: Path,
    services_day: set[str],
    services_before: set[str],
    start_s: int,
    end_s: int,
) -> pd.DataFrame:
    """`stop_id`, `departures`: boardable stop events between `start_s` and `end_s` (seconds after
    midnight of the reference date). Trips of the previous service day count with their time
    minus 24 h, so a night bus at "24:40" of Friday is a departure at 00:40 on Saturday."""
    stop_times, trips = gtfs_dir / "stop_times.txt", gtfs_dir / "trips.txt"
    con = duckdb.connect()
    cols = _columns(con, stop_times)
    missing = {"trip_id", "stop_id", "departure_time"} - cols
    if missing:
        raise StageValidationError(f"GTFS: missing columns {sorted(missing)}")
    boards = "coalesce(st.pickup_type, '') <> '1'" if "pickup_type" in cols else "true"
    active = pd.DataFrame(
        {
            "service_id": [*sorted(services_day), *sorted(services_before)],
            "shift": [0] * len(services_day) + [86400] * len(services_before),
        }
    ).astype({"service_id": str})
    con.register("active", active)
    return con.execute(
        f"""
        SELECT st.stop_id, count(*)::INTEGER AS departures
        FROM {_READER} AS st
        JOIN {_READER} AS t USING (trip_id)
        JOIN active AS a USING (service_id)
        WHERE {boards} AND coalesce(st.departure_time, '') <> ''
          AND {_seconds("st.departure_time")} - a.shift BETWEEN ? AND ?
        GROUP BY st.stop_id
        ORDER BY st.stop_id
        """,
        [str(stop_times), str(trips), start_s, end_s],
    ).df()
