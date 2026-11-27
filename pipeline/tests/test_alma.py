"""Alma day view: form replay, parsing and building matching (synthetic page, no network)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from reach_pipeline import alma, uni_buildings
from reach_pipeline.campus import load_campus
from reach_pipeline.errors import StageValidationError

REPO = Path(__file__).resolve().parents[2]
PAGE = (Path(__file__).parent / "fixtures" / "alma" / "day.html").read_text(encoding="utf-8")
DAY = date(2026, 12, 1)
SEMESTER = "Wintersemester 2026/27"
BUILDINGS = uni_buildings.load(REPO / "config" / uni_buildings.OUT_NAME)


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
    assert len(s) == 5 and list(s.columns) == alma.SESSION_COLUMNS
    assert s.loc[0, "building"] == "Hörsaalzentrum Morgenstelle"
    assert s.loc[1, "building"] == "Informatik/Kriminologie"
    assert not s.astype(str).apply(lambda c: c.str.contains("Person")).any().any()
    with pytest.raises(StageValidationError, match="not the day view"):
        alma.parse_day(PAGE, date(2026, 12, 2))
    with pytest.raises(StageValidationError, match="paging"):
        alma.parse_day(PAGE.replace("Suchergebnis: 5", "Suchergebnis: 1.153"), DAY)


def test_parse_day_keeps_course_ids_and_groups() -> None:
    s = alma.parse_day(PAGE, DAY)
    assert s["unit_id"].tolist() == ["101", "102", "103", "103", "104"]
    assert set(s["period_id"]) == {"237"} and s.loc[3, "group"] == "2. PG"


def test_coverage_counts_sessions_with_an_official_building() -> None:
    campus = load_campus(REPO / "config" / "config.yaml", generated=False)
    cov = alma.coverage(alma.parse_day(PAGE, DAY), campus, SEMESTER)
    assert cov == {"sessions": 5, "with_room": 4, "building_matched": 1.0}


def test_building_of_takes_the_last_top_level_bracket() -> None:
    assert alma.building_of("Hörsaal N01 (Hörsaalzentrum Morgenstelle (0))") == (
        "Hörsaalzentrum Morgenstelle"
    )
    assert alma.building_of("Hörsaal A1 (A-206) (Cyber Valley Campus, MVL1 (EG))") == (
        "Cyber Valley Campus, MVL1"
    )
    assert alma.building_of("Übungsraum (groß) 7 (Seminar f. Japanologie (0))") == (
        "Seminar f. Japanologie"
    )


def test_every_mapped_building_is_on_the_official_list_and_located() -> None:
    campus = load_campus(REPO / "config" / "config.yaml", generated=False)
    titles = set(BUILDINGS["title"])
    assert set(campus.alma.building_addresses) <= titles
    assert set(campus.building_points) <= titles
    assert BUILDINGS["site"].notna().all() and set(BUILDINGS["site"]) <= set(campus.areas)
    names = ["Cyber Valley Campus, MVL6", "BURSE", "Neue Aula", "WiWi Sem Mohl", "Kupferbau"]
    official = alma.address_of(pd.Series(names), campus)
    assert official.tolist() == [
        "Maria-von-Linden-Straße 6",
        "Bursagasse 1",
        "Geschwister-Scholl-Platz",
        "Mohlstraße 36",
        "Hölderlinstraße 5 – Kupferbau",
    ]
    areas = official.map(BUILDINGS.set_index("title")["site"])
    assert areas.tolist() == ["cyber_valley", "altstadt", "tal", "tal", "tal"]
