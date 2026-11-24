"""Checks of validation report part 1 on small synthetic layers (no osmium, no data)."""

from __future__ import annotations

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
    layers = {
        "cells": cells,
        "stops": gpd.GeoDataFrame({"stop_id": ["s1"]}, geometry=[Point(2, 2)], crs=CRS),
        "districts": gpd.GeoDataFrame({"district_id": ["r1"]}, geometry=[CITY], crs=CRS),
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
        "gtfs_valid_from": date(2026, 7, 12),
        "gtfs_valid_to": date(2026, 12, 12),
        "reference_dates": {"morning_lecture": date(2026, 11, 24), "night": date(2026, 11, 28)},
        "active_services": {"2026-11-24": 470, "2026-11-28": 210},
    }
    return {**result, **overrides}


def _status(checks: list[validate.Check]) -> dict[str, str]:
    return {c.check: c.status for c in checks}


def test_all_ok(ctx: RunContext) -> None:
    assert set(_status(validate.checks(ctx, _result())).values()) == {"ok"}


def test_origin_coverage_below_minimum_fails(ctx: RunContext) -> None:
    checks = validate.checks(ctx, _result(residents_touching=100_000, residents_excluded=10_000))
    share = next(c for c in checks if c.check == "origin_coverage")
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


def test_trip_windows_and_holiday_calendar(ctx: RunContext) -> None:
    refs = {"morning_lecture": date(2026, 11, 24), "night": None}
    checks = {c.check: c for c in validate.checks(ctx, _result(reference_dates=refs))}
    assert checks["gtfs_trip_windows"].status == "fail"
    assert "['night']" in checks["gtfs_trip_windows"].message
    late = {"morning_lecture": date(2029, 1, 2)}
    status = _status(validate.checks(ctx, _result(reference_dates=late)))
    assert status["holiday_calendar"] == "fail"  # outside the covered range
    status = _status(validate.checks(ctx, _result(gtfs_valid_to=date(2029, 1, 31))))
    assert status["holiday_calendar"] == "warn"  # feed longer than the holiday lists


def test_empty_layer_and_wrong_crs(ctx: RunContext) -> None:
    result = _result()
    result["layers"]["stops"] = result["layers"]["stops"].iloc[0:0]
    cells = result["layers"]["cells"]
    cells["origin_geom"] = cells["origin_geom"].to_crs("EPSG:4326")
    checks = {c.check: c for c in validate.checks(ctx, result)}
    assert checks["non_empty"].status == "fail" and "stops" in checks["non_empty"].message
    assert checks["crs"].status == "fail" and "cells.origin_geom" in checks["crs"].message


def test_cell_outside_scope_fails(ctx: RunContext) -> None:
    result = _result()
    result["layers"]["cells"]["origin_geom"] = gpd.GeoSeries([Point(5000, 5000)], crs=CRS)
    assert _status(validate.checks(ctx, result))["cells_inside_boundary"] == "fail"


def test_markdown_lists_reference_dates(ctx: RunContext) -> None:
    result = _result()
    report = {
        "run_id": ctx.run_id,
        "status": "ok",
        "generated_at": "now",
        "summary": {
            "reference_dates": {"morning_lecture": "2026-11-24", "night": None},
            "active_services": {"2026-11-24": 470},
            "excluded_by_district": result["excluded_by_district"],
        },
        "checks": [],
        "stages": [],
        "steps": [],
    }
    md = validate._markdown(report)
    assert "| morning_lecture | 2026-11-24 | 470 |" in md and "| night | none | 0 |" in md
