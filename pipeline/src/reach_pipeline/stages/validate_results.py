"""validate_results: validation report part 2 (arch. §7 "validate results").

Checks completeness, value ranges, thresholds, class totals (residents in classes = scored
residents), that `reachable` gives exactly the counts, monotonicity between profiles
(`validation.results.monotonic`), and compares a sample of matrix times with /route
(`validation.results.route_check`, a known limitation, never fails), checks a sample of pairs
within the prefilter reach that are not in `reachable` with /route for missed facilities
(`validation.results.false_negatives`, notes N9), and reports from both samples the share of
pairs on which matrix and /route lie on different sides of the budget
(`validation.results.budget_flips`, methodology V10, warns only); lists the values of sample
cells for a manual check. Writes `report_results.json` + `.md`; any failed check fails the
stage after the report is written, so `publish` does not run.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer

from reach_pipeline import results
from reach_pipeline.config import Config
from reach_pipeline.context import RunContext
from reach_pipeline.errors import BadRequestError, StageValidationError
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    config_input,
    file_inputs,
    is_up_to_date,
    read_manifest,
    require_ok,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import count, recommend, score, validate
from reach_pipeline.valhalla.client import ValhallaClient, costing_options

STAGE = results.STAGE
# Config sections this stage uses; only they are part of its inputs (see
# manifest.config_input): result checks and sample points.
CONFIG_SECTIONS = (
    "categories",
    "count",
    "profiles",
    "recommend",
    "time_budgets_min",
    "validation",
    "valhalla",
)
PREVIOUS = recommend.STAGE
REPORT_JSON, REPORT_MD = "report_results.json", "report_results.md"

log = logging.getLogger(__name__)


def _paths(ctx: RunContext) -> dict[str, Any]:
    vdir, cdir = ctx.stage_dir(validate.STAGE), ctx.stage_dir(count.STAGE)
    return {
        "cells": vdir / "cells.parquet",
        "report_inputs": vdir / validate.REPORT_JSON,
        "access": cdir / count.ACCESS,
        "reachable": cdir / count.REACHABLE,
        "facilities": vdir / "facilities.parquet",
        "facility_points": vdir / "facility_points.parquet",
        "transit": cdir / count.TRANSIT,
        "thresholds": ctx.stage_dir(score.STAGE) / score.THRESHOLDS,
        "recommendations": ctx.stage_dir(recommend.STAGE) / recommend.RECOMMENDATIONS,
        "recommendation_catchments": ctx.stage_dir(recommend.STAGE) / recommend.REC_CATCHMENTS,
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
        reachable=pd.read_parquet(p["reachable"]),
        facilities=pd.read_parquet(p["facilities"], columns=["facility_id", "category"]),
        recommendations=pd.read_parquet(p["recommendations"], columns=recommend.REC_COLUMNS),
        recommendation_catchments=pd.read_parquet(p["recommendation_catchments"]),
    )
    return tables, origins


def _lonlat(geoms: gpd.GeoSeries) -> np.ndarray:
    g = geoms.to_crs("EPSG:4326")
    return np.column_stack([g.x.to_numpy(), g.y.to_numpy()])


async def route_times(
    cfg: Config,
    pairs: pd.DataFrame,
    origins: dict[str, tuple[float, float]],
    points: dict[str, list[tuple[float, float]]],
) -> list[float | None]:
    """/route time from the cell origin to the facility (fastest of its routing points) per
    pair; None if Valhalla finds no route to any point."""

    async with ValhallaClient(cfg.valhalla) as client:

        async def one(cell_id: str, profile_id: str, facility_id: str) -> float | None:
            profile = cfg.profiles[profile_id]
            lon, lat = origins[cell_id]
            times = []
            for plon, plat in points[facility_id]:
                payload = {
                    "locations": [{"lon": lon, "lat": lat}, {"lon": plon, "lat": plat}],
                    "costing": profile.costing,
                    "costing_options": costing_options(profile),
                    "directions_type": "none",
                }
                try:
                    body = await client.post("route", payload)
                except BadRequestError:  # 4xx: no route to this point; other errors abort
                    continue
                times.append(float(body["trip"]["summary"]["time"]))
            return min(times, default=None)

        return await asyncio.gather(
            *(one(r.cell_id, r.profile_id, r.facility_id) for r in pairs.itertuples())
        )


def require_count_valhalla(ctx: RunContext) -> None:
    """The /route checks must use the Valhalla config `count` used: the copy the service runs
    with (`count.check_valhalla_config`) must have the checksum `report_count.json` recorded."""
    report = json.loads((ctx.stage_dir(count.STAGE) / count.REPORT).read_text(encoding="utf-8"))
    recorded = (report.get("valhalla") or {}).get("sha256")
    current = count.check_valhalla_config(ctx)["sha256"]
    if recorded != current:
        raise StageValidationError(
            f"Valhalla now runs with another config than count used ({current[:12]} vs. "
            f"{str(recorded)[:12]}); rerun count"
        )


def _seed(run_id: str) -> int:
    return int("".join(ch for ch in run_id if ch.isdigit()))


def _with_routes(ctx: RunContext, pairs: pd.DataFrame, origins: gpd.GeoDataFrame) -> pd.DataFrame:
    """`pairs` (`cell_id`, `profile_id`, `facility_id`) plus `route_s` from /route (NaN = no
    route), fastest over the facility's routing points."""
    o = dict(zip(origins["cell_id"], map(tuple, _lonlat(origins.geometry)), strict=True))
    fp = gpd.read_parquet(_paths(ctx)["facility_points"])
    fp = fp[fp["facility_id"].isin(set(pairs["facility_id"]))]
    pts: dict[str, list[tuple[float, float]]] = {}
    for fid, xy in zip(fp["facility_id"], _lonlat(fp.geometry), strict=True):
        pts.setdefault(fid, []).append(tuple(xy))
    times = asyncio.run(route_times(ctx.config, pairs, o, pts)) if len(pairs) else []
    return pairs.assign(route_s=pd.array(times, dtype="Float64").astype(float))


