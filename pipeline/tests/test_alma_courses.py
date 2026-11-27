"""Alma course detail tab: modules and programmes of a course (synthetic page, no network)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from reach_pipeline import alma_courses
from reach_pipeline.errors import StageValidationError

PAGE = (Path(__file__).parent / "fixtures" / "alma" / "course.html").read_text(encoding="utf-8")


def test_parse_course_reads_both_tables() -> None:
    mods, progs = alma_courses.parse_course(PAGE, "42")
    assert mods["name"].tolist() == [
        "Marketing",
        "Elective Studies",
        "Kontextstudien (Vertiefung)",
        "Marketing",
    ]
    assert progs[["degree", "subject", "major", "po"]].values.tolist() == [
        ["Bachelor", "Economics and Business Administration", "Hauptfach", "2023"],
        ["Bachelor", "Betriebswirtschaftslehre", "Nebenfach", "2023"],
    ]
    assert set(mods["unit_id"]) == set(progs["unit_id"]) == {"42"}


def test_parse_course_fails_on_a_wrong_or_truncated_page() -> None:
    with pytest.raises(StageValidationError, match="not the"):
        alma_courses.parse_course("<html>Termine</html>", "42")
    with pytest.raises(StageValidationError, match="paging"):
        alma_courses.parse_course(PAGE.replace("Suchergebnis: 2", "Suchergebnis: 31"), "42")


def test_a_course_in_more_programmes_than_alma_shows_is_open(monkeypatch) -> None:
    monkeypatch.setattr(alma_courses, "MAX_ROWS", 2)
    page = PAGE.replace("Suchergebnis: 2", "Suchergebnis: 655")
    mods, progs = alma_courses.parse_course(page, "42")
    assert progs["open"].all() and mods["open"].all() and len(progs) == 2


def test_split_code_reads_degree_subject_major_po() -> None:
    codes = alma_courses.split_code(
        pd.Series(["82|410|H|2023-B220", "82|275|-|-|H|2018-4200-WPI_e", "410B220"])
    )
    assert codes.iloc[0].tolist() == ["82", "410", "H", "2023", "B220"]
    assert codes.iloc[1].tolist() == ["82", "275", "H", "2018", "4200-WPI_e"]
    assert codes.iloc[2].isna().all()  # old-style short text: no code


def test_courses_to_fetch_needs_a_room() -> None:
    sessions = pd.DataFrame(
        {
            "unit_id": ["1", "1", "2", "3", ""],
            "period_id": ["237"] * 5,
            "room": ["R", "R", "", "R", "R"],
        }
    )
    assert alma_courses.courses_to_fetch(sessions)["unit_id"].tolist() == ["1", "3"]
