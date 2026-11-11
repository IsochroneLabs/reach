"""recommend: ranked candidate zones for new facilities (methodology §5, arch. §6.4, §7).

1. Candidates: 100 m grid cells inside the urban boundary (`recommend.candidate_spacing_m`),
   without excluded OSM land use (`recommend.exclude_tags`, protected areas of
   `recommend.exclude_protect_classes`; osmium on validate's clipped PBF).
2. Per profile in `recommend.profiles`: candidates within the prefilter reach of a cell with a
   deficit (any category) are routed in groups (§6.5 rule 7): sources = scored cells within the
   prefilter reach of the group, targets = the group's candidates, `costmatrix` as in `count`.
   A candidate Valhalla cannot snap (4xx) is dropped and reported.
3. Greedy per category and profile on `access_counts` (`reach_pipeline.recommend.greedy`).

Outputs (EPSG:25832): `candidates.parquet`, `catchments.parquet` (every routed candidate),
`recommendations.parquet`, `recommendation_catchments.parquet` (catchments of the picks only)
and `report_recommend.json`. Raw values only; classes stay derived at read time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from reach_pipeline import count, landuse
from reach_pipeline import recommend as rec
from reach_pipeline.config import Config, Profile
from reach_pipeline.context import RunContext
from reach_pipeline.errors import BadRequestError
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
from reach_pipeline.stages import count as count_stage
from reach_pipeline.stages import housing, tiles, validate
from reach_pipeline.valhalla.client import ValhallaClient, costing_options

STAGE = "recommend"
# Config sections this stage uses; only they are part of its inputs (see
# manifest.config_input): k per category, profiles and budget, the recommender, Valhalla.
CONFIG_SECTIONS = ("categories", "profiles", "recommend", "time_budgets_min", "valhalla")
PREVIOUS = housing.STAGE
CANDIDATES, CATCHMENTS = "candidates.parquet", "catchments.parquet"
RECOMMENDATIONS, REC_CATCHMENTS = "recommendations.parquet", "recommendation_catchments.parquet"
REPORT = "report_recommend.json"
REC_COLUMNS = [
    "category",
    "profile_id",
    "rank",
    "candidate_id",
    "population_gain",
    "residents_gaining_access",
    "residents_to_sufficient",
    "catchment_residents",
    "catchment_cells",
]

log = logging.getLogger(__name__)


def candidates(ctx: RunContext) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Grid candidates inside the urban boundary minus excluded land use, sorted by id."""
    urban = gpd.read_parquet(ctx.stage_dir(validate.STAGE) / "urban_boundary.parquet")
    grid = rec.candidate_grid(urban.geometry.union_all(), ctx.config.recommend.candidate_spacing_m)
    polygons, stats = landuse.excluded(ctx, STAGE)
    keep = rec.outside(grid.geometry, polygons)
    out = grid[keep].sort_values("candidate_id").reset_index(drop=True)
    return out, {
        "grid_in_urban_boundary": len(grid),
        "excluded_landuse": int((~keep).sum()),
        "excluded_polygons": len(polygons),
        **stats,
    }


def deficit_cells(access: pd.DataFrame, cfg: Config, profile_id: str) -> np.ndarray:
    """Cell ids with a deficit (A < k) in any category for the profile."""
    k = pd.Series({c.id: c.k for c in cfg.categories})
    a = access[access["profile_id"] == profile_id]
    return a.loc[a["count"].to_numpy() < k.reindex(a["category"]).to_numpy(), "cell_id"].unique()


async def _group_matrix(
    client: ValhallaClient, sources: np.ndarray, targets: np.ndarray, profile: Profile
) -> tuple[np.ndarray, list[int]]:
    """Matrix of one group; if Valhalla rejects it (4xx: a location it cannot snap), each target
    is routed alone and the rejected ones are returned (their column stays NaN)."""
    opts = costing_options(profile)
    try:
        return await client.matrix(sources, targets, profile.costing, opts), []
    except BadRequestError:
        times = np.full((len(sources), len(targets)), np.nan)
        rejected = []
        for j in range(len(targets)):
            try:
                times[:, j] = (
                    await client.matrix(sources, targets[j : j + 1], profile.costing, opts)
                )[:, 0]
            except BadRequestError as exc:
                log.warning("candidate %d not routable: %s", j, exc)
                rejected.append(j)
        return times, rejected