def check_routes(ctx: RunContext, t: results.Tables, origins: gpd.GeoDataFrame) -> tuple:
    """Sample matrix times of `reachable` and compare them with /route (known limitation)."""
    cfg = ctx.config
    rc = cfg.validation.results.route_check
    budget_s = cfg.time_budgets_min.facilities * 60
    pairs = results.route_sample(t.reachable, budget_s, rc, _seed(ctx.run_id))
    pairs = _with_routes(ctx, pairs, origins)
    check, per_profile = results.route_check(pairs, budget_s, rc)
    return check, {"budget_s": budget_s, "profiles": per_profile}


def check_false_negatives(
    ctx: RunContext, t: results.Tables, origins: gpd.GeoDataFrame
) -> tuple[results.Check, dict[str, Any]]:
    """Sample pairs within the prefilter reach that are not in `reachable` and check them with
    /route (notes N9): per profile and category `pairs_per_category` random pairs."""
    cfg = ctx.config
    fc = cfg.validation.results.false_negatives
    budget_min = cfg.time_budgets_min.facilities
    rng = np.random.default_rng(_seed(ctx.run_id) + 1)
    o_xy = np.column_stack([origins.geometry.x.to_numpy(), origins.geometry.y.to_numpy()])
    fp = gpd.read_parquet(_paths(ctx)["facility_points"])
    p_xy = np.column_stack([fp.geometry.x.to_numpy(), fp.geometry.y.to_numpy()])
    parts = []
    for pid, profile in cfg.profiles.items():
        candidates = results.false_negative_candidates(
            o_xy,
            origins["cell_id"].to_numpy(),
            p_xy,
            fp["facility_id"].to_numpy(),
            t.facilities,
            t.reachable[t.reachable["profile_id"] == pid],
            profile.prefilter_reach_m(budget_min),
        )
        sample = results.false_negative_sample(candidates, fc.pairs_per_category, rng)
        parts.append(sample.assign(profile_id=pid))
        log.info("false negatives %s: %d candidates, %d sampled", pid, len(candidates), len(sample))
    pairs = _with_routes(ctx, pd.concat(parts, ignore_index=True), origins)
    return results.false_negative_check(pairs, budget_min * 60, fc)


