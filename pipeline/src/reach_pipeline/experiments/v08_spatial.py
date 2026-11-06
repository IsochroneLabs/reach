"""V8 spatial autocorrelation of deficits: global and local Moran's I (methodology M5).

Variables per scored cell (profile `v08.profile`): the unmet share max(0, 1 − A/k) per category
(the deficit per resident) and the number of categories in "lack" (0–6). Neighbours: cells whose
centres are at most `neighbour_distance_m` apart (queen contiguity on the 100 m grid), row-
standardised; cells without neighbours (isolated Teilort cells) are left out. Significance by
permutation (`permutations`): global I by random relabelling, local I (LISA) by conditional
permutation (neighbour values drawn from the other cells, with replacement), pseudo p-values
as in PySAL, no multiple-testing correction. District level: Moran's I of the share of
residents in lack, districts as neighbours when their boundaries touch. Implemented with NumPy
only (no new dependency).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import shapely

from reach_pipeline.experiments import common
from reach_pipeline.experiments.common import Experiment

NAME = "v08"
TITLE = "Spatial autocorrelation of deficits (Moran's I, LISA)"
QUADRANTS = {1: "high-high", 2: "low-high", 3: "low-low", 4: "high-low"}


def distance_neighbours(xy: np.ndarray, distance_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Pairs (i, j), i != j, of points at most `distance_m` apart (both directions)."""
    pts = shapely.points(xy)
    i, j = shapely.STRtree(pts).query(pts, predicate="dwithin", distance=distance_m)
    keep = i != j
    return i[keep], j[keep]


