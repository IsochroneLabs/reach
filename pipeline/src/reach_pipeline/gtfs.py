"""GTFS: stops, feed validity, active services and the reference weekday (arch. §6.3, C7)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
import shapely

from reach_pipeline.config import ReferenceDay
from reach_pipeline.errors import StageValidationError

METRIC_CRS = "EPSG:25832"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _read(path: Path, columns: list[str]) -> pd.DataFrame:
    """Small GTFS table as strings; fails if a required column is missing."""
    con = duckdb.connect()
    df = con.execute("SELECT * FROM read_csv(?, header=true, all_varchar=true)", [str(path)]).df()
    missing = set(columns) - set(df.columns)
    if missing:
        raise StageValidationError(f"{path.name}: missing columns {sorted(missing)}")
    return df


def _date(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def read_stops(path: Path) -> gpd.GeoDataFrame:
    """Stops and platforms (`location_type` 0, empty or column absent) as points in EPSG:25832;
    fails if a stop has no valid coordinates."""
    con = duckdb.connect()
    reader = "read_csv(?, header=true, all_varchar=true)"
    columns = {
        r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {reader}", [str(path)]).fetchall()
    }
    missing = {"stop_id", "stop_name", "stop_lat", "stop_lon"} - columns
    if missing:
        raise StageValidationError(f"{path.name}: missing columns {sorted(missing)}")
    is_stop = "coalesce(location_type, '') IN ('', '0')" if "location_type" in columns else "true"
    df = con.execute(
        f"""
        SELECT stop_id, stop_name AS name,
               TRY_CAST(stop_lon AS DOUBLE) AS lon, TRY_CAST(stop_lat AS DOUBLE) AS lat
        FROM {reader}
        WHERE {is_stop}
        """,
        [str(path)],
    ).df()
    bad = df["lon"].isna() | df["lat"].isna()
    if bad.any():
        raise StageValidationError(
            f"{path.name}: {int(bad.sum())} stops without valid coordinates, "
            f"e.g. {df.loc[bad, 'stop_id'].head(3).tolist()}"
        )
    geom = gpd.GeoSeries(shapely.points(df["lon"], df["lat"]), crs="EPSG:4326")
    return gpd.GeoDataFrame(
        df[["stop_id", "name"]], geometry=geom.to_crs(METRIC_CRS).values, crs=METRIC_CRS
    )


def read_calendar(gtfs_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`calendar.txt` and `calendar_dates.txt` with parsed dates (either may be empty)."""
    cal_cols = ["service_id", *WEEKDAYS, "start_date", "end_date"]
    dates_cols = ["service_id", "date", "exception_type"]
    cal_path, dates_path = gtfs_dir / "calendar.txt", gtfs_dir / "calendar_dates.txt"
    cal = _read(cal_path, cal_cols) if cal_path.exists() else pd.DataFrame(columns=cal_cols)
    dates = (
        _read(dates_path, dates_cols) if dates_path.exists() else pd.DataFrame(columns=dates_cols)
    )
    if cal.empty and dates.empty:
        raise StageValidationError(f"{gtfs_dir}: neither calendar.txt nor calendar_dates.txt")
    cal = cal.assign(start_date=cal["start_date"].map(_date), end_date=cal["end_date"].map(_date))
    dates = dates.assign(date=dates["date"].map(_date))
    return cal, dates


def feed_validity(gtfs_dir: Path, cal: pd.DataFrame, dates: pd.DataFrame) -> tuple[date, date]:
    """Validity from `feed_info.txt` if it has both dates, else the span of the calendars."""
    info_path = gtfs_dir / "feed_info.txt"
    if info_path.exists():
        info = _read(info_path, [])
        if {"feed_start_date", "feed_end_date"} <= set(info.columns) and len(info):
            start, end = info["feed_start_date"].iloc[0], info["feed_end_date"].iloc[0]
            if start and end and not pd.isna(start) and not pd.isna(end):
                return _date(start), _date(end)
    starts = [*cal["start_date"], *dates["date"]]
    ends = [*cal["end_date"], *dates["date"]]
    return min(starts), max(ends)


def active_service_ids(cal: pd.DataFrame, dates: pd.DataFrame, day: date) -> set[str]:
    """Services running on `day`: weekly pattern, then `calendar_dates` adds (1) and removes (2)."""
    weekday = WEEKDAYS[day.weekday()]
    regular = cal[(cal["start_date"] <= day) & (cal["end_date"] >= day) & (cal[weekday] == "1")]
    on_day = dates[dates["date"] == day]
    added = set(on_day.loc[on_day["exception_type"] == "1", "service_id"])
    removed = set(on_day.loc[on_day["exception_type"] == "2", "service_id"])
    return (set(regular["service_id"]) | added) - removed


def reference_weekday(
    valid_from: date,
    valid_to: date,
    cal: pd.DataFrame,
    dates: pd.DataFrame,
    cfg: ReferenceDay,
    not_before: date,
) -> date:
    """First `cfg.weekday` on or after `not_before` inside the feed validity that is no public or
    school holiday and has at least one active service."""
    target = WEEKDAYS.index(cfg.weekday)
    day = max(valid_from, not_before)
    day += timedelta(days=(target - day.weekday()) % 7)
    while day <= valid_to:
        if not cfg.is_holiday(day) and active_service_ids(cal, dates, day):
            return day
        day += timedelta(days=7)
    raise StageValidationError(
        f"no regular {cfg.weekday} between {max(valid_from, not_before)} and {valid_to} "
        "(feed validity, holidays, active services)"
    )