def build_report(ctx: RunContext, t: results.Tables, origins: gpd.GeoDataFrame) -> dict[str, Any]:
    """All checks, summary and samples; dependent checks are skipped if completeness fails."""
    cfg = ctx.config
    part1 = json.loads(_paths(ctx)["report_inputs"].read_text(encoding="utf-8"))
    checks = results.completeness(cfg, t)
    out: dict[str, Any] = {
        "summary": None,
        "samples": [],
        "route_check": None,
        "false_negatives": None,
        "budget_flips": None,
    }
    if all(c.status != "fail" for c in checks):
        rows = results.class_rows(t)
        checks += results.value_ranges(cfg, t)
        checks += results.thresholds_cover(t)
        checks += results.reachable_matches_counts(t)
        route, out["route_check"] = check_routes(ctx, t, origins)
        checks.append(route)
        missed, out["false_negatives"] = check_false_negatives(ctx, t, origins)
        checks.append(missed)
        flips, out["budget_flips"] = results.budget_flips(
            out["route_check"], out["false_negatives"], cfg.validation.results.budget_flips
        )
        checks.append(flips)
        checks.append(results.recommendations_consistent(cfg, t))
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
    rc = report.get("route_check")
    if rc:
        lines += [
            "",
            "## Known limitation: matrix times vs. /route",
            "",
            "Counts use Valhalla's matrix (`costmatrix`, the same algorithm for every request, "
            "notes N8). For a sample of reachable cell × facility pairs the matrix time is "
            "compared with Valhalla's /route time from the same origin; both search separately "
            "and can end on different paths of similar cost, so a facility close to the "
            f"{rc['budget_s'] / 60:.0f}-minute budget can count although /route takes longer "
            "(`flips`).",
            "",
            "| Profile | Pairs | No route | Mean abs. Δ (s) | Max abs. Δ (s) | Flips |",
            "|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {p} | {v['pairs']} | {v['no_route']} | {v['mean_abs_s']} | {v['max_abs_s']} "
            f"| {v['flips']} |"
            for p, v in rc["profiles"].items()
        ]
    fn = report.get("false_negatives")
    if fn:
        lines += [
            "",
            "## Missed facilities: pairs within the prefilter reach not counted",
            "",
            f"Random cell × facility pairs whose routing point lies within the prefilter reach "
            f"but which are not in `reachable`, checked with /route: {fn['false_negatives']} of "
            f"{fn['pairs']} reach the facility within {fn['budget_s'] / 60:.0f} minutes "
            f"({fn['rate']:.1%}).",
            "",
            "| Profile | Category | Pairs | No route | False negatives | Rate |",
            "|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {p} | {c} | {v['pairs']} | {v['no_route']} | {v['false_negatives']} "
            f"| {v['rate']:.1%} |"
            for p, cats in fn["profiles"].items()
            for c, v in cats.items()
        ]
        if fn["examples"]:
            lines += ["", "| Profile | Cell | Facility | Straight line (m) | /route (s) |"]
            lines += ["|---|---|---|---|---|"]
            lines += [
                f"| {e['profile_id']} | {e['cell_id']} | {e['facility_id']} "
                f"| {e['distance_m']} | {e['route_s']} |"
                for e in fn["examples"]
            ]
    bf = report.get("budget_flips")
    if bf:
        lines += [
            "",
            "## Budget flips: matrix and /route on different sides of the budget",
            "",
            "Share of routed pairs per profile and direction (methodology V10). *Within → "
            "beyond*: counted by the matrix, /route takes longer than the budget (sample "
            "above, mostly near the budget). *Beyond → within*: not counted, /route within "
            "the budget (missed-facility sample). The samples differ, so the two directions "
            f"are not comparable; warns above {bf['warn_above']:.1%}, never fails.",
            "",
            "| Profile | Within → beyond | Beyond → within |",
            "|---|---|---|",
        ]
        lines += [
            f"| {p} | {v['within_to_beyond']['flips']} of {v['within_to_beyond']['routed']} "
            f"({v['within_to_beyond']['rate']:.1%}) | {v['beyond_to_within']['flips']} of "
            f"{v['beyond_to_within']['routed']} ({v['beyond_to_within']['rate']:.1%}) |"
            for p, v in bf["profiles"].items()
        ]
    recs = report.get("recommendations") or []
    if recs:
        lines += [
            "",
            "## Recommendations (methodology §5)",
            "",
            "Greedy picks per category and profile; gain = reduction of the deficit sum "
            "(residents), checked by `recommendations_consistent`. Accessibility only: zoning, "
            "parcels, capacity and statutory planning are not considered.",
            "",
            "| Profile | Category | Rank | Zone | Gain | Gaining access | To sufficient "
            "| Catchment residents |",
            "|---|---|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {r['profile_id']} | {r['category']} | {r['rank']} | {r['candidate_id']} "
            f"| {r['population_gain']} | {r['residents_gaining_access']} "
            f"| {r['residents_to_sufficient']} | {r['catchment_residents']} |"
            for r in recs
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
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    require_ok(ctx.stage_dir(count.STAGE), count.STAGE, ctx.config)
    require_count_valhalla(ctx)
    stage_dir = ctx.stage_dir(STAGE)
    inputs = [config_input(ctx.config, CONFIG_SECTIONS), *file_inputs(list(_paths(ctx).values()))]
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
        "route_check": built["route_check"],
        "false_negatives": built["false_negatives"],
        "budget_flips": built["budget_flips"],
        "recommendations": tables.recommendations.sort_values(
            ["profile_id", "category", "rank"]
        ).to_dict("records"),
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
