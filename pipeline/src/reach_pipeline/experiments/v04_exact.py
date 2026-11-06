"""V4 greedy vs. exact solution (MILP) of the recommender objective.

For N new facilities of a category the exact problem is

    max  sum_i P_i z_i
    s.t. z_i <= (A_i + sum_j a_ij x_j) / k,  0 <= z_i <= 1,  sum_j x_j = N,  x_j binary

(a_ij = 1 if cell i reaches candidate j). At the optimum z_i = min(1, (A_i + new_i) / k), so
the objective minus sum_i P_i min(1, A_i / k) is the total gain sum ΔW of methodology §5.
Cells that are already sufficient and candidates without an insufficient cell in their catchment
are dropped (they cannot change the objective). Solved with PuLP and HiGHS (dev dependencies,
imported here only); the instances are the run's stored catchments, so greedy and MILP see
exactly the same data.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from reach_pipeline import recommend as rec
from reach_pipeline.experiments.common import Experiment, records

NAME = "v04"
TITLE = "Greedy vs. exact solution (MILP)"


def covered_gain(cover: np.ndarray, pop: np.ndarray, counts: np.ndarray, k: int, picks) -> float:
    """Total deficit reduction of a set of candidates (each adds one facility)."""
    new = cover[list(picks)].sum(axis=0) if len(picks) else np.zeros(cover.shape[1])
    before = np.minimum(1.0, counts / k)
    after = np.minimum(1.0, (counts + new) / k)
    return float((pop * (after - before)).sum())


def reduce_instance(
    cover: np.ndarray, pop: np.ndarray, counts: np.ndarray, k: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Keep cells with A < k and candidates reaching at least one of them; returns the reduced
    cover, population, counts and the kept candidate indices."""
    needy = counts < k
    cand = np.flatnonzero(cover[:, needy].any(axis=1))
    return cover[np.ix_(cand, needy)], pop[needy], counts[needy], cand


def solve_exact(
    cover: np.ndarray, pop: np.ndarray, counts: np.ndarray, k: int, n: int, time_limit_s: float
) -> dict[str, Any]:
    """MILP optimum for N sites; returns chosen candidate indices, gain, objective and status."""
    import pulp

    red, p, a, cand = reduce_instance(cover, pop, counts, k)
    n = min(n, len(cand))
    if n == 0:
        return {"picks": [], "gain": 0.0, "status": "Optimal", "candidates": 0}
    prob = pulp.LpProblem("recommender", pulp.LpMaximize)
    x = [prob.add_variable(f"x{j}", cat="Binary") for j in range(len(cand))]
    z = [prob.add_variable(f"z{i}", lowBound=0, upBound=1) for i in range(len(p))]
    prob += pulp.lpSum(float(p[i]) * z[i] for i in range(len(p)))
    cols = [np.flatnonzero(red[:, i]) for i in range(len(p))]
    for i, js in enumerate(cols):
        prob += k * z[i] <= float(a[i]) + pulp.lpSum(x[j] for j in js)
    prob += pulp.lpSum(x) == n
    solver = pulp.HiGHS(msg=False, timeLimit=time_limit_s)
    prob.solve(solver)
    chosen = [int(cand[j]) for j in range(len(cand)) if (x[j].value() or 0) > 0.5]
    objective = float(pulp.value(prob.objective) or 0.0)
    return {
        "picks": chosen,
        "gain": covered_gain(cover, pop, counts, k, chosen),
        "objective": objective,
        "status": pulp.LpStatus[prob.status],
        "candidates": int(len(cand)),
    }


def run(e: Experiment) -> dict[str, Any]:
    s = e.settings.v04
    cells = e.cells
    cell_ids = cells["cell_id"].to_numpy()
    pop = cells["population"].to_numpy().astype(float)
    cand_ids = e.candidates["candidate_id"].to_numpy()
    k_of = e.k()
    rows = []
    for pid in s.profiles:
        cat = e.catchments[e.catchments["profile_id"] == pid]
        cover = np.zeros((len(cand_ids), len(cell_ids)), dtype=bool)
        cover[
            pd.Index(cand_ids).get_indexer(cat["candidate_id"]),
            pd.Index(cell_ids).get_indexer(cat["cell_id"]),
        ] = True
        access = e.access[e.access["profile_id"] == pid].set_index(["category", "cell_id"])
        for c in e.cfg.categories:
            k = c.k
            counts = access.loc[c.id]["count"].reindex(cell_ids).to_numpy()
            for n in s.n_sites:
                t0 = time.perf_counter()
                g = rec.greedy(cover, pop, counts, int(k_of[c.id]), n, 0.0)
                t_greedy = time.perf_counter() - t0
                g_idx = [p.candidate for p in g]
                g_gain = covered_gain(cover, pop, counts, k, g_idx)
                t0 = time.perf_counter()
                ex = solve_exact(cover, pop, counts, k, n, s.time_limit_s)
                t_exact = time.perf_counter() - t0
                gap = (ex["gain"] - g_gain) / ex["gain"] if ex["gain"] > 0 else 0.0
                rows.append(
                    {
                        "profile_id": pid,
                        "category": c.id,
                        "k": k,
                        "n_sites": n,
                        "candidates": ex["candidates"],
                        "greedy_sites": len(g_idx),
                        "greedy_gain": round(g_gain, 1),
                        "exact_gain": round(ex["gain"], 1),
                        "exact_status": ex["status"],
                        "optimality_gap": round(gap, 5),
                        "same_sites": len(set(g_idx) & set(ex["picks"])),
                        "greedy_s": round(t_greedy, 3),
                        "exact_s": round(t_exact, 2),
                    }
                )
    table = pd.DataFrame(rows)
    e.write_table("instances.csv", table)
    worst = table.sort_values("optimality_gap", ascending=False).iloc[0]
    return {
        "status": "done",
        "instances": len(table),
        "optimal": int((table["exact_status"] == "Optimal").sum()),
        "max_optimality_gap": float(table["optimality_gap"].max()),
        "mean_optimality_gap": round(float(table["optimality_gap"].mean()), 5),
        "instances_with_gap": int((table["optimality_gap"] > 1e-9).sum()),
        "worst": records(worst.to_frame().T)[0],
        "theoretical_bound": round(1 - 1 / np.e, 4),
        "exact_s_max": float(table["exact_s"].max()),
    }