async def catchments_profile(
    client: ValhallaClient,
    cells: count.Targets,
    cand_xy: np.ndarray,
    cand_lonlat: np.ndarray,
    profile: Profile,
    budget_min: float,
    group_size_m: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Catchment pairs (`source` = cell index, `target` = candidate index, `time_s`) of the given
    candidates for one profile, plus statistics."""
    reach_m = profile.prefilter_reach_m(budget_min)
    labels = count.make_blocks(cand_xy, group_size_m) if len(cand_xy) else np.empty(0, int)
    groups = [np.flatnonzero(labels == g) for g in range(labels.max() + 1)] if len(labels) else []
    sizes: list[tuple[int, int]] = []
    rejected: list[int] = []

    async def one(tgt: np.ndarray) -> pd.DataFrame:
        src = count.prefilter(cand_xy[tgt], cells, reach_m)
        sizes.append((len(src), len(tgt)))
        times, bad = await _group_matrix(client, cells.lonlat[src], cand_lonlat[tgt], profile)
        rejected.extend(int(tgt[j]) for j in bad)
        pairs = rec.catchment_pairs(times, budget_min * 60)
        return pairs.assign(source=src[pairs["source"]], target=tgt[pairs["target"]])

    before, started = client.requests, time.perf_counter()
    parts = await asyncio.gather(*(one(g) for g in groups))
    pairs = (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame({"source": [], "target": [], "time_s": []})
    )
    stats = {
        "candidates_routed": int(len(cand_xy)),
        "groups": len(groups),
        "requests": client.requests - before,
        "runtime_s": round(time.perf_counter() - started, 2),
        "max_sources": max((s for s, _ in sizes), default=0),
        "pairs": int(sum(s * t for s, t in sizes)),
        "catchment_pairs": int(len(pairs)),
        "reach_m": round(reach_m, 1),
        "not_routable": sorted(rejected),
    }
    return pairs, stats


def select(
    cfg: Config,
    profile_id: str,
    pairs: pd.DataFrame,
    n_candidates: int,
    population: np.ndarray,
    access: pd.DataFrame,
    cell_ids: np.ndarray,
) -> list[dict[str, Any]]:
    """Greedy picks per category for one profile, as `recommendations` rows (candidate index in
    `candidate`)."""
    r = cfg.recommend
    cover = np.zeros((n_candidates, len(cell_ids)), dtype=bool)
    cover[pairs["target"].to_numpy(int), pairs["source"].to_numpy(int)] = True
    a = access[access["profile_id"] == profile_id].set_index(["category", "cell_id"])["count"]
    rows = []
    for cat in cfg.categories:
        counts = a.xs(cat.id).reindex(cell_ids).to_numpy()
        for p in rec.greedy(cover, population, counts, cat.k, r.top_n, r.min_gain):
            rows.append(
                {
                    "category": cat.id,
                    "profile_id": profile_id,
                    "rank": p.rank,
                    "candidate": p.candidate,
                    "population_gain": p.population_gain,
                    "residents_gaining_access": p.residents_gaining_access,
                    "residents_to_sufficient": p.residents_to_sufficient,
                    "catchment_residents": p.catchment_residents,
                    "catchment_cells": p.catchment_cells,
                }
            )
    return rows


async def _recommend_all(
    cfg: Config, cells: gpd.GeoDataFrame, access: pd.DataFrame, cand: gpd.GeoDataFrame
) -> tuple[list[pd.DataFrame], list[dict[str, Any]], dict[str, Any]]:
    cell_ids = cells["cell_id"].to_numpy()
    origin = cells.set_geometry("origin_geom").geometry
    o_xy = np.column_stack([origin.x.to_numpy(), origin.y.to_numpy()])
    targets = count.Targets.build(o_xy, count_stage._lonlat(o_xy))
    population = cells["population"].to_numpy()
    c_xy = np.column_stack([cand.geometry.x.to_numpy(), cand.geometry.y.to_numpy()])
    c_lonlat = count_stage._lonlat(c_xy) if len(c_xy) else np.empty((0, 2))
    budget = cfg.time_budgets_min.facilities
    catchments, rows, stats = [], [], {}
    async with ValhallaClient(cfg.valhalla) as client:
        for pid in cfg.recommend.profiles:
            profile = cfg.profiles[pid]
            needy = np.isin(cell_ids, deficit_cells(access, cfg, pid))
            on_grid = rec.on_spacing(cand["candidate_id"].to_numpy(), cfg.recommend.spacing_m(pid))
            near = rec.near_any(c_xy, o_xy[needy], profile.prefilter_reach_m(budget))
            idx = np.flatnonzero(near & on_grid)
            pairs, stats[pid] = await catchments_profile(
                client,
                targets,
                c_xy[idx],
                c_lonlat[idx],
                profile,
                budget,
                cfg.recommend.group_size_m,
            )
            pairs["target"] = idx[pairs["target"].to_numpy(int)]
            stats[pid]["cells_with_deficit"] = int(needy.sum())
            stats[pid]["not_routable"] = [
                str(cand["candidate_id"].iat[idx[j]]) for j in stats[pid]["not_routable"]
            ]
            log.info("catchments %s: %s", pid, stats[pid])
            started = time.perf_counter()
            picked = select(cfg, pid, pairs, len(cand), population, access, cell_ids)
            stats[pid]["greedy_s"] = round(time.perf_counter() - started, 2)
            stats[pid]["recommendations"] = len(picked)
            rows += picked
            catchments.append(
                pd.DataFrame(
                    {
                        "profile_id": pid,
                        "candidate_id": cand["candidate_id"].to_numpy()[
                            pairs["target"].to_numpy(int)
                        ],
                        "cell_id": cell_ids[pairs["source"].to_numpy(int)],
                        "time_s": pairs["time_s"].astype(np.int16).to_numpy(),
                    }
                )
            )
    return catchments, rows, stats


def recommendation_frames(
    rows: list[dict[str, Any]], cand: gpd.GeoDataFrame, catchments: pd.DataFrame
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """`recommendations` (zone polygon as geometry, centre as `point_geom`) and the catchments of
    the picked candidates (`recommendation_catchments`)."""
    frame = pd.DataFrame(rows, columns=[*REC_COLUMNS[:3], "candidate", *REC_COLUMNS[4:]])
    picked = cand.iloc[frame["candidate"].to_numpy(int)]
    out = gpd.GeoDataFrame(
        frame.drop(columns="candidate").assign(
            candidate_id=picked["candidate_id"].to_numpy(),
            point_geom=gpd.GeoSeries(picked.geometry.values, crs=cand.crs),
        )[[*REC_COLUMNS, "point_geom"]],
        geometry=gpd.GeoSeries(picked["zone_geom"].values, crs=cand.crs),
        crs=cand.crs,
    )
    out = out.astype(
        {
            "rank": np.int32,
            "population_gain": float,
            "residents_gaining_access": np.int32,
            "residents_to_sufficient": np.int32,
            "catchment_residents": np.int32,
            "catchment_cells": np.int32,
        }
    )
    keys = out[["candidate_id", "profile_id"]].drop_duplicates()
    rc = catchments.merge(keys, on=["candidate_id", "profile_id"])
    rc = rc[["candidate_id", "profile_id", "cell_id", "time_s"]]
    return out.reset_index(drop=True), rc.sort_values(["profile_id", "candidate_id", "cell_id"])


def _input_paths(ctx: RunContext) -> list[Path]:
    vdir, cdir = ctx.stage_dir(validate.STAGE), ctx.stage_dir(count_stage.STAGE)
    return [
        tiles.effective_config(ctx),
        vdir / validate.ROUTING_PBF,
        vdir / "cells.parquet",
        vdir / "urban_boundary.parquet",
        cdir / count_stage.ACCESS,
    ]


def run(ctx: RunContext) -> Manifest:
    """Candidates, catchments and greedy recommendations; write outputs + report."""
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    require_ok(ctx.stage_dir(count_stage.STAGE), count_stage.STAGE, ctx.config)
    cfg = ctx.config
    if cfg.recommend.profiles:
        valhalla = count_stage.check_valhalla_config(ctx)
    stage_dir = ctx.stage_dir(STAGE)
    inputs = [config_input(cfg, CONFIG_SECTIONS), *file_inputs(_input_paths(ctx))]
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        log.info("inputs unchanged since %s, nothing to do", previous.finished_at.isoformat())
        return previous

    started_at = datetime.now(UTC)
    with measure() as m:
        vdir = ctx.stage_dir(validate.STAGE)
        cells = gpd.read_parquet(vdir / "cells.parquet")
        access = pd.read_parquet(ctx.stage_dir(count_stage.STAGE) / count_stage.ACCESS)
        stage_dir.mkdir(parents=True, exist_ok=True)
        if cfg.recommend.profiles:
            cand, cand_stats = candidates(ctx)
            catchments, rows, stats = asyncio.run(_recommend_all(cfg, cells, access, cand))
        else:
            log.info("recommend.profiles is empty: no recommendations in this run")
            cand = rec.no_candidates()
            cand_stats, catchments, rows, stats, valhalla = {}, [], [], {}, None
        catchment = (
            pd.concat(catchments, ignore_index=True)
            if catchments
            else pd.DataFrame(
                {
                    "profile_id": pd.Series(dtype=str),
                    "candidate_id": pd.Series(dtype=str),
                    "cell_id": pd.Series(dtype=str),
                    "time_s": pd.Series(dtype=np.int16),
                }
            )
        )
        recs, rec_catch = recommendation_frames(rows, cand, catchment)
        outputs = []
        frames = (
            (CANDIDATES, cand.drop(columns="zone_geom")),
            (CATCHMENTS, catchment),
            (RECOMMENDATIONS, recs),
            (REC_CATCHMENTS, rec_catch),
        )
        for name, frame in frames:
            frame.to_parquet(stage_dir / name, index=False)
            outputs.append(FileOutput(path=str(stage_dir / name), rows=len(frame)))

    report = {
        "run_id": ctx.run_id,
        "stage": STAGE,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "valhalla": valhalla,
        "candidates": {**cand_stats, "kept": len(cand)},
        "profiles": stats,
        "recommendations": pd.DataFrame(recs[REC_COLUMNS]).to_dict("records"),
        "runtime_s": m.runtime_s,
        "peak_rss_mb": m.peak_rss_mb,
    }
    (stage_dir / REPORT).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    outputs.append(FileOutput(path=str(stage_dir / REPORT)))
    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        outputs=outputs,
        message=(
            f"{len(cand)} candidates, {len(recs)} recommendations for profiles "
            f"{list(cfg.recommend.profiles)}; protected areas not excluded: "
            f"{cand_stats.get('protected_area_not_excluded', {})}; "
            f"{sum(s['requests'] for s in stats.values())} matrix requests"
        ),
    )
    write_manifest(manifest, stage_dir)
    return manifest
