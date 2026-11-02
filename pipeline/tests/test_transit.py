"""Departures per stop on the reference day (DuckDB over stop_times.txt)."""

from __future__ import annotations

from pathlib import Path

import pytest

from reach_pipeline.errors import StageValidationError
from reach_pipeline.transit import departures_per_stop


def _feed(d: Path, stop_times: str, trips: str = "route_id,service_id,trip_id\nr,a,t1\nr,b,t2\n"):
    (d / "trips.txt").write_text(trips, encoding="utf-8")
    (d / "stop_times.txt").write_text(stop_times, encoding="utf-8")
    return d


def test_counts_active_trips_and_skips_no_pickup(tmp_path: Path) -> None:
    feed = _feed(
        tmp_path,
        "trip_id,stop_id,stop_sequence,pickup_type\n"
        "t1,s1,1,0\nt1,s2,2,\nt1,s3,3,1\n"  # s3: last stop, no boarding
        "t2,s1,1,0\n",  # t2's service b is not active
    )
    out = departures_per_stop(feed, {"a"}).set_index("stop_id")["departures"]
    assert out.to_dict() == {"s1": 1, "s2": 1}


def test_without_pickup_type_every_event_counts(tmp_path: Path) -> None:
    feed = _feed(tmp_path, "trip_id,stop_id,stop_sequence\nt1,s1,1\nt1,s2,2\nt2,s2,1\n")
    out = departures_per_stop(feed, {"a", "b"}).set_index("stop_id")["departures"]
    assert out.to_dict() == {"s1": 1, "s2": 2}


def test_no_active_service_gives_no_departures(tmp_path: Path) -> None:
    feed = _feed(tmp_path, "trip_id,stop_id,stop_sequence\nt1,s1,1\n")
    assert departures_per_stop(feed, set()).empty


def test_missing_column_fails(tmp_path: Path) -> None:
    feed = _feed(tmp_path, "trip_id,stop_id\nt1,s1\n", trips="trip_id\nt1\n")
    with pytest.raises(StageValidationError, match="trips.txt:service_id"):
        departures_per_stop(feed, {"a"})
