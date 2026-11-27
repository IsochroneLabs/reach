"""Programmes → teaching buildings from course hours, modules and programmes (synthetic tables)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from reach_pipeline import programmes as P
from reach_pipeline.campus import load_campus

REPO = Path(__file__).resolve().parents[2]
ELECTIVE = ["Wahl", "Elective"]


def _progs(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    """(unit_id, degree, subject) rows as majors."""
    df = pd.DataFrame(rows, columns=["unit_id", "degree", "subject"])
    return df.assign(major="Hauptfach", programme="", kind="", po="2023")


def _mods(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    """(unit_id, code, module name) rows."""
    df = pd.DataFrame(rows, columns=["unit_id", "code", "name_module"])
    return df.assign(module="")


def test_slug_is_ascii() -> None:
    assert P.slug("Bachelor Sportwissenschaft: Gesundheitsförderung") == (
        "bachelor-sportwissenschaft-gesundheitsfoerderung"
    )
    assert P.slug("Master Straße / Ökonomie") == "master-strasse-oekonomie"


def test_course_hours_split_parallel_groups() -> None:
    campus = load_campus(REPO / "config" / "config.yaml", generated=False)
    sem = "Wintersemester 2026/27"
    s = pd.DataFrame(
        {
            "unit_id": ["1", "2", "2", "3"],
            "group": ["1. PG", "1. PG", "2. PG", "1. PG"],
            "start": ["08:00", "10:00", "10:00", "00:00"],
            "end": ["10:00", "12:00", "12:00", "23:00"],  # 23 h: placeholder, dropped
            "room": ["R"] * 4,
            "building": ["WiWi Sem Mohl", "Kupferbau", "WiWi Sem Mohl", "Kupferbau"],
            "semester": [sem] * 4,
        }
    )
    out = P.course_hours(s, campus, sem).set_index(["unit_id", "title"])["hours"]
    assert out[("1", "Mohlstraße 36")] == 2
    assert out[("2", "Hölderlinstraße 5 – Kupferbau")] == 1  # one of two groups
    assert out[("2", "Mohlstraße 36")] == 1
    assert "3" not in out.index.get_level_values(0)


def test_codes_map_to_programmes_by_shared_courses() -> None:
    progs = _progs(
        [
            ("1", "Bachelor", "Economics"),
            ("2", "Bachelor", "Economics"),
            ("2", "Bachelor", "IBA"),
            ("3", "Bachelor", "IBA"),
        ]
    )
    mods = _mods(
        [
            ("1", "82|410|H|2023-B1", "Micro"),
            ("2", "82|410|H|2023-B2", "Marketing"),
            ("2", "82|412|H|2023-B2", "Marketing"),
            ("3", "82|412|H|2023-B3", "Wahlmodul"),
        ]
    )
    names = P.code_names(mods, progs)
    assert names["82|410|H"] == "Bachelor|Economics|Hauptfach"
    assert names["82|412|H"] == "Bachelor|IBA|Hauptfach"
    comp = P.compulsory(mods, names, ELECTIVE).set_index(["unit_id", "name"])["compulsory"]
    assert comp[("3", "Bachelor|IBA|Hauptfach")] == False  # noqa: E712 (only elective modules)
    assert comp[("2", "Bachelor|IBA|Hauptfach")] == True  # noqa: E712


def test_programme_hours_use_compulsory_courses_or_fall_back_to_all() -> None:
    hours = pd.DataFrame(
        {"unit_id": ["1", "2", "3"], "title": ["A", "B", "C"], "hours": [4.0, 2.0, 1.0]}
    )
    progs = _progs([("1", "Bachelor", "Eco"), ("2", "Bachelor", "Eco"), ("3", "Master", "Eco")])
    progs = P.programme_names(progs, ["Bachelor", "Master"])
    comp = pd.DataFrame(
        {
            "unit_id": ["1", "2", "3"],
            "name": ["Bachelor|Eco|Hauptfach", "Bachelor|Eco|Hauptfach", "Master|Eco|Hauptfach"],
            "compulsory": [True, False, False],
        }
    )
    per, meta = P.programme_hours(hours, progs, comp, min_compulsory_h=2)
    assert per[per["programme"] == "bachelor-eco"]["title"].tolist() == ["A"]  # B is elective
    assert meta.loc["bachelor-eco", "basis"] == "compulsory"
    assert meta.loc["master-eco", "basis"] == "all"  # no compulsory hours: all courses
    assert meta.loc["master-eco", "hours"] == 1


def test_destinations_cluster_drop_small_shares_and_normalise() -> None:
    campus = load_campus(REPO / "config" / "config.yaml", generated=False)
    table = pd.DataFrame(
        {
            "title": ["A", "A2", "B", "C", "M"],
            "address": ["A 1", "A 2", "B 1", "C 1", "M 1"],
            "site": ["tal", "tal", "tal", "tal", "morgenstelle"],
            "lon": [9.0600, 9.0603, 9.0700, 9.0800, 9.0352],  # A2 is ~22 m from A
            "lat": [48.5258, 48.5258, 48.5258, 48.5258, 48.5371],
        }
    )
    per = pd.DataFrame(
        {
            "programme": ["p", "p", "p", "p", "q"],
            "title": ["A", "A2", "B", "C", "M"],
            "hours": [6.0, 2.0, 11.0, 0.5, 3.0],
        }
    )
    meta = pd.DataFrame(
        {
            "basis": ["compulsory", "all"],
            "courses": [3, 1],
            "hours": [19.5, 3.0],
            "degree": ["Bachelor", "Master"],
            "subject": ["P", "Q"],
        },
        index=pd.Index(["p", "q"], name="programme"),
    )
    names = pd.Series({"A": "Building A (A 1)"})
    b, p = P.destinations(per, meta, table, campus, 60, 0.05, names)
    row = p.set_index("programme").loc["p"]
    assert row["buildings"] == "b|a"  # A and A2 merged; C (2.6 %) dropped
    assert [float(x) for x in row["shares"].split("|")] == pytest.approx([11 / 19, 8 / 19], 1e-3)
    assert set(b["building_id"]) == {"a", "b", "m"}
    assert b.set_index("building_id").loc["a", "name"] == "Building A (A 1)"