def touching_neighbours(geoms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pairs (i, j), i != j, of polygons that share a boundary point."""
    i, j = shapely.STRtree(geoms).query(geoms, predicate="intersects")
    keep = i != j
    return i[keep], j[keep]


def _weights(i: np.ndarray, n: int) -> np.ndarray:
    deg = np.bincount(i, minlength=n)
    return 1.0 / deg[i]


def lag(values: np.ndarray, i: np.ndarray, j: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Spatial lag sum_j w_ij x_j (row-standardised weights)."""
    return np.bincount(i, weights=w * values[j], minlength=len(values))


def global_moran(
    x: np.ndarray, i: np.ndarray, j: np.ndarray, permutations: int, rng: np.random.Generator
) -> dict[str, float]:
    """Moran's I with row-standardised weights, expected value and pseudo p (one-sided for the
    observed sign). Cells without neighbours must already be removed."""
    n = len(x)
    z = x - x.mean()
    m2 = (z**2).sum()
    if m2 == 0:
        return {"I": float("nan"), "expected": -1 / (n - 1), "p": float("nan"), "n": n}
    w = _weights(i, n)
    observed = float((z * lag(z, i, j, w)).sum() / m2)  # S0 = n for row-standardised weights
    sims = np.empty(permutations)
    for p in range(permutations):
        zp = rng.permutation(z)
        sims[p] = (zp * lag(zp, i, j, w)).sum() / m2
    larger = int((sims >= observed).sum())
    if larger > permutations / 2:
        larger = permutations - larger
    return {
        "I": round(observed, 4),
        "expected": round(-1 / (n - 1), 4),
        "p": round((larger + 1) / (permutations + 1), 4),
        "z": round(float((observed - sims.mean()) / sims.std()), 2),
        "n": n,
    }


def local_moran(
    x: np.ndarray,
    i: np.ndarray,
    j: np.ndarray,
    permutations: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """LISA: local I, quadrant (1 HH, 2 LH, 3 LL, 4 HL) and pseudo p per observation."""
    n = len(x)
    z = x - x.mean()
    m2 = (z**2).sum() / n
    w = _weights(i, n)
    zl = lag(z, i, j, w)
    local = z * zl / m2 if m2 else np.zeros(n)
    deg = np.bincount(i, minlength=n)
    kmax = int(deg.max())
    # Conditional permutation: for each i, deg_i values drawn from the other n-1 observations.
    draws = rng.integers(0, n - 1, size=(n, permutations, kmax))
    draws = draws + (draws >= np.arange(n)[:, None, None])  # skip i itself
    mask = np.arange(kmax)[None, None, :] < deg[:, None, None]
    sim_lag = (z[draws] * mask).sum(axis=2) / deg[:, None]
    sims = z[:, None] * sim_lag / m2 if m2 else np.zeros((n, permutations))
    larger = (sims >= local[:, None]).sum(axis=1)
    larger = np.where(larger > permutations / 2, permutations - larger, larger)
    quadrant = np.select(
        [(z > 0) & (zl > 0), (z <= 0) & (zl > 0), (z <= 0) & (zl <= 0)], [1, 2, 3], 4
    )
    return pd.DataFrame(
        {"local_i": local, "quadrant": quadrant, "p": (larger + 1) / (permutations + 1)}
    )


def run(e: Experiment) -> dict[str, Any]:
    s = e.settings.v08
    cells = e.cells.reset_index(drop=True)
    k = e.k()
    acc = e.access[e.access["profile_id"] == s.profile]
    unmet = acc.assign(
        unmet=np.maximum(0.0, 1 - acc["count"] / k.reindex(acc["category"]).to_numpy()),
        lack=acc["count"] == 0,
    )
    wide = unmet.pivot(index="cell_id", columns="category", values="unmet").reindex(
        cells["cell_id"]
    )
    wide["categories_lack"] = (
        unmet.groupby("cell_id")["lack"].sum().reindex(cells["cell_id"]).to_numpy()
    )
    i, j = distance_neighbours(common.xy(cells.geometry.centroid), s.neighbour_distance_m)
    has = np.bincount(i, minlength=len(cells)) > 0
    keep = np.flatnonzero(has)
    remap = np.full(len(cells), -1)
    remap[keep] = np.arange(len(keep))
    i, j = remap[i], remap[j]
    rng = e.rng(8)
    globals_ = {}
    for col in wide.columns:
        globals_[col] = global_moran(wide[col].to_numpy(float)[keep], i, j, s.permutations, rng)

    lisa = local_moran(wide["categories_lack"].to_numpy(float)[keep], i, j, s.permutations, rng)
    lisa.insert(0, "cell_id", cells["cell_id"].to_numpy()[keep])
    lisa["population"] = cells["population"].to_numpy()[keep]
    lisa["categories_lack"] = wide["categories_lack"].to_numpy()[keep]
    lisa["cluster"] = np.where(
        lisa["p"] <= s.significance, lisa["quadrant"].map(QUADRANTS), "not significant"
    )
    lisa.to_parquet(e.out / "lisa.parquet", index=False)
    clusters = (
        lisa.groupby("cluster")
        .agg(cells=("cell_id", "size"), residents=("population", "sum"))
        .reset_index()
    )
    hh = lisa[lisa["cluster"] == "high-high"].merge(cells[["cell_id", "district_id"]], on="cell_id")
    hh_districts = (
        hh.merge(e.districts[["district_id", "name"]], on="district_id")
        .groupby("name")["population"]
        .sum()
        .sort_values(ascending=False)
    )

    # District level.
    d = common.district_deficits(acc, cells, k)
    districts = e.districts.reset_index(drop=True)
    di, dj = touching_neighbours(districts.geometry.values)
    d_has = np.bincount(di, minlength=len(districts)) > 0
    d_keep = np.flatnonzero(d_has)
    d_map = np.full(len(districts), -1)
    d_map[d_keep] = np.arange(len(d_keep))
    di, dj = d_map[di], d_map[dj]
    district_global = {}
    for cat, g in d.groupby("category"):
        share = (
            g.set_index("district_id")["share_lack"]
            .reindex(districts["district_id"])
            .fillna(0)
            .to_numpy()
        )
        district_global[cat] = global_moran(share[d_keep], di, dj, s.permutations, rng)
    e.notes.append(
        f"{int((~has).sum())} cells without a neighbour within {s.neighbour_distance_m:g} m "
        "left out; LISA p-values are not corrected for multiple testing."
    )
    return {
        "status": "done",
        "profile": s.profile,
        "cells": int(len(keep)),
        "neighbour_pairs": int(len(i)),
        "global_cells": globals_,
        "lisa_categories_lack": common.records(clusters),
        "high_high_residents_by_district": {k_: int(v) for k_, v in hh_districts.head(8).items()},
        "global_districts_share_lack": district_global,
        "districts": int(len(d_keep)),
    }
