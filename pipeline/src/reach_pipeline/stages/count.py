"""count: reachable facilities per cell × category × profile and transit supply (arch. §6.3).

Per profile, cells are grouped into blocks and every block sends one matrix to Valhalla (cell
origins → facility routing points within the facility prefilter reach, plus stops within the
transit prefilter reach for transit profiles). Outputs, all EPSG:25832 / plain Parquet:

- `access_counts.parquet`: `cell_id`, `category`, `profile_id`, `count`, `nearest_min`
- `transit_supply.parquet`: `cell_id`, `profile_id`, `departures`, `stops_count`,
  `nearest_stop_min` (profiles with `transit: true`)
- `stops.parquet`: validate's stops plus `weekday_departures` on the reference weekday
- `report_count.json`: per-profile statistics and the prefilter evidence (O20)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer

from reach_pipeline import count, gtfs, transit
from reach_pipeline.config import Config, Profile
from reach_pipeline.context import RunContext
from reach_pipeline.errors import StageValidationError
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
from reach_pipeline.stages import tiles, validate
from reach_pipeline.valhalla.client import ValhallaClient, costing_options

STAGE = "count"
# Config sections this stage uses; only they are part of its inputs (see
# manifest.config_input): targets, blocks, profiles, budgets and the Valhalla client.
CONFIG_SECTIONS = ("categories", "count", "profiles", "time_budgets_min", "valhalla")
PREVIOUS = tiles.STAGE
ACCESS, TRANSIT, STOPS = "access_counts.parquet", "transit_supply.parquet", "stops.parquet"
REPORT = "report_count.json"
LAYERS = ["cells", "facilities", "facility_points", "stops"]
GTFS_FILES = ["stop_times.txt", "trips.txt", "calendar.txt", "calendar_dates.txt"]

log = logging.getLogger(__name__)
_to_lonlat = Transformer.from_crs(validate.METRIC_CRS, "EPSG:4326", always_xy=True)


def _lonlat(xy: np.ndarray) -> np.ndarray:
    lon, lat = _to_lonlat.transform(xy[:, 0], xy[:, 1])
    return np.column_stack([lon, lat])


def _xy(geoms: gpd.GeoSeries) -> np.ndarray:
    return np.column_stack([geoms.x.to_numpy(), geoms.y.to_numpy()])


@dataclass
class Data:
    """Everything the matrix blocks need, as arrays."""

    cell_ids: np.ndarray
    origin_xy: np.ndarray
    origin_lonlat: np.ndarray
    points: count.Targets
    links: pd.DataFrame  # target (point index), facility_id, category
    point_facility: np.ndarray  # facility_id per point
    stops: count.Targets
    stop_ids: np.ndarray
    departures: np.ndarray


def load_data(vdir: Path, departures: pd.DataFrame) -> tuple[Data, gpd.GeoDataFrame]:
    """Read validate's layers; returns the arrays and the stops with `weekday_departures`."""
    cells = gpd.read_parquet(vdir / "cells.parquet")
    fac = pd.read_parquet(vdir / "facilities.parquet", columns=["facility_id", "category"])
    points = gpd.read_parquet(vdir / "facility_points.parquet")
    stops = gpd.read_parquet(vdir / "stops.parquet")
    stops = stops.merge(departures, on="stop_id", how="left")
    stops.insert(2, "weekday_departures", stops.pop("departures").fillna(0).astype(np.int64))
    points = points.reset_index(drop=True)
    links = (
        points[["facility_id"]]
        .assign(target=np.arange(len(points)))
        .merge(fac, on="facility_id", how="inner")[["target", "facility_id", "category"]]
    )
    origin_xy = _xy(cells["origin_geom"])
    point_xy, stop_xy = _xy(points.geometry), _xy(stops.geometry)
    data = Data(
        cell_ids=cells["cell_id"].to_numpy(),
        origin_xy=origin_xy,
        origin_lonlat=_lonlat(origin_xy),
        points=count.Targets.build(point_xy, _lonlat(point_xy)),
        links=links,
        point_facility=points["facility_id"].to_numpy(),
        stops=count.Targets.build(stop_xy, _lonlat(stop_xy)),
        stop_ids=stops["stop_id"].to_numpy(),
        departures=stops["weekday_departures"].to_numpy(),
    )
    return data, stops


