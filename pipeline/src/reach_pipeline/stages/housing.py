"""housing: access of unpopulated grid cells, the housing potential (methodology §5b).

Candidates are 100 m Zensus grid cells without residents (not in `cells`), centre inside the
urban boundary + `housing.edge_buffer_m`, outside `recommend.exclude_tags` and
`housing.exclude_tags` land use. For every profile in `housing.profiles` they are counted like
resident cells: the block procedure of `count` (arch. §6.5; matrix from the cell centre to the
facility points, exact prefilter). Transit is not counted.

Outputs (EPSG:25832): `housing_cells.parquet`, `housing_counts.parquet` (columns as
`access_counts`), `housing_reachable.parquet` (as `reachable`, for the flexible score) and
`report_housing.json`. Raw counts and times only.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from datetime import UTC, datetime
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from reach_pipeline import count, housing, landuse
from reach_pipeline.config import Config
from reach_pipeline.context import RunContext
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
from reach_pipeline.stages import score, tiles, validate
from reach_pipeline.valhalla.client import ValhallaClient

STAGE = "housing"
# Config sections this stage uses; only they are part of its inputs (see
# manifest.config_input): categories, profiles and budget, block size, Valhalla, the recommender's
# land-use exclusions and the housing section.
CONFIG_SECTIONS = (
    "categories",
    "count",
    "housing",
    "profiles",
    "recommend",
    "time_budgets_min",
    "valhalla",
)
PREVIOUS = score.STAGE
CELLS, COUNTS = "housing_cells.parquet", "housing_counts.parquet"
REACHABLE = "housing_reachable.parquet"
REPORT = "report_housing.json"

log = logging.getLogger(__name__)


def candidates(ctx: RunContext) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Housing candidates (see module docstring) and statistics."""
    vdir = ctx.stage_dir(validate.STAGE)
    cfg = ctx.config
    urban = gpd.read_parquet(vdir / "urban_boundary.parquet")
    area = urban.geometry.union_all().buffer(cfg.housing.edge_buffer_m)
    polygons, protected = landuse.excluded(ctx, STAGE, cfg.housing.exclude_tags)
    cells = pd.read_parquet(vdir / "cells.parquet", columns=["cell_id"])
    districts = gpd.read_parquet(vdir / "districts.parquet")
    frame, stats = housing.candidate_cells(area, cells["cell_id"].to_numpy(), polygons, districts)
    return frame, {**stats, "excluded_polygons": len(polygons), **protected}


async def count_candidates(
    cfg: Config, data: count_stage.Data
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Counts and reachable facilities of every housing profile (candidates as sources)."""
    labels = count.make_blocks(data.origin_xy, cfg.count.block_size_m)
    categories = [c.id for c in cfg.categories]
    access, reachable, stats = [], [], {}
    async with ValhallaClient(cfg.valhalla) as client:
        for pid in cfg.housing.profiles:
            profile = cfg.profiles[pid]
            reach = dataclasses.replace(
                count_stage.Reach.of(profile, cfg), transit_s=0, transit_m=0
            )
            acc, rch, _, stats[pid] = await count_stage.count_profile(
                client, data, labels, profile, reach
            )
            log.info("housing profile %s: %s", pid, stats[pid])
            access.append(count_stage._complete_access(acc, data.cell_ids, categories, pid))
            reachable.append(count_stage._reachable_rows(rch, data.cell_ids, pid))
    return (
        pd.concat(access, ignore_index=True),
        pd.concat(reachable, ignore_index=True),
        stats,
    )


def _empty_counts() -> tuple[pd.DataFrame, pd.DataFrame]:
    access = pd.DataFrame(
        {
            "cell_id": pd.Series(dtype=object),
            "category": pd.Series(dtype=str),
            "profile_id": pd.Series(dtype=str),
            "count": pd.Series(dtype=np.int32),
            "nearest_min": pd.Series(dtype=float),
        }
    )
    reachable = pd.DataFrame(
        {
            "cell_id": pd.Series(dtype=object),
            "profile_id": pd.Series(dtype=str),
            "facility_id": pd.Series(dtype=str),
            "time_s": pd.Series(dtype=np.int16),
        }
    )
    return access, reachable


def _input_paths(ctx: RunContext) -> list:
    vdir = ctx.stage_dir(validate.STAGE)
    return [
        *([tiles.effective_config(ctx)] if ctx.config.housing.profiles else []),
        vdir / validate.ROUTING_PBF,
        vdir / "cells.parquet",
        vdir / "districts.parquet",
        vdir / "urban_boundary.parquet",
        vdir / "facilities.parquet",
        vdir / "facility_points.parquet",
        vdir / "stops.parquet",
    ]


def run(ctx: RunContext) -> Manifest:
    """Candidates and their counts per housing profile; write outputs + report."""
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    require_ok(ctx.stage_dir(count_stage.STAGE), count_stage.STAGE, ctx.config)
    cfg = ctx.config
    valhalla = count_stage.check_valhalla_config(ctx) if cfg.housing.profiles else None
    stage_dir = ctx.stage_dir(STAGE)
    inputs = [config_input(cfg, CONFIG_SECTIONS), *file_inputs(_input_paths(ctx))]
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        log.info("inputs unchanged since %s, nothing to do", previous.finished_at.isoformat())
        return previous

    started_at = datetime.now(UTC)
    with measure() as m:
        stage_dir.mkdir(parents=True, exist_ok=True)
        if cfg.housing.profiles:
            cells, cell_stats = candidates(ctx)
            data, _ = count_stage.load_data(
                ctx.stage_dir(validate.STAGE),
                pd.DataFrame({"stop_id": pd.Series(dtype=object), "departures": []}),
            )
            origin = cells.set_geometry("origin_geom").geometry
            xy = count_stage._xy(origin)
            data = dataclasses.replace(
                data,
                cell_ids=cells["cell_id"].to_numpy(),
                origin_xy=xy,
                origin_lonlat=count_stage._lonlat(xy) if len(xy) else np.empty((0, 2)),
            )
            if len(cells):
                access, reachable, stats = asyncio.run(count_candidates(cfg, data))
            else:
                access, reachable = _empty_counts()
                stats = {}
        else:
            log.info("housing.profiles is empty: no housing potential in this run")
            cells, cell_stats, stats = housing.no_cells(), {}, {}
            access, reachable = _empty_counts()
        outputs = []
        for name, frame in ((CELLS, cells), (COUNTS, access), (REACHABLE, reachable)):
            frame.to_parquet(stage_dir / name, index=False)
            outputs.append(FileOutput(path=str(stage_dir / name), rows=len(frame)))

    report = {
        "run_id": ctx.run_id,
        "stage": STAGE,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "valhalla": valhalla,
        "candidates": cell_stats,
        "profiles": stats,
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
            f"{len(cells)} housing candidates for profiles {list(cfg.housing.profiles)}, "
            f"{len(access)} counts, {len(reachable)} reachable pairs; "
            f"{sum(s['requests'] for s in stats.values())} matrix requests"
        ),
    )
    write_manifest(manifest, stage_dir)
    return manifest
