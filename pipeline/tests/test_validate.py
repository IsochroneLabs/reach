"""Checks of validation report part 1 on small synthetic layers (no osmium, no data)."""

from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path
from typing import Any

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from reach_pipeline.config import load_config
from reach_pipeline.context import RunContext
from reach_pipeline.stages import validate

REPO = Path(__file__).resolve().parents[2]
CRS = "EPSG:25832"
CITY = box(0, 0, 1000, 1000)


@pytest.fixture
def ctx() -> RunContext:
    path = REPO / "config" / "config.yaml"
    return RunContext(config=load_config(path), config_path=path, run_id="20261102T120000Z")


def _result(**overrides: Any) -> dict[str, Any]:
    cells = gpd.GeoDataFrame(
        {
            "cell_id": ["c1"],
            "population": [90_000],
            "district_id": ["r1"],
            "origin_geom": gpd.GeoSeries([Point(500, 500)], crs=CRS),
        },
        geometry=[box(450, 450, 550, 550)],
        crs=CRS,
    )
    # one facility of every configured category
    categories = [c.id for c in load_config(REPO / "config" / "config.yaml").categories]
    n = len(categories)
    layers = {
        "cells": cells,
        "facilities": gpd.GeoDataFrame(
            {"facility_id": [f"n{i}" for i in range(n)], "category": categories},
            geometry=[Point(100, 100)] * n,
            crs=CRS,
        ),
        "facility_points": gpd.GeoDataFrame(
            {"facility_id": ["n0"]}, geometry=[Point(1, 1)], crs=CRS
        ),
        "stops": gpd.GeoDataFrame({"stop_id": ["s1"]}, geometry=[Point(2, 2)], crs=CRS),
        "districts": gpd.GeoDataFrame({"district_id": ["r1"]}, geometry=[CITY], crs=CRS),
        "urban_boundary": gpd.GeoDataFrame({"part_id": [1]}, geometry=[CITY], crs=CRS),
        "routing_area": gpd.GeoDataFrame(geometry=[CITY.buffer(4000)], crs=CRS),
    }
    result = {
        "layers": layers,
        "scope": CITY,
        "district_gap": 0.0,
        "district_overlap": 0.0,
        "residents_touching": 90_500,
        "residents_scored": 90_000,
        "residents_excluded": 500,
        "excluded_by_district": {"West": 500},
        "excluded_by_filter": {"playgrounds": {"excluded": 3, "access=private": 2, "access=no": 1}},
        "subtype_total": 20,
        "subtype_missing": [],
        "gtfs_valid_from": date(2026, 7, 12),
        "gtfs_valid_to": date(2026, 12, 12),
        "reference_weekday": date(2026, 11, 3),
        "active_services": 470,
    }
    return {**result, **overrides}


def _status(checks: list[validate.Check]) -> dict[str, str]:
    return {c.check: c.status for c in checks}


def test_all_ok(ctx: RunContext) -> None:
    assert set(_status(validate.checks(ctx, _result())).values()) == {"ok"}


def test_scored_share_below_minimum_fails(ctx: RunContext) -> None:
    checks = validate.checks(ctx, _result(residents_touching=100_000, residents_excluded=10_000))
    share = next(c for c in checks if c.check == "scored_share")
    assert share.status == "fail" and share.value == pytest.approx(0.9)
    assert "West 500" in share.message


def test_population_and_districts(ctx: RunContext) -> None:
    status = _status(validate.checks(ctx, _result(residents_scored=50_000, district_gap=0.01)))
    assert status["population_total"] == "fail"  # 50,000 vs. 90,499
    assert status["district_coverage"] == "fail"  # 1 % gap > 0.5 %


def test_population_without_official_total_warns(ctx: RunContext) -> None:
    cfg = ctx.config.model_copy(
        update={
            "validation": ctx.config.validation.model_copy(update={"official_population": None})
        }
    )
    status = _status(validate.checks(RunContext(cfg, ctx.config_path, ctx.run_id), _result()))
    assert status["population_total"] == "warn"


def test_reference_day_and_holiday_calendar(ctx: RunContext) -> None:
    status = _status(validate.checks(ctx, _result(reference_weekday=None)))
    assert status["gtfs_reference_day"] == "fail"
    status = _status(validate.checks(ctx, _result(reference_weekday=date(2029, 1, 2))))
    assert status["holiday_calendar"] == "fail"  # outside the covered range
    status = _status(validate.checks(ctx, _result(gtfs_valid_to=date(2029, 1, 31))))
    assert status["holiday_calendar"] == "warn"  # feed longer than the holiday lists


def test_empty_layer_wrong_crs_and_missing_category(ctx: RunContext) -> None:
    result = _result()
    result["layers"]["stops"] = result["layers"]["stops"].iloc[0:0]
    cells = result["layers"]["cells"]
    cells["origin_geom"] = cells["origin_geom"].to_crs("EPSG:4326")
    result["layers"]["facilities"] = result["layers"]["facilities"].iloc[1:]  # no grocery
    checks = {c.check: c for c in validate.checks(ctx, result)}
    assert checks["non_empty"].status == "fail" and "stops" in checks["non_empty"].message
    assert checks["crs"].status == "fail" and "cells.origin_geom" in checks["crs"].message
    assert checks["facilities_per_category"].status == "fail"


def test_cell_outside_scope_fails(ctx: RunContext) -> None:
    result = _result()
    result["layers"]["cells"]["origin_geom"] = gpd.GeoSeries([Point(5000, 5000)], crs=CRS)
    assert _status(validate.checks(ctx, result))["cells_inside_boundary"] == "fail"


def test_facilities_excluded_by_access_is_informative(ctx: RunContext) -> None:
    checks = {c.check: c for c in validate.checks(ctx, _result())}
    c = checks["facilities_excluded_by_access"]
    assert c.status == "ok" and c.value == 3
    assert "playgrounds: access=private 2, access=no 1" in c.message


def test_facility_subtypes_complete_warns_below_the_gate(ctx: RunContext) -> None:
    ok = {c.check: c for c in validate.checks(ctx, _result())}["facility_subtypes_complete"]
    assert ok.status == "ok" and ok.value == 100.0
    missing = [f"School {i}" for i in range(12)]
    warn = {c.check: c for c in validate.checks(ctx, _result(subtype_missing=missing))}[
        "facility_subtypes_complete"
    ]
    assert warn.status == "warn" and warn.value == 40.0
    assert "8 of 20 amenity=school" in warn.message and "School 0" in warn.message
    assert warn.message.endswith("…")


def test_no_subtype_check_without_config(ctx: RunContext) -> None:
    cfg = ctx.config.model_copy(
        update={"validation": ctx.config.validation.model_copy(update={"facility_subtypes": None})}
    )
    names = {c.check for c in validate.checks(dataclasses.replace(ctx, config=cfg), _result())}
    assert "facility_subtypes_complete" not in names
