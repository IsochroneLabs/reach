"""Shared helpers of the validation experiments: inputs of a run, class comparison, recounts.

Experiments read the files of a finished run (`data/runs/<run_id>/…`) and write only below
`<data_dir>/<results_dir>/<run_id>/vNN/`; they never change a run or the database.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from reach_pipeline import count, scoring
from reach_pipeline.config import Config, Profile
from reach_pipeline.context import RunContext
from reach_pipeline.experiments.settings import Settings
from reach_pipeline.stages import count as count_stage
from reach_pipeline.stages import recommend, validate
from reach_pipeline.valhalla.client import ValhallaClient

log = logging.getLogger(__name__)

CLASSES = ("lack", "insufficient", "sufficient")


@dataclass
class Experiment:
    """Context of one experiment: run, settings and its output folder."""

    ctx: RunContext
    settings: Settings
    name: str  # e.g. "v05"
    notes: list[str] = field(default_factory=list)

    @property
    def cfg(self) -> Config:
        return self.ctx.config

    @property
    def out(self) -> Path:
        path = self.cfg.data_dir / self.settings.results_dir / self.ctx.run_id / self.name
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def reference_dir(self) -> Path:
        path = self.cfg.data_dir / self.settings.reference_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def rng(self, offset: int = 0) -> np.random.Generator:
        return np.random.default_rng(self.settings.seed + offset)

    def k(self) -> pd.Series:
        return pd.Series({c.id: c.k for c in self.cfg.categories})

    # Run inputs, read once per experiment.
    @cached_property
    def cells(self) -> gpd.GeoDataFrame:
        return gpd.read_parquet(self.ctx.stage_dir(validate.STAGE) / "cells.parquet")

    @cached_property
    def districts(self) -> gpd.GeoDataFrame:
        return gpd.read_parquet(self.ctx.stage_dir(validate.STAGE) / "districts.parquet")

    @cached_property
    def facilities(self) -> gpd.GeoDataFrame:
        return gpd.read_parquet(self.ctx.stage_dir(validate.STAGE) / "facilities.parquet")

    @cached_property
    def facility_points(self) -> gpd.GeoDataFrame:
        return gpd.read_parquet(self.ctx.stage_dir(validate.STAGE) / "facility_points.parquet")

    @cached_property
    def urban_boundary(self) -> gpd.GeoDataFrame:
        return gpd.read_parquet(self.ctx.stage_dir(validate.STAGE) / "urban_boundary.parquet")

    @cached_property
    def access(self) -> pd.DataFrame:
        return pd.read_parquet(self.ctx.stage_dir(count_stage.STAGE) / count_stage.ACCESS)

    @cached_property
    def reachable(self) -> pd.DataFrame:
        return pd.read_parquet(self.ctx.stage_dir(count_stage.STAGE) / count_stage.REACHABLE)

    @cached_property
    def candidates(self) -> gpd.GeoDataFrame:
        return gpd.read_parquet(self.ctx.stage_dir(recommend.STAGE) / recommend.CANDIDATES)

    @cached_property
    def catchments(self) -> pd.DataFrame:
        return pd.read_parquet(self.ctx.stage_dir(recommend.STAGE) / recommend.CATCHMENTS)

    @cached_property
    def recommendations(self) -> pd.DataFrame:
        return pd.read_parquet(
            self.ctx.stage_dir(recommend.STAGE) / recommend.RECOMMENDATIONS,
            columns=recommend.REC_COLUMNS,
        )

    def write_json(self, name: str, data: Any) -> Path:
        path = self.out / name
        path.write_text(json.dumps(data, indent=2, default=_json_default) + "\n", encoding="utf-8")
        return path

    def write_table(self, name: str, frame: pd.DataFrame) -> Path:
        path = self.out / name
        frame.to_csv(path, index=False)
        return path


def _json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def xy(geoms: gpd.GeoSeries) -> np.ndarray:
    return np.column_stack([geoms.x.to_numpy(), geoms.y.to_numpy()])


def classes(access: pd.DataFrame, k: pd.Series) -> np.ndarray:
    """Class of every `access` row (`count`, `category`) for the k per category."""
    return scoring.classify(access["count"].to_numpy(), k.reindex(access["category"]).to_numpy())


def with_population(access: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    return access.merge(cells[["cell_id", "population", "district_id"]], on="cell_id")


def class_summary(access: pd.DataFrame, cells: pd.DataFrame, k: pd.Series) -> pd.DataFrame:
    """Per profile × category: residents per class and the deficit sum."""
    a = with_population(access, cells)
    kk = k.reindex(a["category"]).to_numpy()
    a = a.assign(
        cls=scoring.classify(a["count"].to_numpy(), kk),
        deficit=scoring.deficit(a["population"].to_numpy(), a["count"].to_numpy(), kk),
    )
    res = a.pivot_table(
        index=["profile_id", "category"], columns="cls", values="population", aggfunc="sum"
    ).reindex(columns=list(CLASSES), fill_value=0)
    res = res.fillna(0).astype(int).add_prefix("residents_")
    total = res.sum(axis=1)
    res["share_lack"] = (res["residents_lack"] / total).round(4)
    res["deficit_sum"] = a.groupby(["profile_id", "category"])["deficit"].sum().round(1)
    return res.reset_index()


def compare(
    base: pd.DataFrame, alt: pd.DataFrame, cells: pd.DataFrame, k_base: pd.Series, k_alt=None
) -> pd.DataFrame:
    """Per profile × category: how many cells and residents change class from `base` to `alt`
    (both `access_counts`-shaped), and the change in lack share and deficit sum."""
    k_alt = k_base if k_alt is None else k_alt
    keys = ["cell_id", "category", "profile_id"]
    m = base[[*keys, "count"]].merge(
        alt[[*keys, "count"]], on=keys, suffixes=("_base", "_alt"), validate="one_to_one"
    )
    m = with_population(m, cells)
    c_base = scoring.classify(m["count_base"].to_numpy(), k_base.reindex(m["category"]).to_numpy())
    c_alt = scoring.classify(m["count_alt"].to_numpy(), k_alt.reindex(m["category"]).to_numpy())
    m = m.assign(
        changed=c_base != c_alt,
        to_worse=_rank(c_alt) < _rank(c_base),
        count_diff=m["count_alt"] - m["count_base"],
    )
    pop = m["population"]
    g = m.assign(res_changed=pop * m["changed"], res_worse=pop * m["to_worse"]).groupby(
        ["profile_id", "category"]
    )
    out = pd.DataFrame(
        {
            "cells": g.size(),
            "cells_changed": g["changed"].sum(),
            "residents": g["population"].sum(),
            "residents_changed": g["res_changed"].sum(),
            "residents_worse": g["res_worse"].sum(),
            "count_diff_mean": g["count_diff"].mean().round(3),
        }
    )
    out["share_residents_changed"] = (out["residents_changed"] / out["residents"]).round(4)
    s_base = class_summary(base, cells, k_base).set_index(["profile_id", "category"])
    s_alt = class_summary(alt, cells, k_alt).set_index(["profile_id", "category"])
    out["share_lack_base"] = s_base["share_lack"]
    out["share_lack_alt"] = s_alt["share_lack"]
    out["deficit_base"] = s_base["deficit_sum"]
    out["deficit_alt"] = s_alt["deficit_sum"]
    return out.reset_index()


def _rank(cls: np.ndarray) -> np.ndarray:
    return np.select([cls == "lack", cls == "insufficient"], [0, 1], 2)


def district_deficits(access: pd.DataFrame, cells: pd.DataFrame, k: pd.Series) -> pd.DataFrame:
    """Deficit sum and share of residents in lack per district × profile × category."""
    a = with_population(access, cells).dropna(subset=["district_id"])
    kk = k.reindex(a["category"]).to_numpy()
    a = a.assign(
        deficit=scoring.deficit(a["population"].to_numpy(), a["count"].to_numpy(), kk),
        lack_pop=a["population"] * (a["count"].to_numpy() == 0),
    )
    g = a.groupby(["profile_id", "category", "district_id"])
    out = pd.DataFrame(
        {
            "deficit_sum": g["deficit"].sum(),
            "share_lack": g["lack_pop"].sum() / g["population"].sum(),
        }
    )
    return out.reset_index()


def spearman(a: pd.Series, b: pd.Series) -> float:
    """Spearman rank correlation of two aligned series (ranks, then Pearson; no SciPy)."""
    joined = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(joined) < 3 or joined.iloc[:, 0].nunique() < 2 or joined.iloc[:, 1].nunique() < 2:
        return float("nan")
    r = joined.rank()
    return round(float(r.iloc[:, 0].corr(r.iloc[:, 1])), 4)


def ranking_agreement(
    base: pd.DataFrame, alt: pd.DataFrame, top: int, value: str = "deficit_sum"
) -> pd.DataFrame:
    """Per profile × category: Spearman of the district ranking by `value` and the overlap of
    the `top` districts (district_deficits frames)."""
    rows = []
    for (pid, cat), b in base.groupby(["profile_id", "category"]):
        a = alt[(alt["profile_id"] == pid) & (alt["category"] == cat)]
        if a.empty:
            continue
        bs, as_ = b.set_index("district_id")[value], a.set_index("district_id")[value]
        top_b = set(bs.sort_values(ascending=False).index[:top])
        top_a = set(as_.sort_values(ascending=False).index[:top])
        rows.append(
            {
                "profile_id": pid,
                "category": cat,
                "spearman": spearman(bs, as_),
                f"top{top}_overlap": len(top_b & top_a),
            }
        )
    return pd.DataFrame(rows)


def counts_within(
    reachable: pd.DataFrame,
    facilities: pd.DataFrame,
    cell_ids: np.ndarray,
    categories: list[str],
    profile_id: str,
    budget_s: float,
) -> pd.DataFrame:
    """`access_counts`-shaped counts of one profile from `reachable` with a smaller budget."""
    r = reachable[(reachable["profile_id"] == profile_id) & (reachable["time_s"] <= budget_s)]
    r = r.merge(facilities[["facility_id", "category"]], on="facility_id")
    c = r.groupby(["cell_id", "category"]).size().rename("count")
    full = pd.MultiIndex.from_product([cell_ids, categories], names=["cell_id", "category"])
    out = c.reindex(full, fill_value=0).reset_index()
    out.insert(2, "profile_id", profile_id)
    return out


def load_count_data(ctx: RunContext) -> count_stage.Data:
    """Arrays `count` uses: cells, facility points and stops with the run's departures (the
    stops stay in the matrix, because costmatrix results depend on the whole target set)."""
    stops = pd.read_parquet(ctx.stage_dir(count_stage.STAGE) / count_stage.STOPS)
    departures = stops[["stop_id", "weekday_departures"]].rename(
        columns={"weekday_departures": "departures"}
    )
    data, _ = count_stage.load_data(ctx.stage_dir(validate.STAGE), departures)
    return data


def facility_reach(profile: Profile, cfg: Config, budget_min: float) -> count_stage.Reach:
    """`count`'s budgets and prefilter reaches with another facility budget."""
    r = count_stage.Reach.of(profile, cfg)
    return count_stage.Reach(
        facility_s=budget_min * 60,
        facility_m=profile.prefilter_reach_m(budget_min),
        transit_s=r.transit_s,
        transit_m=r.transit_m,
    )


async def recount(
    cfg: Config,
    data: count_stage.Data,
    profile_ids: list[str],
    budget_min: float,
    url: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Counts and reachable pairs of the given profiles, exactly as `count` computes them (same
    blocks, prefilter and matrix), with another budget, origins or Valhalla (`url`)."""
    labels = count.make_blocks(data.origin_xy, cfg.count.block_size_m)
    categories = [c.id for c in cfg.categories]
    access, reach, stats = [], [], {}
    async with ValhallaClient(cfg.valhalla, url=url) as client:
        for pid in profile_ids:
            profile = cfg.profiles[pid]
            acc, rch, _, stats[pid] = await count_stage.count_profile(
                client, data, labels, profile, facility_reach(profile, cfg, budget_min)
            )
            log.info("recount %s (%s min): %s", pid, budget_min, stats[pid])
            access.append(count_stage._complete_access(acc, data.cell_ids, categories, pid))
            reach.append(count_stage._reachable_rows(rch, data.cell_ids, pid))
    return pd.concat(access, ignore_index=True), pd.concat(reach, ignore_index=True), stats


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """JSON-friendly rows (NaN → None)."""
    return json.loads(frame.to_json(orient="records"))
