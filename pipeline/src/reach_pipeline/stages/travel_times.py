"""travel_times: raw door-to-door times cell × destination × mode × window (meth. §4, arch. §6.3).

Targets come from `targets.py`: nearest k per destination type and per offered label, every
campus site; transit takes `transit_candidate_factor` × k per type and
`transit_candidate_factor_label` × k per label. Each destination is routed in the window of its
type; `direction: back` windows route from the destination to the cell.

- walk, bike: Valhalla `sources_to_targets` (costmatrix) per block of cells
  (`block_size_m`); parks are routed to all their access points and keep the shortest time.
- transit, bike_transit: OpenTripPlanner, one query per cell × destination point (pairs with the
  same point coordinates are asked once), bounded concurrency, in batches of `otp_batch`.
  Transit is never slower than walking: where the walk time is shorter it replaces the transit
  time (`walk_only`).

Writes `travel_times.parquet` (data contract), `pairs.parquet` and `report.json`. A mode whose
`<mode>.parquet` was written with the same inputs is reused, so a failed run resumes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer

from reach_pipeline import otp, targets
from reach_pipeline.config import Config
from reach_pipeline.context import RunContext
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    config_input,
    file_inputs,
    require_ok,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import transit, validate
from reach_pipeline.timing import window_datetime
from reach_pipeline.valhalla.client import ValhallaClient, costing_options

STAGE = "travel_times"
CONFIG_SECTIONS = (
    "destination_labels",
    "destination_types",
    "otp",
    "routing_profiles",
    "timezone",
    "travel_times",
    "trip_windows",
    "valhalla",
)
PREVIOUS = transit.STAGE
OUT = "travel_times.parquet"
PAIRS = "pairs.parquet"
REPORT = "report.json"
LEG_COLUMNS = [
    "access_s",
    "wait_s",
    "in_vehicle_s",
    "egress_s",
    "transfers",
    "first_stop",
    "first_route",
    "departure",
]
COLUMNS = ["cell_id", "destination_id", "mode", "trip_window", "time_s", *LEG_COLUMNS, "walk_only"]

log = logging.getLogger(__name__)
_to_lonlat = Transformer.from_crs(validate.METRIC_CRS, "EPSG:4326", always_xy=True)


# --- inputs ----------------------------------------------------------------------------------


def load_inputs(ctx: RunContext) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Origins (`cell_id`, point) and destination points (`destination_id`, `destination_type`,
    `point_id`, point) of types and labels."""
    v = ctx.stage_dir(validate.STAGE)
    cells = gpd.read_parquet(v / "cells.parquet")
    origins = gpd.GeoDataFrame(
        {"cell_id": cells["cell_id"].to_numpy()},
        geometry=cells["origin_geom"].to_numpy(),
        crs=validate.METRIC_CRS,
    )
    dest = gpd.read_parquet(v / "destinations.parquet")
    parts = [dest[["destination_id", "destination_type", "point_id", "geometry"]]]
    lab_path = v / "destination_labels.parquet"
    if lab_path.exists():
        lab = gpd.read_parquet(lab_path)
        lab = lab[lab["offered"]]
        parts.append(
            lab.assign(point_id=lab["destination_id"])[
                ["destination_id", "destination_type", "point_id", "geometry"]
            ]
        )
    points = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=validate.METRIC_CRS)
    return origins, points