@dataclass(frozen=True)
class Reach:
    """Budgets (seconds) and prefilter reaches (metres) of one profile."""

    facility_s: float
    facility_m: float
    transit_s: float
    transit_m: float  # 0 = no transit for this profile

    @classmethod
    def of(cls, profile: Profile, cfg: Config) -> Reach:
        b = cfg.time_budgets_min
        return cls(
            facility_s=b.facilities * 60,
            facility_m=profile.prefilter_reach_m(b.facilities),
            transit_s=b.transit * 60,
            transit_m=profile.prefilter_reach_m(b.transit) if profile.transit else 0.0,
        )


def _block_links(links: pd.DataFrame, chosen: np.ndarray, n_points: int) -> pd.DataFrame:
    """Rows of `links` whose point is among `chosen`, with `target` = column in the block."""
    column = np.full(n_points, -1)
    column[chosen] = np.arange(len(chosen))
    mapped = column[links["target"].to_numpy()]
    keep = mapped >= 0
    return links[keep].assign(target=mapped[keep])


async def _block(
    client: ValhallaClient,
    data: Data,
    src: np.ndarray,
    f_idx: np.ndarray,
    s_idx: np.ndarray,
    profile: Profile,
) -> np.ndarray:
    targets = np.vstack([data.points.lonlat[f_idx], data.stops.lonlat[s_idx]])
    return await client.matrix(
        data.origin_lonlat[src], targets, profile.costing, costing_options(profile)
    )


