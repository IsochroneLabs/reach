"""Alma day view: form replay, parsing and programme × site shares (synthetic page, no network)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from reach_pipeline import alma
from reach_pipeline.campus import load_campus
from reach_pipeline.errors import StageValidationError

REPO = Path(__file__).resolve().parents[2]
PAGE = (Path(__file__).parent / "fixtures" / "alma" / "day.html").read_text(encoding="utf-8")
DAY = date(2026, 12, 1)
SEMESTER = "Wintersemester 2026/27"


def test_day_request_sets_date_rows_and_filter() -> None:
    action, data = alma.day_request(PAGE, DAY, 2000)
    assert action.endswith("_flowExecutionKey=e1s1")
    assert data[alma.FORM + ":tabContainer:date-selection-container:date"] == "01.12.2026"
    assert data[alma.FORM + ":tabContainer:filter-container:selectCheckbox"] == "selectAllCourses"
    assert data[alma.TABLE + "Navi2NumRowsInput"] == "2000"
    assert data["authenticity_token"] == "tok" and data["lang"] == "de"
    assert "unchecked" not in data and alma.FORM + ":searchButtonId" not in data


def test_parse_day_keeps_no_people() -> None:
    s = alma.parse_day(PAGE, DAY)
    assert len(s) == 4 and list(s.columns) == alma.SESSION_COLUMNS
    assert s.loc[0, "building"] == "Hörsaalzentrum Morgenstelle"
    assert s.loc[1, "building"] == "Informatik/Kriminologie"
    assert not s.astype(str).apply(lambda c: c.str.contains("Person")).any().any()
    with pytest.raises(StageValidationError, match="not the day view"):
        alma.parse_day(PAGE, date(2026, 12, 2))
    with pytest.raises(StageValidationError, match="paging"):
        alma.parse_day(PAGE.replace("Suchergebnis: 4", "Suchergebnis: 1.153"), DAY)


def test_shares_per_programme_and_site() -> None:
    campus = load_campus(REPO / "config" / "config.yaml")
    s = alma.parse_day(PAGE, DAY)
    t = alma.shares(s, campus, SEMESTER).set_index(["programme", "site"])
    assert t.loc[("computer_science", "sand"), "share"] == pytest.approx(0.5)
    assert t.loc[("computer_science", "tal"), "hours"] == pytest.approx(2)
    assert t.loc[("mathematics", "morgenstelle"), "share"] == 1
    cov = alma.coverage(s, campus, SEMESTER)
    assert cov["with_room"] == 3 and cov["site_matched"] == 1
