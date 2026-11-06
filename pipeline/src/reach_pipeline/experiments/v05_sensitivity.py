"""V5 sensitivity: k_c, walking speed (3.39 vs. 5.0 km/h) and the time budget.

- k_c ± shift and budgets below the facility budget are derived from the stored counts and
  matrix times (`reachable`), without routing.
- Budgets above it recount the base profile on the demo Valhalla (same blocks and matrix).
- Recommendations: greedy on the stored catchments with shifted k (catchments depend on the
  budget, so budgets are not replayed); speed compares the stored top-N of both profiles.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
import pandas as pd

from reach_pipeline import recommend as rec
from reach_pipeline.experiments import common
from reach_pipeline.experiments.common import Experiment
from reach_pipeline.stages import count as count_stage

NAME = "v05"
TITLE = "Sensitivity: k_c, walking speed, time budget"

log = logging.getLogger(__name__)


def top_sets(recs: pd.DataFrame) -> dict[tuple[str, str], set[str]]:
    return {key: set(g["candidate_id"]) for key, g in recs.groupby(["profile_id", "category"])}


def near_count(xy: pd.DataFrame, ref: set[str], alt: set[str], radius_m: float) -> int:
    """Zones of `ref` with a zone of `alt` within `radius_m` (centre to centre)."""
    if not ref or not alt:
        return 0
    a, b = xy.loc[sorted(ref)].to_numpy(), xy.loc[sorted(alt)].to_numpy()
    d = np.hypot(a[:, None, 0] - b[None, :, 0], a[:, None, 1] - b[None, :, 1])
    return int((d.min(axis=1) <= radius_m).sum())


def greedy_picks(e: Experiment, profile_id: str, k: pd.Series, top_n: int) -> dict[str, list[str]]:
    """Greedy candidate ids per category on the stored catchments of a profile with k."""
    cells = e.cells
    cell_ids = cells["cell_id"].to_numpy()
    cand_ids = e.candidates["candidate_id"].to_numpy()
    cat = e.catchments[e.catchments["profile_id"] == profile_id]
    cover = np.zeros((len(cand_ids), len(cell_ids)), dtype=bool)
    cover[
        pd.Index(cand_ids).get_indexer(cat["candidate_id"]),
        pd.Index(cell_ids).get_indexer(cat["cell_id"]),
    ] = True
    a = e.access[e.access["profile_id"] == profile_id].set_index(["category", "cell_id"])["count"]
    out = {}
    for c in e.cfg.categories:
        counts = a.xs(c.id).reindex(cell_ids).to_numpy()
        picks = rec.greedy(
            cover,
            cells["population"].to_numpy(),
            counts,
            int(k[c.id]),
            top_n,
            e.cfg.recommend.min_gain,
        )
        out[c.id] = [str(cand_ids[p.candidate]) for p in picks]
    return out


def run(e: Experiment) -> dict[str, Any]:
    s = e.settings.v05
    cfg = e.cfg
    base_pid = s.base_profile
    k = e.k()
    budget = cfg.time_budgets_min.facilities
    cells = e.cells
    base = e.access[e.access["profile_id"] == base_pid]
    base_d = common.district_deficits(base, cells, k)
    scenarios: dict[str, pd.DataFrame] = {}
    rankings: dict[str, pd.DataFrame] = {}

    # k_c shifts.
    for shift in s.k_shifts:
        k_alt = (k + shift).clip(lower=1)
        name = f"k{shift:+d}"
        scenarios[name] = common.compare(base, base, cells, k, k_alt)
        rankings[name] = common.ranking_agreement(
            base_d, common.district_deficits(base, cells, k_alt), s.top_districts
        )

    # Speed: the 5.0 km/h profile against the base profile (same costing, only speed differs).
    fast = next(
        (
            pid
            for pid, p in cfg.profiles.items()
            if pid != base_pid
            and p.costing == cfg.profiles[base_pid].costing
            and p.costing_options == cfg.profiles[base_pid].costing_options
        ),
        None,
    )
    if fast:
        alt = e.access[e.access["profile_id"] == fast].assign(profile_id=base_pid)
        scenarios[f"speed_{fast}"] = common.compare(base, alt, cells, k)
        rankings[f"speed_{fast}"] = common.ranking_agreement(
            base_d, common.district_deficits(alt, cells, k), s.top_districts
        )

    # Budgets below the facility budget, from the stored matrix times.
    categories = [c.id for c in cfg.categories]
    for b in s.budgets_from_reachable:
        if b >= budget:
            raise ValueError(f"v05.budgets_from_reachable: {b} min is not below {budget} min")
        alt = common.counts_within(
            e.reachable, e.facilities, cells["cell_id"].to_numpy(), categories, base_pid, b * 60
        )
        scenarios[f"budget_{b:g}"] = common.compare(base, alt, cells, k)
        rankings[f"budget_{b:g}"] = common.ranking_agreement(
            base_d, common.district_deficits(alt, cells, k), s.top_districts
        )
    recount_stats: dict[str, Any] = {}
    reproduced = None
    if s.budgets_recount:
        count_stage.check_valhalla_config(e.ctx)
        data = common.load_count_data(e.ctx)
        # The recount at the run's own budget must give the run's counts (method check).
        same, _, _ = asyncio.run(common.recount(cfg, data, [base_pid], budget))
        keys = ["cell_id", "category", "profile_id"]
        m = base.merge(same, on=keys, suffixes=("", "_recount"), validate="one_to_one")
        reproduced = {
            "rows": int(len(m)),
            "rows_differing": int((m["count"] != m["count_recount"]).sum()),
        }
        for b in s.budgets_recount:
            alt, _, st = asyncio.run(common.recount(cfg, data, [base_pid], b))
            recount_stats[f"{b:g}"] = st[base_pid]
            scenarios[f"budget_{b:g}"] = common.compare(base, alt, cells, k)
            rankings[f"budget_{b:g}"] = common.ranking_agreement(
                base_d, common.district_deficits(alt, cells, k), s.top_districts
            )

    # Recommendations: same zones, and zones with an alternative zone within near_radius_m.
    stored = top_sets(e.recommendations)
    cand_xy = pd.DataFrame(
        common.xy(e.candidates.geometry), index=e.candidates["candidate_id"], columns=["x", "y"]
    )

    def row(scenario: str, cat: str, ref: set[str], alt: set[str]) -> dict[str, Any]:
        return {
            "scenario": scenario,
            "category": cat,
            "stored": len(ref),
            "alt": len(alt),
            "same_zones": len(ref & alt),
            "near_zones": near_count(cand_xy, ref, alt, s.near_radius_m),
        }

    rec_rows = []
    top_n = cfg.recommend.top_n
    if base_pid in cfg.recommend.profiles:
        for shift in s.k_shifts:
            picks = greedy_picks(e, base_pid, (k + shift).clip(lower=1), top_n)
            for cat, ids in picks.items():
                rec_rows.append(
                    row(f"k{shift:+d}", cat, stored.get((base_pid, cat), set()), set(ids))
                )
        if fast in cfg.recommend.profiles:
            for c in cfg.categories:
                ref, alt_ids = stored.get((base_pid, c.id), set()), stored.get((fast, c.id), set())
                rec_rows.append(row(f"speed_{fast}", c.id, ref, alt_ids))

    table = pd.concat([f.assign(scenario=n) for n, f in scenarios.items()], ignore_index=True)
    rank_table = pd.concat([f.assign(scenario=n) for n, f in rankings.items()], ignore_index=True)
    recs = pd.DataFrame(rec_rows)
    e.write_table("classes.csv", table)
    e.write_table("district_rankings.csv", rank_table)
    e.write_table("recommendations.csv", recs)

    summary = (
        table.groupby("scenario")
        .agg(residents_changed=("residents_changed", "sum"), residents=("residents", "sum"))
        .assign(share=lambda d: (d["residents_changed"] / d["residents"]).round(4))
    )
    spearman = rank_table.groupby("scenario")["spearman"].agg(["min", "median"]).round(3)
    overlap = (
        recs.groupby("scenario")[["same_zones", "near_zones", "stored"]].sum()
        if len(recs)
        else pd.DataFrame()
    )
    return {
        "status": "done",
        "base_profile": base_pid,
        "speed_profile": fast,
        "scenarios": {
            n: {
                "share_resident_class_changes": float(summary.loc[n, "share"]),
                "district_spearman_min": float(spearman.loc[n, "min"]),
                "district_spearman_median": float(spearman.loc[n, "median"]),
                "recommendations_same": (
                    f"{int(overlap.loc[n, 'same_zones'])}/{int(overlap.loc[n, 'stored'])}"
                    if n in overlap.index
                    else None
                ),
                f"recommendations_within_{s.near_radius_m:g}m": (
                    f"{int(overlap.loc[n, 'near_zones'])}/{int(overlap.loc[n, 'stored'])}"
                    if n in overlap.index
                    else None
                ),
            }
            for n in scenarios
        },
        "lack_share": common.records(
            table.pivot_table(index="category", columns="scenario", values="share_lack_alt")
            .join(table.groupby("category")["share_lack_base"].first())
            .reset_index()
        ),
        "recount": recount_stats,
        "recount_reproduces_run": reproduced,
    }