async def count_profile(
    client: ValhallaClient, data: Data, labels: np.ndarray, profile: Profile, reach: Reach
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Counts (`source` = cell index) and transit supply of one profile, plus statistics."""
    n_points = len(data.points.xy)
    blocks = [np.flatnonzero(labels == b) for b in range(labels.max() + 1)]
    sizes: list[tuple[int, int]] = []

    async def one(src: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame]:
        f_idx = count.prefilter(data.origin_xy[src], data.points, reach.facility_m)
        s_idx = count.prefilter(data.origin_xy[src], data.stops, reach.transit_m)
        sizes.append((len(src), len(f_idx) + len(s_idx)))
        times = await _block(client, data, src, f_idx, s_idx, profile)
        ft, st = times[:, : len(f_idx)], times[:, len(f_idx) :]
        acc = count.count_block(ft, _block_links(data.links, f_idx, n_points), reach.facility_s)
        acc["source"] = src[acc["source"].to_numpy(dtype=np.int64)]
        tr = count.transit_block(st, data.departures[s_idx], reach.transit_s)
        tr["source"] = src[tr["source"].to_numpy()]
        return acc, tr

    before = client.requests
    started = time.perf_counter()
    parts = await asyncio.gather(*(one(src) for src in blocks))
    targets = np.array([t for _, t in sizes])
    stats = {
        "blocks": len(blocks),
        "requests": client.requests - before,
        "runtime_s": round(time.perf_counter() - started, 2),
        "max_sources": max(s for s, _ in sizes),
        "targets_max": int(targets.max()),
        "targets_median": float(np.median(targets)),
        "pairs": int(sum(s * t for s, t in sizes)),
        "facility_reach_m": round(reach.facility_m, 1),
        "transit_reach_m": round(reach.transit_m, 1),
    }
    return (
        pd.concat([p[0] for p in parts], ignore_index=True),
        pd.concat([p[1] for p in parts], ignore_index=True),
        stats,
    )


def _complete_access(
    acc: pd.DataFrame, cell_ids: np.ndarray, categories: list[str], profile_id: str
) -> pd.DataFrame:
    """One row per cell × category (count 0, nearest null where nothing was within reach)."""
    full = pd.MultiIndex.from_product(
        [np.arange(len(cell_ids)), categories], names=["source", "category"]
    )
    acc = acc.set_index(["source", "category"]).reindex(full).reset_index()
    return pd.DataFrame(
        {
            "cell_id": cell_ids[acc["source"].to_numpy()],
            "category": acc["category"].astype(str),
            "profile_id": profile_id,
            "count": acc["count"].fillna(0).astype(np.int32),
            "nearest_min": (acc["nearest_s"] / 60).round(2),
        }
    )


def _transit_rows(tr: pd.DataFrame, cell_ids: np.ndarray, profile_id: str) -> pd.DataFrame:
    tr = tr.sort_values("source")
    return pd.DataFrame(
        {
            "cell_id": cell_ids[tr["source"].to_numpy()],
            "profile_id": profile_id,
            "departures": tr["departures"].astype(np.int32),
            "stops_count": tr["stops_count"].astype(np.int32),
            "nearest_stop_min": (tr["nearest_stop_s"] / 60).round(2),
        }
    )


def evidence_blocks(data: Data, labels: np.ndarray, points: dict[str, tuple]) -> dict[str, int]:
    """Block label of the cell nearest to each sample point (duplicates removed)."""
    out: dict[str, int] = {}
    xy = data.origin_xy
    to_metric = Transformer.from_crs("EPSG:4326", validate.METRIC_CRS, always_xy=True)
    for name, (lon, lat) in points.items():
        px, py = to_metric.transform(lon, lat)
        nearest = int(np.argmin(np.hypot(xy[:, 0] - px, xy[:, 1] - py)))
        if labels[nearest] not in out.values():
            out[name] = int(labels[nearest])
    return out


async def evidence_profile(
    client: ValhallaClient,
    data: Data,
    labels: np.ndarray,
    blocks: dict[str, int],
    profile: Profile,
    reach: Reach,
    cfg: Config,
) -> dict[str, Any]:
    """Widened matrices for the sample blocks; summary per target kind (O20)."""
    ev = cfg.count.evidence
    facility_pairs, stop_pairs, beyond = [], [], []
    for name, label in blocks.items():
        src = np.flatnonzero(labels == label)
        f_idx = count.prefilter(
            data.origin_xy[src], data.points, reach.facility_m * ev.widen_factor + ev.widen_m
        )
        s_idx = count.prefilter(
            data.origin_xy[src],
            data.stops,
            reach.transit_m * ev.widen_factor + ev.widen_m if reach.transit_m else 0.0,
        )
        times = await _block(client, data, src, f_idx, s_idx, profile)
        src_xy, n_f = data.origin_xy[src], len(f_idx)
        fp = count.evidence_pairs(times[:, :n_f], src_xy, data.points.xy[f_idx])
        sp = count.evidence_pairs(times[:, n_f:], src_xy, data.stops.xy[s_idx])
        facility_pairs.append(fp)
        stop_pairs.append(sp)
        far = fp[(fp["time_s"] <= reach.facility_s) & (fp["distance_m"] > reach.facility_m)]
        for row in far.itertuples():
            beyond.append(
                {
                    "block": name,
                    "cell_id": str(data.cell_ids[src[row.source]]),
                    "facility_id": str(data.point_facility[f_idx[row.target]]),
                    "distance_m": round(row.distance_m, 1),
                    "time_s": round(row.time_s, 1),
                }
            )
    out: dict[str, Any] = {
        "facilities": count.summarise_evidence(
            pd.concat(facility_pairs),
            profile.speed_kmh,
            reach.facility_s,
            reach.facility_m,
            ev.band_edges,
        ),
        "beyond_prefilter_examples": beyond[:20],
    }
    if reach.transit_m:
        out["stops"] = count.summarise_evidence(
            pd.concat(stop_pairs),
            profile.speed_kmh,
            reach.transit_s,
            reach.transit_m,
            ev.band_edges,
        )
    return out


async def _count_all(
    cfg: Config, data: Data
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    labels = count.make_blocks(data.origin_xy, cfg.count.block_size_m)
    categories = [c.id for c in cfg.categories]
    sample = evidence_blocks(data, labels, cfg.count.evidence.sample_points)
    access, supply, stats, evidence = [], [], {}, {"sample_blocks": sample, "profiles": {}}
    async with ValhallaClient(cfg.valhalla) as client:
        for pid, profile in cfg.profiles.items():
            reach = Reach.of(profile, cfg)
            acc, tr, stats[pid] = await count_profile(client, data, labels, profile, reach)
            log.info("profile %s: %s", pid, stats[pid])
            access.append(_complete_access(acc, data.cell_ids, categories, pid))
            if profile.transit:
                supply.append(_transit_rows(tr, data.cell_ids, pid))
            evidence["profiles"][pid] = await evidence_profile(
                client, data, labels, sample, profile, reach, cfg
            )
            log.info("prefilter evidence %s: %s", pid, evidence["profiles"][pid]["facilities"])
    transit_cols = ["cell_id", "profile_id", "departures", "stops_count", "nearest_stop_min"]
    return (
        pd.concat(access, ignore_index=True),
        pd.concat(supply, ignore_index=True) if supply else pd.DataFrame(columns=transit_cols),
        stats,
        evidence,
    )


def reference_day(vdir: Path) -> date:
    """Reference weekday chosen by validate (report part 1)."""
    report = json.loads((vdir / validate.REPORT_JSON).read_text(encoding="utf-8"))
    day = report["summary"].get("reference_weekday")
    if not day:
        raise StageValidationError("validate report has no reference weekday")
    return date.fromisoformat(day)


def _input_paths(ctx: RunContext) -> list[Path]:
    vdir = ctx.stage_dir(validate.STAGE)
    gtfs_dir = ctx.raw_dir / "gtfs"
    gtfs_files = [gtfs_dir / f for f in GTFS_FILES if (gtfs_dir / f).exists()]
    return [
        tiles.valhalla_config(ctx),
        vdir / validate.ROUTING_PBF,
        *(vdir / f"{name}.parquet" for name in LAYERS),
        vdir / validate.REPORT_JSON,
        *gtfs_files,
    ]


def run(ctx: RunContext) -> Manifest:
    """Count every cell × category × profile and the transit supply; write outputs + report."""
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    stage_dir = ctx.stage_dir(STAGE)
    vdir = ctx.stage_dir(validate.STAGE)
    inputs = [config_input(ctx.config, CONFIG_SECTIONS), *file_inputs(_input_paths(ctx))]
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        log.info("inputs unchanged since %s, nothing to do", previous.finished_at.isoformat())
        return previous

    started_at = datetime.now(UTC)
    with measure() as m:
        day = reference_day(vdir)
        gtfs_dir = ctx.raw_dir / "gtfs"
        cal, dates = gtfs.read_calendar(gtfs_dir)
        services = gtfs.active_service_ids(cal, dates, day)
        departures = transit.departures_per_stop(gtfs_dir, services)
        log.info(
            "reference day %s: %d services, %d stops with departures",
            day,
            len(services),
            len(departures),
        )
        data, stops = load_data(vdir, departures)
        access, supply, stats, evidence = asyncio.run(_count_all(ctx.config, data))

        stage_dir.mkdir(parents=True, exist_ok=True)
        outputs = []
        for name, frame in ((ACCESS, access), (TRANSIT, supply), (STOPS, stops)):
            frame.to_parquet(stage_dir / name, index=False)
            outputs.append(FileOutput(path=str(stage_dir / name), rows=len(frame)))

    beyond = {pid: ev["facilities"]["beyond_prefilter"] for pid, ev in evidence["profiles"].items()}
    report = {
        "run_id": ctx.run_id,
        "stage": STAGE,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "reference_weekday": day.isoformat(),
        "cells": len(data.cell_ids),
        "profiles": stats,
        "evidence": evidence,
        "runtime_s": m.runtime_s,
        "peak_rss_mb": m.peak_rss_mb,
    }
    (stage_dir / REPORT).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    outputs.append(FileOutput(path=str(stage_dir / REPORT)))
    if any(beyond.values()):
        log.warning(
            "prefilter evidence: facilities reachable beyond the prefilter reach %s; "
            "propose a larger max_speed_factor/prefilter_margin_m (O20, ask first)",
            beyond,
        )
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
            f"{len(access)} counts ({len(data.cell_ids)} cells × "
            f"{access['category'].nunique()} categories × {len(stats)} profiles), "
            f"{len(supply)} transit rows, {sum(s['requests'] for s in stats.values())} "
            f"matrix requests; beyond prefilter: {beyond}"
        ),
    )
    write_manifest(manifest, stage_dir)
    return manifest
