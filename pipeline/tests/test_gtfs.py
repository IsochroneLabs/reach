"""GTFS stops, feed validity, active services and the reference weekday (holidays + exceptions)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from reach_pipeline import gtfs
from reach_pipeline.config import ReferenceDay
from reach_pipeline.errors import StageValidationError

DAYS = "monday,tuesday,wednesday,thursday,friday,saturday,sunday"


def _write(d: Path, name: str, text: str) -> None:
    (d / name).write_text(text.strip() + "\n", encoding="utf-8")


@pytest.fixture
def feed(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "stops.txt",
        """
stop_id,stop_name,stop_lat,stop_lon,location_type
"s1","Platform 1","48.52","9.05",""
"s2","Platform 2","48.52","9.06","0"
"st","Station","48.52","9.055","1"
""",
    )
    # weekday service all of November; a special service only via calendar_dates
    _write(
        tmp_path,
        "calendar.txt",
        f"""
service_id,{DAYS},start_date,end_date
"wk","1","1","1","1","1","0","0","20261101","20261130"
"sp","0","0","0","0","0","0","0","20261101","20261130"
""",
    )
    _write(
        tmp_path,
        "calendar_dates.txt",
        """
service_id,date,exception_type
"wk","20261110","2"
"sp","20261110","1"
"wk","20261117","2"
""",
    )
    _write(
        tmp_path,
        "feed_info.txt",
        """
feed_publisher_name,feed_start_date,feed_end_date
"NVBW","20261101","20261130"
""",
    )
    return tmp_path


def _ref(**kw) -> ReferenceDay:
    data = {
        "weekday": "tuesday",
        "covered": {"from": "2026-10-01", "to": "2027-01-31"},
        "public_holidays": [],
        "school_holidays": [],
    }
    return ReferenceDay.model_validate({**data, **kw})


def test_read_stops_keeps_stops_and_platforms(feed: Path) -> None:
    stops = gtfs.read_stops(feed / "stops.txt")
    assert sorted(stops["stop_id"]) == ["s1", "s2"]
    assert stops.crs.to_string() == "EPSG:25832"
    assert stops.geometry.x.between(490_000, 510_000).all()  # UTM 32N near Tübingen


def test_active_services_apply_exceptions(feed: Path) -> None:
    cal, dates = gtfs.read_calendar(feed)
    assert gtfs.active_service_ids(cal, dates, date(2026, 11, 3)) == {"wk"}
    assert gtfs.active_service_ids(cal, dates, date(2026, 11, 10)) == {"sp"}  # removed + added
    assert gtfs.active_service_ids(cal, dates, date(2026, 11, 17)) == set()  # removed only
    assert gtfs.active_service_ids(cal, dates, date(2026, 11, 7)) == set()  # Saturday


def test_feed_validity_from_feed_info(feed: Path) -> None:
    cal, dates = gtfs.read_calendar(feed)
    assert gtfs.feed_validity(feed, cal, dates) == (date(2026, 11, 1), date(2026, 11, 30))
    (feed / "feed_info.txt").unlink()
    assert gtfs.feed_validity(feed, cal, dates) == (date(2026, 11, 1), date(2026, 11, 30))


def test_reference_weekday_skips_holidays_and_empty_days(feed: Path) -> None:
    cal, dates = gtfs.read_calendar(feed)
    args = (date(2026, 11, 1), date(2026, 11, 30), cal, dates)
    assert gtfs.reference_weekday(*args, _ref(), date(2026, 11, 2)) == date(2026, 11, 3)
    # 3 Nov is a school holiday, 10 Nov is a public holiday, 17 Nov has no service → 24 Nov
    cfg = _ref(
        public_holidays=["2026-11-10"],
        school_holidays=[{"from": "2026-11-02", "to": "2026-11-06"}],
    )
    assert gtfs.reference_weekday(*args, cfg, date(2026, 11, 2)) == date(2026, 11, 24)
    # the run date is after the start of the feed: no earlier day is chosen
    assert gtfs.reference_weekday(*args, _ref(), date(2026, 11, 4)) == date(2026, 11, 10)
    with pytest.raises(StageValidationError, match="no regular tuesday"):
        gtfs.reference_weekday(*args, _ref(), date(2026, 11, 25))


def test_missing_column_fails(feed: Path) -> None:
    _write(feed, "calendar_dates.txt", "service_id,date\n")
    with pytest.raises(StageValidationError, match="exception_type"):
        gtfs.read_calendar(feed)
