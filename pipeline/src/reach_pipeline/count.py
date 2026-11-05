"""Network counting with the Valhalla matrix (arch. §6.3, §6.5; methodology §1–§3).

Cells are grouped into square blocks; per block and profile one matrix (split only above
`valhalla.max_matrix_pairs`) has the block's cell origins as sources and, as targets, every
facility routing point within the facility prefilter reach plus, for transit profiles, every stop
within the transit prefilter reach of the block. Counts are split by category afterwards; a
facility with several routing points counts once with its minimum time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shapely


@dataclass(frozen=True)
class Targets:
    """Routing targets of one kind (facility points or stops) with a spatial index."""

    xy: np.ndarray  # (n, 2) EPSG:25832
    lonlat: np.ndarray  # (n, 2) EPSG:4326
    tree: shapely.STRtree

    @classmethod
    def build(cls, xy: np.ndarray, lonlat: np.ndarray) -> Targets:
        return cls(xy=xy, lonlat=lonlat, tree=shapely.STRtree(shapely.points(xy)))


def make_blocks(xy: np.ndarray, size_m: float) -> np.ndarray:
    """Block label (0..n_blocks-1) per origin: square grid cells of `size_m` in EPSG:25832."""
    keys = np.floor(xy / size_m).astype(np.int64)
    _, labels = np.unique(keys, axis=0, return_inverse=True)
    return labels.reshape(-1)


def prefilter(block_xy: np.ndarray, targets: Targets, reach_m: float) -> np.ndarray:
    """Indices of targets within `reach_m` (straight line) of the block's origin bounding box.

    A superset of the targets within reach of any single origin, so no target a cell can reach
    within the budget is dropped (O20).
    """
    if reach_m <= 0 or len(targets.xy) == 0:
        return np.empty(0, dtype=np.int64)
    (x0, y0), (x1, y1) = block_xy.min(axis=0), block_xy.max(axis=0)
    box = shapely.box(x0, y0, x1, y1)
    return np.sort(targets.tree.query(box, predicate="dwithin", distance=reach_m))


def count_block(times: np.ndarray, links: pd.DataFrame, budget_s: float) -> pd.DataFrame:
    """Counts and nearest times per source and category from one matrix block.

    `times` has shape (sources, targets) in seconds (NaN = unreachable); `links` maps the target
    columns to facilities: columns `target` (column index), `facility_id`, `category` (one row
    per point and category). Returns `source`, `category`, `count` (facilities with minimum time
    ≤ budget) and `nearest_s` (minimum time if ≤ budget, else NaN: beyond the budget the prefilter
    does not guarantee that the nearest facility was among the targets).
    """
    n_src = times.shape[0]
    cols = ["source", "category", "count", "nearest_s"]
    if n_src == 0 or links.empty:
        return pd.DataFrame(columns=cols)
    t = times[:, links["target"].to_numpy()]  # (sources, links)
    long = pd.DataFrame(
        {
            "source": np.repeat(np.arange(n_src), len(links)),
            "category": np.tile(links["category"].to_numpy(), n_src),
            "facility_id": np.tile(links["facility_id"].to_numpy(), n_src),
            "time": t.reshape(-1),
        }
    )
    per_facility = long.groupby(["source", "category", "facility_id"], sort=False)["time"].min()
    within = per_facility.where(per_facility <= budget_s).rename("within").reset_index()
    out = within.groupby(["source", "category"], sort=False)["within"].agg(["count", "min"])
    return out.rename(columns={"min": "nearest_s"}).reset_index()[cols]


def reachable_block(times: np.ndarray, links: pd.DataFrame, budget_s: float) -> pd.DataFrame:
    """Facilities reachable within the budget per source, with their minimum time.

    Same inputs as `count_block`; one row per source and facility (a facility in several
    categories or with several routing points appears once). Columns `source`, `facility_id`,
    `time_s` (whole seconds, int16: the budget is far below 32,767 s). Joined with `facilities`
    by `facility_id`, these rows give exactly the counts of `count_block`.
    """
    cols = ["source", "facility_id", "time_s"]
    if times.shape[0] == 0 or links.empty:
        return pd.DataFrame(columns=cols)
    pts = links.drop_duplicates(["target", "facility_id"])
    t = times[:, pts["target"].to_numpy()]
    long = pd.DataFrame(
        {
            "source": np.repeat(np.arange(times.shape[0]), len(pts)),
            "facility_id": np.tile(pts["facility_id"].to_numpy(), times.shape[0]),
            "time": t.reshape(-1),
        }
    )
    long = long[long["time"] <= budget_s]  # NaN (unreachable) compares False
    out = long.groupby(["source", "facility_id"], sort=False)["time"].min().reset_index()
    return pd.DataFrame(
        {
            "source": out["source"].to_numpy(),
            "facility_id": out["facility_id"].to_numpy(),
            "time_s": np.rint(out["time"].to_numpy()).astype(np.int16),
        }
    )


def transit_block(times: np.ndarray, departures: np.ndarray, budget_s: float) -> pd.DataFrame:
    """Transit supply per source from the stop columns of one block (methodology §3).

    Returns `source`, `departures` (sum over stops reachable within the budget), `stops_count`
    and `nearest_stop_s` (NaN if no stop is reachable within the budget).
    """
    reachable = times <= budget_s  # NaN compares False
    nearest = np.where(reachable, times, np.inf).min(axis=1, initial=np.inf)
    return pd.DataFrame(
        {
            "source": np.arange(times.shape[0]),
            "departures": (reachable * departures[np.newaxis, :]).sum(axis=1).astype(np.int64),
            "stops_count": reachable.sum(axis=1).astype(np.int64),
            "nearest_stop_s": np.where(np.isinf(nearest), np.nan, nearest),
        }
    )


def evidence_pairs(times: np.ndarray, src_xy: np.ndarray, tgt_xy: np.ndarray) -> pd.DataFrame:
    """All measured pairs of an evidence block: `source`, `target`, `distance_m` (straight
    line), `time_s` (NaN = unreachable)."""
    d = np.linalg.norm(src_xy[:, np.newaxis, :] - tgt_xy[np.newaxis, :, :], axis=2)
    n_src, n_tgt = times.shape
    return pd.DataFrame(
        {
            "source": np.repeat(np.arange(n_src), n_tgt),
            "target": np.tile(np.arange(n_tgt), n_src),
            "distance_m": d.reshape(-1),
            "time_s": times.reshape(-1),
        }
    )


def summarise_evidence(
    pairs: pd.DataFrame,
    speed_kmh: float,
    budget_s: float,
    prefilter_reach_m: float,
    band_edges: list[float],
) -> dict[str, Any]:
    """Prefilter evidence of one profile and budget (O20).

    `nominal_reach_m` = speed × budget; `max_reachable_distance_m` = largest straight-line
    distance of a pair reachable within the budget; `required_factor` = that distance ÷ nominal
    reach (the speed factor that would have kept every measured pair); `max_speed_ratio_by_band`
    = highest implied speed (straight line ÷ time) ÷ profile speed for pairs whose time lies in
    each band, bands given as fractions of the budget (short pairs are dominated by the snap
    distance, which Valhalla does not count as time; the band ending at the budget is the one
    that matters for the prefilter); `beyond_nominal` / `beyond_prefilter` = reachable pairs
    farther than the nominal / configured prefilter reach (the latter would be dropped).
    """
    nominal = speed_kmh / 3.6 * budget_s
    reachable = pairs[pairs["time_s"] <= budget_s]
    max_dist = float(reachable["distance_m"].max()) if len(reachable) else None
    by_band: dict[str, float | None] = {}
    for lo, hi in zip(band_edges, band_edges[1:], strict=False):
        band = pairs[(pairs["time_s"] >= lo * budget_s) & (pairs["time_s"] <= hi * budget_s)]
        ratio = (band["distance_m"] / band["time_s"] * 3.6 / speed_kmh).max()
        by_band[f"{lo:.2f}-{hi:.2f}"] = None if band.empty else round(float(ratio), 3)
    return {
        "pairs": int(len(pairs)),
        "reachable_pairs": int(len(reachable)),
        "nominal_reach_m": round(nominal, 1),
        "prefilter_reach_m": round(prefilter_reach_m, 1),
        "max_reachable_distance_m": None if max_dist is None else round(max_dist, 1),
        "required_factor": None if max_dist is None else round(max_dist / nominal, 3),
        "max_speed_ratio_by_band": by_band,
        "beyond_nominal": int((reachable["distance_m"] > nominal).sum()),
        "beyond_prefilter": int((reachable["distance_m"] > prefilter_reach_m).sum()),
    }