def select_pairs(
    origins: gpd.GeoDataFrame, points: gpd.GeoDataFrame, cfg: Config
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pairs for walk/bike (factor 1) and for transit (candidate factors), one row per cell ×
    destination; transit pairs include every walk pair."""
    tt = cfg.travel_times
    first = points.drop_duplicates("destination_id")
    is_label = first["destination_id"].str.count(":") >= 2
    type_groups = targets.type_groups(first[~is_label], cfg)
    labels = first[is_label]
    k_label = cfg.destination_labels.nearest_k_label if cfg.destination_labels else 2
    label_groups = [
        targets.Group(key=f"label:{t}:{lbl}", k=k_label, destinations=g.reset_index(drop=True))
        for (t, lbl), g in labels.assign(
            lbl=labels["destination_id"].str.split(":").str[1]
        ).groupby(["destination_type", "lbl"])
    ]
    base = targets.pairs(origins, type_groups + label_groups, 1)
    extra = pd.concat(
        [
            targets.pairs(origins, type_groups, tt.transit_candidate_factor),
            targets.pairs(origins, label_groups, tt.transit_candidate_factor_label),
        ],
        ignore_index=True,
    )
    pt = pd.concat([base, extra], ignore_index=True).drop_duplicates(["cell_id", "destination_id"])
    return base.reset_index(drop=True), pt.reset_index(drop=True)


def windows_of(points: gpd.GeoDataFrame, cfg: Config) -> pd.Series:
    """Trip window per destination id (the window of its type)."""
    first = points.drop_duplicates("destination_id").set_index("destination_id")
    return first["destination_type"].map(
        {k: v.trip_window for k, v in cfg.destination_types.items()}
    )


def _lonlat(geoms: gpd.GeoSeries) -> np.ndarray:
    x, y = _to_lonlat.transform(geoms.x.to_numpy(), geoms.y.to_numpy())
    return np.column_stack([x, y])


# --- Valhalla --------------------------------------------------------------------------------


async def _valhalla_mode(
    client: ValhallaClient,
    pairs: pd.DataFrame,
    origins: gpd.GeoDataFrame,
    points: gpd.GeoDataFrame,
    window: pd.Series,
    back: set[str],
    profile_name: str,
    cfg: Config,
) -> pd.DataFrame:
    profile = cfg.routing_profiles[profile_name]
    options = costing_options(profile)
    o_ll = pd.DataFrame(_lonlat(origins.geometry), index=origins["cell_id"], columns=["lon", "lat"])
    p_ll = pd.DataFrame(_lonlat(points.geometry), index=points["point_id"], columns=["lon", "lat"])
    exp = pairs[["cell_id", "destination_id"]].merge(
        points[["destination_id", "point_id"]], on="destination_id"
    )
    exp["trip_window"] = exp["destination_id"].map(window)
    exp["back"] = exp["trip_window"].isin(back)
    xy = origins.set_index("cell_id").geometry
    bs = cfg.travel_times.block_size_m
    cx, cy = xy.x.reindex(exp["cell_id"]).to_numpy(), xy.y.reindex(exp["cell_id"]).to_numpy()
    exp["block"] = (
        (np.floor(cx / bs)).astype(int).astype(str)
        + "_"
        + (np.floor(cy / bs)).astype(int).astype(str)
    )
    exp["time_s"] = np.nan

    async def one(idx: np.ndarray, back_dir: bool) -> None:
        sub = exp.loc[idx]
        cells = sub["cell_id"].unique()
        pts = sub["point_id"].unique()
        if back_dir:
            m = await client.matrix(
                p_ll.loc[pts].to_numpy(), o_ll.loc[cells].to_numpy(), profile.costing, options
            )
            m = m.T
        else:
            m = await client.matrix(
                o_ll.loc[cells].to_numpy(), p_ll.loc[pts].to_numpy(), profile.costing, options
            )
        ci = pd.Index(cells).get_indexer(sub["cell_id"])
        pi = pd.Index(pts).get_indexer(sub["point_id"])
        exp.loc[idx, "time_s"] = m[ci, pi]

    groups = exp.groupby(["block", "back"]).indices
    await asyncio.gather(*(one(idx, bool(key[1])) for key, idx in groups.items()))
    best = exp.groupby(["cell_id", "destination_id", "trip_window"], as_index=False)["time_s"].min()
    best["mode"] = profile_name
    best["walk_only"] = False
    return best


# --- OpenTripPlanner -------------------------------------------------------------------------


async def _otp_mode(
    client: otp.OtpClient,
    pairs: pd.DataFrame,
    origins: gpd.GeoDataFrame,
    points: gpd.GeoDataFrame,
    window: pd.Series,
    refs: dict[str, date],
    profile_name: str,
    cfg: Config,
) -> pd.DataFrame:
    profile = cfg.routing_profiles[profile_name]
    first = points.drop_duplicates("destination_id").set_index("destination_id")
    o_ll = pd.DataFrame(_lonlat(origins.geometry), index=origins["cell_id"], columns=["lon", "lat"])
    d_ll = pd.DataFrame(_lonlat(first.geometry), index=first.index, columns=["lon", "lat"])
    q = pairs[["cell_id", "destination_id"]].copy()
    q["trip_window"] = q["destination_id"].map(window)
    q[["dlon", "dlat"]] = d_ll.reindex(q["destination_id"]).round(6).to_numpy()
    uniq = q.drop_duplicates(["cell_id", "dlon", "dlat", "trip_window"]).reset_index(drop=True)
    log.info("%s: %d pairs, %d OTP queries", profile_name, len(q), len(uniq))
    rows: list[dict[str, Any]] = []
    batch = cfg.travel_times.otp_batch
    started = datetime.now(UTC)
    for start in range(0, len(uniq), batch):
        part = uniq.iloc[start : start + batch]
        coros = []
        for r in part.itertuples(index=False):
            w = cfg.trip_windows[r.trip_window]
            when = window_datetime(refs[r.trip_window], w.time, cfg.timezone)
            cell = (float(o_ll.at[r.cell_id, "lon"]), float(o_ll.at[r.cell_id, "lat"]))
            dest = (float(r.dlon), float(r.dlat))
            o, d = (dest, cell) if w.direction == "back" else (cell, dest)
            coros.append(client.plan(o, d, when, w.mode == "arrive_by", profile.access))
        trips = await asyncio.gather(*coros)
        rows += [asdict(t) for t in trips]
        done = start + len(part)
        rate = done / max((datetime.now(UTC) - started).total_seconds(), 1e-6)
        log.info("%s: %d / %d queries (%.0f/s)", profile_name, done, len(uniq), rate)
    res = pd.concat([uniq, pd.DataFrame(rows)], axis=1)
    out = q.merge(
        res.drop(columns=["destination_id"]), on=["cell_id", "dlon", "dlat", "trip_window"]
    )
    out["mode"] = profile_name
    return out.drop(columns=["dlon", "dlat"])


def cap_by_walk(tr: pd.DataFrame, walk: pd.DataFrame | None) -> pd.DataFrame:
    """Transit is never slower than walking the whole way (meth. §4)."""
    if walk is None or tr.empty:
        return tr
    w = walk.set_index(["cell_id", "destination_id"])["time_s"]
    wt = w.reindex(pd.MultiIndex.from_frame(tr[["cell_id", "destination_id"]])).to_numpy()
    slower = np.isfinite(wt) & (np.isnan(tr["time_s"].to_numpy(float)) | (wt < tr["time_s"]))
    tr = tr.copy()
    tr.loc[slower, "time_s"] = wt[slower]
    tr.loc[slower, LEG_COLUMNS] = None
    tr.loc[slower, "walk_only"] = True
    return tr


def finish(frame: pd.DataFrame) -> pd.DataFrame:
    """Columns and types of the data contract."""
    for c in COLUMNS:
        if c not in frame:
            frame[c] = None
    out = frame[COLUMNS].copy()
    out["time_s"] = out["time_s"].round().astype("Int32")
    for c in ["access_s", "wait_s", "in_vehicle_s", "egress_s"]:
        out[c] = pd.to_numeric(out[c]).round().astype("Int32")
    out["transfers"] = pd.to_numeric(out["transfers"]).astype("Int16")
    out["walk_only"] = out["walk_only"].fillna(False).astype(bool)
    for c in ["first_stop", "first_route", "departure"]:
        out[c] = out[c].astype("string")
    return out


# --- stage -----------------------------------------------------------------------------------


def _inputs(ctx: RunContext) -> list:
    v = ctx.stage_dir(validate.STAGE)
    files = [v / "cells.parquet", v / "destinations.parquet"]
    if (v / "destination_labels.parquet").exists():
        files.append(v / "destination_labels.parquet")
    return [config_input(ctx.config, CONFIG_SECTIONS), *file_inputs(files)]


def _cached(stage_dir: Path, mode: str, digest: str) -> pd.DataFrame | None:
    path, tag = stage_dir / f"{mode}.parquet", stage_dir / f"{mode}.inputs"
    if path.exists() and tag.exists() and tag.read_text() == digest:
        log.info("%s: reusing %s (same inputs)", mode, path.name)
        return pd.read_parquet(path)
    return None


async def _route(ctx: RunContext, stage_dir: Path, digest: str) -> tuple[pd.DataFrame, dict]:
    cfg = ctx.config
    origins, points = load_inputs(ctx)
    base, tpairs = select_pairs(origins, points, cfg)
    base.to_parquet(stage_dir / PAIRS, index=False)
    window = windows_of(points, cfg)
    back = {k for k, w in cfg.trip_windows.items() if w.direction == "back"}
    refs = transit.reference_dates(ctx)
    report: dict[str, Any] = {
        "pairs": targets.summary(base, origins),
        "transit_pairs": len(tpairs),
        "modes": {},
    }
    frames: dict[str, pd.DataFrame] = {}
    for mode in cfg.travel_times.modes:
        cached = _cached(stage_dir, mode, digest)
        with measure() as m:
            if cached is not None:
                frames[mode] = cached
            elif cfg.routing_profiles[mode].engine == "valhalla":
                async with ValhallaClient(cfg.valhalla) as vc:
                    frames[mode] = await _valhalla_mode(
                        vc, base, origins, points, window, back, mode, cfg
                    )
            else:
                async with otp.OtpClient(cfg.otp) as oc:
                    frames[mode] = await _otp_mode(
                        oc, tpairs, origins, points, window, refs, mode, cfg
                    )
            if cached is None:
                frames[mode].to_parquet(stage_dir / f"{mode}.parquet", index=False)
                (stage_dir / f"{mode}.inputs").write_text(digest)
        f = frames[mode]
        report["modes"][mode] = {
            "rows": len(f),
            "unreachable_share": round(float(f["time_s"].isna().mean()), 4) if len(f) else 0.0,
            "median_min": round(float(f["time_s"].median()) / 60, 1) if len(f) else None,
            "runtime_s": m.runtime_s,
            "peak_rss_mb": m.peak_rss_mb,
            "reused": cached is not None,
        }
        log.info("%s: %s", mode, report["modes"][mode])
    walk = frames.get("walk")
    for mode in list(frames):
        if cfg.routing_profiles[mode].engine == "otp":
            frames[mode] = cap_by_walk(frames[mode], walk)
            report["modes"][mode]["walk_only_share"] = round(
                float(frames[mode]["walk_only"].mean()), 4
            )
    return finish(pd.concat(frames.values(), ignore_index=True)), report


def run(ctx: RunContext) -> Manifest:
    """Route all pairs and write the raw times, the pairs and the report."""
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    stage_dir = ctx.stage_dir(STAGE)
    stage_dir.mkdir(parents=True, exist_ok=True)
    inputs = _inputs(ctx)
    digest = ",".join(i.sha256 for i in inputs)
    started_at = datetime.now(UTC)
    with measure() as m:
        times, report = asyncio.run(_route(ctx, stage_dir, digest))
        times.to_parquet(stage_dir / OUT, index=False)
    report |= {"rows": len(times), "runtime_s": m.runtime_s, "peak_rss_mb": m.peak_rss_mb}
    (stage_dir / REPORT).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        outputs=[
            FileOutput(path=str(stage_dir / OUT), rows=len(times)),
            FileOutput(path=str(stage_dir / PAIRS), rows=report["pairs"]["pairs"]),
            FileOutput(path=str(stage_dir / REPORT)),
        ],
        message=f"{len(times)} travel times, modes {list(report['modes'])}",
    )
    write_manifest(manifest, stage_dir)
    return manifest
