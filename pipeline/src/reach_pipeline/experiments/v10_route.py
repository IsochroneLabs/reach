"""V10 matrix vs. /route with larger samples than `validate_results` (report part 2).

The checks of `validate_results` (`matrix_vs_route`, `false_negatives`, `budget_flips`) run
again with the sample sizes of `v10` and only the profiles listed there; the run's own report
part 2 (small samples, every run) is quoted next to them. Same functions, same Valhalla config
as `count` (checked first).
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import numpy as np

from reach_pipeline import results
from reach_pipeline.context import RunContext
from reach_pipeline.experiments.common import Experiment
from reach_pipeline.stages import validate_results as vr

NAME = "v10"
TITLE = "Matrix vs. /route (larger samples)"


def _config(e: Experiment):
    s = e.settings.v10
    cfg = e.cfg
    res = cfg.validation.results
    res = res.model_copy(
        update={
            "route_check": res.route_check.model_copy(
                update={
                    "pairs_per_profile": s.pairs_per_profile,
                    "near_budget_share": s.near_budget_share,
                }
            ),
            "false_negatives": res.false_negatives.model_copy(
                update={"pairs_per_category": s.false_negative_pairs_per_category}
            ),
        }
    )
    return cfg.model_copy(
        update={
            "profiles": {p: cfg.profiles[p] for p in s.profiles},
            "validation": cfg.validation.model_copy(update={"results": res}),
        }
    )


def run(e: Experiment) -> dict[str, Any]:
    vr.require_count_valhalla(e.ctx)
    cfg = _config(e)
    ctx = RunContext(config=cfg, config_path=e.ctx.config_path, run_id=e.ctx.run_id)
    t, origins = vr.load_tables(ctx)
    t = dataclasses.replace(t, reachable=t.reachable[t.reachable["profile_id"].isin(cfg.profiles)])
    rc = cfg.validation.results.route_check
    budget_s = cfg.time_budgets_min.facilities * 60
    # Another seed than the stage, so the larger sample is not the stage's sample plus more.
    pairs = results.route_sample(t.reachable, budget_s, rc, e.settings.seed + 10)
    pairs = vr._with_routes(ctx, pairs, origins)
    route_check, route_profiles = results.route_check(pairs, budget_s, rc)
    pairs.to_csv(e.out / "route_pairs.csv", index=False)
    d = (pairs["route_s"] - pairs["time_s"]).dropna()
    fn_check, fn = vr.check_false_negatives(ctx, t, origins)
    flips, flip_detail = results.budget_flips(
        {"profiles": route_profiles}, fn, cfg.validation.results.budget_flips
    )
    stage = json.loads((e.ctx.stage_dir(vr.STAGE) / vr.REPORT_JSON).read_text(encoding="utf-8"))
    return {
        "status": "done",
        "profiles": list(cfg.profiles),
        "matrix_vs_route": {
            "check": dataclasses.asdict(route_check),
            "profiles": route_profiles,
            "delta_s_percentiles": {
                q: round(float(np.percentile(d, q)), 1) for q in (1, 5, 50, 95, 99)
            }
            if len(d)
            else {},
            "share_abs_delta_le_5s": round(float((d.abs() <= 5).mean()), 4) if len(d) else None,
        },
        "false_negatives": {"check": dataclasses.asdict(fn_check), **fn},
        "budget_flips": {"check": dataclasses.asdict(flips), **flip_detail},
        "stage_report": {
            c["check"]: {"status": c["status"], "value": c["value"], "message": c["message"]}
            for c in stage["checks"]
            if c["check"] in ("matrix_vs_route", "false_negatives", "budget_flips")
        },
    }
