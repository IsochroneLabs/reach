"""V3 recommender back-test: remove existing facilities, then check whether greedy finds sites
near them again.

Per category and repetition a random share of the category's facilities inside the urban
boundary is removed; counts drop by the removed facilities each cell reaches (`reachable`).
Greedy (methodology §5) then picks as many zones as were removed, on the stored candidate
catchments of the run. Measured: share of picks within r of a removed facility, share of
removed facilities with a pick within r, and how much of the deficit the removal created the
picks win back. Baseline: the same number of random routed candidates.
Existing sites are not optimal, so a low hit rate does not mean the recommender is wrong.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import shapely

from reach_pipeline import recommend as rec
from reach_pipeline import scoring
from reach_pipeline.experiments import common
from reach_pipeline.experiments.common import Experiment

NAME = "v03"
MODES = ("all_deficits", "created_only")
TITLE = "Recommender back-test (remove and recover facilities)"


def hit_rates(pick_xy: np.ndarray, removed_xy: np.ndarray, radius_m: float) -> tuple[float, float]:
    """(share of picks within `radius_m` of a removed facility, share of removed facilities
    within `radius_m` of a pick)."""
    if len(pick_xy) == 0 or len(removed_xy) == 0:
        return 0.0, 0.0
    d = np.hypot(
        pick_xy[:, None, 0] - removed_xy[None, :, 0], pick_xy[:, None, 1] - removed_xy[None, :, 1]
    )
    close = d <= radius_m
    return float(close.any(axis=1).mean()), float(close.any(axis=0).mean())


def _share(value: float, created: float) -> float | None:
    return round(value / created, 4) if created > 0 else None


def deficit_after(
    population: np.ndarray, counts: np.ndarray, k: int, cover: np.ndarray, picks: list[int]
) -> float:
    a = counts.astype(np.int64).copy()
    for j in picks:
        a[cover[j]] += 1
    return float(scoring.deficit(population, a, k).sum())


def run(e: Experiment) -> dict[str, Any]:
    s = e.settings.v03
    cells = e.cells
    cell_ids = cells["cell_id"].to_numpy()
    pop = cells["population"].to_numpy().astype(float)
    cand = e.candidates
    cand_ids = cand["candidate_id"].to_numpy()
    cand_xy = common.xy(cand.geometry)
    cat = e.catchments[e.catchments["profile_id"] == s.profile]
    cover = np.zeros((len(cand_ids), len(cell_ids)), dtype=bool)
    cover[
        pd.Index(cand_ids).get_indexer(cat["candidate_id"]),
        pd.Index(cell_ids).get_indexer(cat["cell_id"]),
    ] = True
    routed = np.flatnonzero(cover.any(axis=1))
    urban = e.urban_boundary.geometry.union_all()
    fac = e.facilities
    reach = e.reachable[e.reachable["profile_id"] == s.profile]
    access = e.access[e.access["profile_id"] == s.profile].set_index(["category", "cell_id"])
    k_of = e.k()
    rng = e.rng(3)
    rows = []
    for c in s.categories:
        k = int(k_of[c])
        f = fac[(fac["category"] == c) & shapely.within(fac.geometry.values, urban)]
        counts0 = access.loc[c]["count"].reindex(cell_ids).to_numpy()
        n_remove = max(1, round(len(f) * s.remove_share))
        for rep in range(s.repetitions):
            removed = f.iloc[np.sort(rng.choice(len(f), size=n_remove, replace=False))]
            hits = reach[reach["facility_id"].isin(set(removed["facility_id"]))]
            drop = hits.groupby("cell_id").size().reindex(cell_ids, fill_value=0).to_numpy()
            counts = counts0 - drop
            d_orig = float(scoring.deficit(pop, counts0, k).sum())
            d_removed = float(scoring.deficit(pop, counts, k).sum())
            created = d_removed - d_orig
            random_idx = list(rng.choice(routed, size=n_remove, replace=False))
            r_xy = common.xy(removed.geometry)
            for mode in MODES:
                # created_only: cells with a deficit before the removal cannot gain.
                a = counts if mode == "all_deficits" else np.where(counts0 < k, k, counts)
                idx = [p.candidate for p in rec.greedy(cover, pop, a, k, n_remove, 0.0)]
                d_start = float(scoring.deficit(pop, a, k).sum())
                row = {
                    "category": c,
                    "mode": mode,
                    "repetition": rep,
                    "facilities_in_urban_boundary": len(f),
                    "removed": n_remove,
                    "picks": len(idx),
                    "deficit_created": round(created, 1),
                    # Deficit won back, as a share of what the removal created (1 = as much as
                    # restoring the removed facilities; above 1 in all_deficits, because older
                    # deficits are won back too).
                    "recovered_share": _share(
                        d_start - deficit_after(pop, a, k, cover, idx), created
                    ),
                    "recovered_share_random": _share(
                        d_start - deficit_after(pop, a, k, cover, random_idx[: len(idx)]),
                        created,
                    ),
                }
                for radius in s.hit_radius_m:
                    p_hit, f_hit = hit_rates(cand_xy[idx], r_xy, radius)
                    b_hit, _ = hit_rates(cand_xy[random_idx[: len(idx)]], r_xy, radius)
                    row[f"picks_near_removed_{radius:g}m"] = round(p_hit, 4)
                    row[f"removed_recovered_{radius:g}m"] = round(f_hit, 4)
                    row[f"random_near_removed_{radius:g}m"] = round(b_hit, 4)
                rows.append(row)
    table = pd.DataFrame(rows)
    e.write_table("repetitions.csv", table)
    per_cat = (
        table.drop(columns="repetition")
        .groupby(["mode", "category"])
        .mean(numeric_only=True)
        .round(3)
    )
    nearest = shapely.STRtree(shapely.points(cand_xy[routed]))
    f_all = fac[fac["category"].isin(s.categories) & shapely.within(fac.geometry.values, urban)]
    _, dist = nearest.query_nearest(f_all.geometry.values, return_distance=True)
    e.notes.append(
        "Candidates are the run's routed candidates (within reach of a deficit cell); "
        f"{(dist <= 100).mean():.1%} of the facilities inside the urban boundary have one "
        "within 100 m, so a removed site can usually be picked again."
    )
    return {
        "status": "done",
        "profile": s.profile,
        "repetitions": s.repetitions,
        "remove_share": s.remove_share,
        "routed_candidates": int(len(routed)),
        "per_category": common.records(per_cat.reset_index()),
    }
