"""validate_results: validation report part 2 (arch. §7 "validate results").

Checks completeness, value ranges, thresholds, class totals (residents in classes = scored
residents) and monotonicity between profiles (`validation.results.monotonic`), and lists the
values of sample cells for a manual check. Writes `report_results.json` + `.md`; any failed
check fails the stage after the report is written, so `publish` does not run.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import geopandas as gpd
import pandas as pd
from pyproj import Transformer

from reach_pipeline import results
from reach_pipeline.config import config_files
from reach_pipeline.context import RunContext
from reach_pipeline.errors import StageValidationError
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    file_inputs,
    is_up_to_date,
    read_manifest,
    require_ok,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import count, score, validate

STAGE = results.STAGE
# recommend (P7) will sit between score and validate_results (arch. §7).
PREVIOUS = score.STAGE
REPORT_JSON, REPORT_MD = "report_results.json", "report_results.md"

log = logging.getLogger(__name__)


def _paths(ctx: RunContext) -> dict[str, Any]:
    vdir, cdir = ctx.stage_dir(validate.STAGE), ctx.stage_dir(count.STAGE)
    return {
        "cells": vdir / "cells.parquet",
        "report_inputs": vdir / validate.REPORT_JSON,
        "access": cdir / count.ACCESS,
        "transit": cdir / count.TRANSIT,
        "thresholds": ctx.stage_dir(score.STAGE) / score.THRESHOLDS,
    }


def load_tables(ctx: RunContext) -> tuple[results.Tables, gpd.GeoDataFrame]:
    p = _paths(ctx)
    origins = gpd.read_parquet(p["cells"], columns=["cell_id", "origin_geom"]).set_geometry(
        "origin_geom"
    )
    tables = results.Tables(
        cells=pd.read_parquet(p["cells"], columns=["cell_id", "population", "district_id"]),
        access=pd.read_parquet(p["access"]),
        transit=pd.read_parquet(p["transit"]),
        thresholds=pd.read_parquet(p["thresholds"]),
    )
    return tables, origins


def build_report(ctx: RunContext, t: results.Tables, origins: gpd.GeoDataFrame) -> dict[str, Any]:
    """All checks, summary and samples; dependent checks are skipped if completeness fails."""
    cfg = ctx.config
    part1 = json.loads(_paths(ctx)["report_inputs"].read_text(encoding="utf-8"))
    checks = results.completeness(cfg, t)
    out: dict[str, Any] = {"summary": None, "samples": []}
    if all(c.status != "fail" for c in checks):
        rows = results.class_rows(t)
        checks += results.value_ranges(cfg, t)
        checks += results.thresholds_cover(t)
        checks += results.totals(t, rows, part1["summary"].get("residents_scored"))
        checks += [results.monotonic(pair, t) for pair in cfg.validation.results.monotonic]
        out["summary"] = results.summary(t, rows)
        to_metric = Transformer.from_crs("EPSG:4326", validate.METRIC_CRS, always_xy=True)
        points = {
            name: to_metric.transform(lon, lat)
            for name, (lon, lat) in cfg.count.evidence.sample_points.items()
        }
        xy = t.cells.merge(
            pd.DataFrame(
                {
                    "cell_id": origins["cell_id"],
                    "x": origins.geometry.x,
                    "y": origins.geometry.y,
                }
            ),
            on="cell_id",
        )
        out["samples"] = results.samples(points, xy, rows)
        checks.append(
            results.Check(
                "sample_cells",
                "ok",
                float(len(out["samples"])),
                "values of the cells nearest to count.evidence.sample_points, for a manual "
                "check (see report)",
            )
        )
    out["checks"] = checks
    return out


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Validation report part 2 — results ({report['run_id']})",
        "",
        f"Status: **{report['status']}** · generated {report['generated_at']}",
        "",
        "## Checks",
        "",
        "| Check | Status | Value | Message |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {c['check']} | {c['status']} | {'' if c['value'] is None else c['value']} "
        f"| {c['message']} |"
        for c in report["checks"]
    ]
    s = report["summary"]
    if s:
        lines += [
            "",
            f"## Residents per class ({s['residents_scored']} scored residents)",
            "",
            "| Profile | Category | Lack | Insufficient | Sufficient | Residents lacking "
            "| Deficit sum |",
            "|---|---|---|---|---|---|---|",
        ]
        for profile, cats in s["access"].items():
            for cat, v in cats.items():
                lines.append(
                    f"| {profile} | {cat} | {v['share_lack']:.1%} | "
                    f"{v['share_insufficient']:.1%} | {v['share_sufficient']:.1%} | "
                    f"{v['residents_lack']} | {v['deficit_sum']} |"
                )
        lines += ["", "| Profile | Transit class shares |", "|---|---|"]
        lines += [
            f"| {p} | " + ", ".join(f"{c} {v:.1%}" for c, v in shares.items()) + " |"
            for p, shares in s["transit"].items()
        ]
    for sample in report["samples"]:
        lines += [
            "",
            f"## Sample {sample['sample']}: {sample['cell_id']} "
            f"({sample['population']} residents, district {sample['district_id']})",
            "",
            "| Profile / category | Count | Class | Deficit |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {key} | {v['count']} | {v['class']} | {v['deficit']} |"
            for key, v in sample["values"].items()
        ]
    lines += [
        "",
        "## Runtime and peak memory",
        "",
        f"{report['runtime_s']} s, peak RSS {report['peak_rss_mb']} MB",
    ]
    return "\n".join(lines) + "\n"


def run(ctx: RunContext) -> Manifest:
    """Check the results of count and score; write report part 2; fail on any failed check."""
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS)
    require_ok(ctx.stage_dir(count.STAGE), count.STAGE)
    stage_dir = ctx.stage_dir(STAGE)
    inputs = file_inputs([*config_files(ctx.config_path), *_paths(ctx).values()])
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        log.info("inputs unchanged since %s, nothing to do", previous.finished_at.isoformat())
        return previous

    started_at = datetime.now(UTC)
    with measure() as m:
        tables, origins = load_tables(ctx)
        built = build_report(ctx, tables, origins)
    checks: list[results.Check] = built["checks"]
    failed = [c.check for c in checks if c.status == "fail"]
    report = {
        "run_id": ctx.run_id,
        "stage": STAGE,
        "status": "fail" if failed else "ok",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "checks": [asdict(c) for c in checks],
        "summary": built["summary"],
        "samples": built["samples"],
        "runtime_s": m.runtime_s,
        "peak_rss_mb": m.peak_rss_mb,
    }
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / REPORT_JSON).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (stage_dir / REPORT_MD).write_text(_markdown(report), encoding="utf-8")
    for c in checks:
        (log.error if c.status == "fail" else log.warning if c.status == "warn" else log.info)(
            "check %s: %s — %s", c.check, c.status, c.message
        )
    if failed:
        raise StageValidationError(f"result validation failed: {failed} (see {REPORT_MD})")

    warned = [c.check for c in checks if c.status == "warn"]
    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        outputs=[FileOutput(path=str(stage_dir / n)) for n in (REPORT_JSON, REPORT_MD)],
        message=f"{len(checks)} checks ok" + (f", warnings: {warned}" if warned else ""),
    )
    write_manifest(manifest, stage_dir)
    return manifest
