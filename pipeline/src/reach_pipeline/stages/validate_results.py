"""validate_results: report part 2, plausibility (V2) and completeness (V3) of the travel times.

Checks with warn/fail limits from `validation.results`; any fail stops the run before publish.

- `pairs_complete` (V3): every selected cell × destination pair has a walk and a bike row.
- `campus_routable` (V3): every campus site is reachable from every populated cell by one mode.
- `unreachable_share` (V2): share of rows without a time, per mode.
- `bike_not_slower_than_walk` (V2): share of pairs with bike ≤ walk.
- `transit_speed` (V2): no transit trip faster than the straight line at `max_transit_kmh`.
- `transit_legs_add_up` (V2): access + wait + in-vehicle + egress = time (± 2 s).
- `night_not_better_than_day` (V2, report): median transit night vs. evening for nightlife.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from reach_pipeline.config import ShareLimits
from reach_pipeline.context import RunContext
from reach_pipeline.errors import StageValidationError
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    config_input,
    file_inputs,
    require_ok,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import travel_times, validate
from reach_pipeline.stages.validate import Check

STAGE = "validate_results"
CONFIG_SECTIONS = ("validation",)
PREVIOUS = travel_times.STAGE
REPORT_JSON, REPORT_MD = "report_results.json", "report_results.md"

log = logging.getLogger(__name__)


def _share_check(name: str, share: float, limits: ShareLimits, message: str) -> Check:
    status = "fail" if share < limits.fail_below else "warn" if share < limits.warn_below else "ok"
    return Check(name, status, round(share, 4), message, stage=STAGE)


def checks(
    times: pd.DataFrame, pairs: pd.DataFrame, cells: pd.DataFrame, distances: pd.Series, cfg
) -> list[Check]:
    """All checks of report part 2 (pure; frames as written by the stages)."""
    v = cfg.validation
    lim = v.results
    out: list[Check] = []
    modes = set(times["mode"])

    key = ["cell_id", "destination_id"]
    have = {m: times.loc[times["mode"] == m, key] for m in ("walk", "bike") if m in modes}
    missing = {
        m: len(
            pairs.merge(h.drop_duplicates(), on=key, how="left", indicator=True).query(
                "_merge == 'left_only'"
            )
        )
        for m, h in have.items()
    }
    bad = {m: n for m, n in missing.items() if n}
    out.append(
        Check(
            "pairs_complete",
            "fail" if bad or not have else "ok",
            sum(missing.values()),
            f"pairs without a time row: {bad}" if bad else f"{len(pairs)} pairs complete",
            stage=STAGE,
        )
    )

    campus = times[times["destination_id"].str.startswith("campus_site:")]
    populated = set(cells.loc[cells["populated"], "cell_id"])
    reach = campus.dropna(subset=["time_s"]).groupby("destination_id")["cell_id"].agg(set)
    sites = sorted(set(campus["destination_id"]))
    lacking = {s: len(populated - reach.get(s, set())) for s in sites}
    lacking = {s: n for s, n in lacking.items() if n}
    out.append(
        Check(
            "campus_routable",
            "fail" if lacking or not sites else "ok",
            sum(lacking.values()),
            (
                f"populated cells without a route to {lacking}"
                if lacking
                else f"{len(sites)} campus sites reachable from every populated cell"
            ),
            stage=STAGE,
        )
    )

    shares = times.groupby("mode")["time_s"].apply(lambda s: float(s.isna().mean())).to_dict()
    worst = max(shares.values()) if shares else 1.0
    status = (
        "fail"
        if worst > lim.unreachable_fail_above
        else "warn"
        if worst > lim.unreachable_warn_above
        else "ok"
    )
    out.append(
        Check(
            "unreachable_share",
            status,
            round(worst, 4),
            "share without a time per mode: "
            + ", ".join(f"{m} {s:.2%}" for m, s in shares.items()),
            stage=STAGE,
        )
    )

    if {"walk", "bike"} <= modes:
        w = times[times["mode"] == "walk"].set_index(key)["time_s"]
        b = times[times["mode"] == "bike"].set_index(key)["time_s"]
        both = pd.concat([w.rename("w"), b.rename("b")], axis=1).dropna()
        share = float((both["b"] <= both["w"]).mean()) if len(both) else 0.0
        out.append(
            _share_check(
                "bike_not_slower_than_walk",
                share,
                v.bike_not_slower_than_walk,
                f"bike ≤ walk for {share:.1%} of {len(both)} pairs",
            )
        )

    tr = times[times["mode"].isin(["transit", "bike_transit"]) & ~times["walk_only"]].dropna(
        subset=["time_s"]
    )
    if len(tr):
        d = distances.reindex(pd.MultiIndex.from_frame(tr[key])).to_numpy()
        kmh = d / 1000 / (tr["time_s"].to_numpy(float) / 3600)
        fast = int(np.nansum(kmh > lim.max_transit_kmh))
        out.append(
            Check(
                "transit_speed",
                "fail" if fast else "ok",
                fast,
                f"{fast} transit trips faster than {lim.max_transit_kmh} km/h straight line",
                stage=STAGE,
            )
        )
        legs = tr[["access_s", "wait_s", "in_vehicle_s", "egress_s"]].sum(axis=1)
        off = int((abs(legs - tr["time_s"]) > 2).sum())
        out.append(
            Check(
                "transit_legs_add_up",
                "warn" if off else "ok",
                off,
                f"{off} of {len(tr)} transit trips whose legs do not add up to the time",
                stage=STAGE,
            )
        )
    night = times[
        (times["mode"] == "transit") & times["destination_id"].str.startswith("nightlife:")
    ]
    if len(night):
        med = night.groupby("trip_window")["time_s"].median().div(60).round(1).to_dict()
        out.append(
            Check(
                "night_transit_median",
                "ok",
                None,
                f"median transit minutes to/from nightlife per window: {med}",
                stage=STAGE,
            )
        )
    return out


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Validation report part 2 — results ({report['run_id']})",
        "",
        f"Status: **{report['status']}** · generated {report['generated_at']}",
        "",
        "| Check | Status | Value | Message |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {c['check']} | {c['status']} | {'' if c['value'] is None else c['value']} "
        f"| {c['message']} |"
        for c in report["checks"]
    ]
    return "\n".join(lines) + "\n"


def run(ctx: RunContext) -> Manifest:
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    tdir, vdir = ctx.stage_dir(travel_times.STAGE), ctx.stage_dir(validate.STAGE)
    stage_dir = ctx.stage_dir(STAGE)
    files = [tdir / travel_times.OUT, tdir / travel_times.PAIRS, vdir / "cells.parquet"]
    started_at = datetime.now(UTC)
    with measure() as m:
        times = pd.read_parquet(files[0])
        pairs = pd.read_parquet(files[1])
        cells = gpd.read_parquet(files[2])
        tpairs = times[["cell_id", "destination_id"]].drop_duplicates()
        distances = _distances(ctx, tpairs, cells)
        report_checks = checks(times, pairs, cells, distances, ctx.config)
    failed = [c.check for c in report_checks if c.status == "fail"]
    report = {
        "run_id": ctx.run_id,
        "stage": STAGE,
        "status": "fail" if failed else "ok",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "checks": [asdict(c) for c in report_checks],
        "runtime_s": m.runtime_s,
        "peak_rss_mb": m.peak_rss_mb,
    }
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / REPORT_JSON).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (stage_dir / REPORT_MD).write_text(_markdown(report), encoding="utf-8")
    for c in report_checks:
        (log.error if c.status == "fail" else log.warning if c.status == "warn" else log.info)(
            "check %s: %s — %s", c.check, c.status, c.message
        )
    if failed:
        raise StageValidationError(f"result validation failed: {failed} (see {REPORT_MD})")
    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=[config_input(ctx.config, CONFIG_SECTIONS), *file_inputs(files)],
        outputs=[FileOutput(path=str(stage_dir / n)) for n in (REPORT_JSON, REPORT_MD)],
        message=f"{len(report_checks)} checks, status {report['status']}",
    )
    write_manifest(manifest, stage_dir)
    return manifest


def _distances(ctx: RunContext, pairs: pd.DataFrame, cells: gpd.GeoDataFrame) -> pd.Series:
    """Straight-line metres per cell × destination (first point of each destination)."""
    _, points = travel_times.load_inputs(ctx)
    first = points.drop_duplicates("destination_id").set_index("destination_id").geometry
    origin = cells.set_index("cell_id")["origin_geom"]
    o = gpd.GeoSeries(origin.reindex(pairs["cell_id"]).to_numpy(), crs=validate.METRIC_CRS)
    d = gpd.GeoSeries(first.reindex(pairs["destination_id"]).to_numpy(), crs=validate.METRIC_CRS)
    return pd.Series(o.distance(d).to_numpy(), index=pd.MultiIndex.from_frame(pairs))
