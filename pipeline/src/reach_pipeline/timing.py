"""Local times of trip windows (meth. §5): reference date + `HH:MM` in the study area's zone."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo


def window_datetime(day: date, hhmm: str, tz: str) -> datetime:
    """Timezone-aware start of a trip window on its reference date."""
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, time(hh, mm), tzinfo=ZoneInfo(tz))
