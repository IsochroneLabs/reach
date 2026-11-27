"""Routing targets per origin cell (arch. §6.3, O22): nearest k per type and per label.

Building block for the travel-time stage (S1.8): it decides which cell × destination pairs are
routed, before any engine is asked. For every origin and target group (a destination type, or one
label of a type) the `k` nearest destinations by straight line are kept; the union over all groups
is deduplicated per pair. "Nearest k" is exact: the search radius only limits work and never drops
a destination when fewer than `k` lie within it. Transit takes `transit_factor` × k candidates per
group, because the nearest by straight line is often not the nearest by bus.

Vectorised: one distance matrix per group and origin chunk, `argpartition` for the k smallest.
The loop runs over groups (dozens), never over cells or destinations.
"""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd

from reach_pipeline.config import Config

PAIR_COLUMNS = ["cell_id", "destination_id", "distance_m", "groups"]
# Origins per distance-matrix chunk: 2,000 × 1,000 destinations = 16 MB of float64.
_CHUNK = 2_000


@dataclass(frozen=True)
class Group:
    """Destinations that compete for the same `k` slots (a type or one label of a type)."""

    key: str
    k: int | None  # None: every destination of the group
    destinations: gpd.GeoDataFrame  # columns destination_id, geometry (points, EPSG:25832)


def _xy(points: gpd.GeoSeries) -> np.ndarray:
    return np.column_stack([points.x.to_numpy(), points.y.to_numpy()])


def nearest_k(origins: gpd.GeoDataFrame, group: Group, factor: int = 1) -> pd.DataFrame:
    """The `factor` × k nearest destinations of `group` for every origin (straight line).

    `origins` has `cell_id` and point geometries; the result has one row per pair with
    `cell_id`, `destination_id`, `distance_m` and `group`.
    """
    dest = group.destinations
    n_dest = len(dest)
    if n_dest == 0 or origins.empty:
        return pd.DataFrame(columns=["cell_id", "destination_id", "distance_m", "group"])
    k = n_dest if group.k is None else min(group.k * factor, n_dest)
    o_xy, d_xy = _xy(origins.geometry), _xy(dest.geometry)
    d_ids = dest["destination_id"].to_numpy()
    c_ids = origins["cell_id"].to_numpy()
    parts = []
    for start in range(0, len(origins), _CHUNK):
        o = o_xy[start : start + _CHUNK]
        dist = np.hypot(o[:, None, 0] - d_xy[None, :, 0], o[:, None, 1] - d_xy[None, :, 1])
        if k < n_dest:
            idx = np.argpartition(dist, k - 1, axis=1)[:, :k]
        else:
            idx = np.broadcast_to(np.arange(n_dest), dist.shape)
        rows = np.repeat(np.arange(len(o)), idx.shape[1])
        cols = idx.ravel()
        parts.append(
            pd.DataFrame(
                {
                    "cell_id": c_ids[start + rows],
                    "destination_id": d_ids[cols],
                    "distance_m": dist[rows, cols],
                }
            )
        )
    out = pd.concat(parts, ignore_index=True)
    out["group"] = group.key
    return out


def label_groups(labels: gpd.GeoDataFrame, k_label: int) -> list[Group]:
    """One group per offered label of `validate/destination_labels.parquet`."""
    offered = labels[labels["offered"]]
    return [
        Group(
            key=f"{dtype}:{kind}:{label}",
            k=k_label,
            destinations=g[["destination_id", "geometry"]].reset_index(drop=True),
        )
        for (dtype, kind, label), g in offered.groupby(
            ["destination_type", "label_kind", "label"], sort=True
        )
    ]


def type_groups(destinations: gpd.GeoDataFrame, cfg: Config) -> list[Group]:
    """One group per destination type with its `nearest_k` (S1.6 destinations)."""
    return [
        Group(
            key=dtype,
            k=cfg.destination_types[dtype].nearest_k,
            destinations=g[["destination_id", "geometry"]].reset_index(drop=True),
        )
        for dtype, g in destinations.groupby("destination_type", sort=True)
        if dtype in cfg.destination_types
    ]


def pairs(origins: gpd.GeoDataFrame, groups: list[Group], factor: int = 1) -> pd.DataFrame:
    """Union of the nearest-k pairs of all groups, one row per cell × destination.

    `groups` is the `;`-joined list of groups that selected the pair (for the report and for
    checks such as "label time ≥ type time").
    """
    found = [nearest_k(origins, g, factor) for g in groups]
    found = [f for f in found if not f.empty]
    if not found:
        return pd.DataFrame(columns=PAIR_COLUMNS)
    allp = pd.concat(found, ignore_index=True)
    out = (
        allp.groupby(["cell_id", "destination_id"], sort=True)
        .agg(distance_m=("distance_m", "first"), groups=("group", lambda s: ";".join(sorted(s))))
        .reset_index()
    )
    return out[PAIR_COLUMNS]


def summary(p: pd.DataFrame, origins: gpd.GeoDataFrame) -> dict[str, float | int]:
    """Numbers for the PR and the stage report: pairs, targets, pairs per cell, distances."""
    n = max(len(origins), 1)
    return {
        "origins": len(origins),
        "pairs": len(p),
        "targets": int(p["destination_id"].nunique()) if len(p) else 0,
        "pairs_per_cell": round(len(p) / n, 1),
        "max_distance_m": round(float(p["distance_m"].max()), 0) if len(p) else 0.0,
        "p95_distance_m": round(float(p["distance_m"].quantile(0.95)), 0) if len(p) else 0.0,
    }
