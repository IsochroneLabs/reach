"""V1 matrix counts vs. isochrone point-in-polygon counts (architecture §6.3, decision D2).

For a random sample of scored cells, one Valhalla isochrone (facility budget, the app's
simplification from `config.yaml` `api.isochrone`) per profile is requested from the cell
origin; a facility counts "by polygon" if any of its routing points lies inside it. Cells
without an isochrone are left out of both counts. Compared with the matrix (`reachable`): counts and
classes per cell × category, and the pairs only one method finds. A pair "crosses a barrier"
if the straight line from the origin to the facility point crosses a river, canal, rail line
or motorway (`v01.barrier_tags`, OSM lines of the run's clipped PBF).
"""

from __future__ import annotations

import asyncio
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from reach_pipeline import osm, scoring
from reach_pipeline.experiments import common
from reach_pipeline.experiments.common import Experiment
from reach_pipeline.stages import count as count_stage
from reach_pipeline.stages import validate
from reach_pipeline.valhalla.client import ValhallaClient, costing_options

NAME = "v01"
TITLE = "Matrix counts vs. isochrone point-in-polygon counts"


def barriers(e: Experiment) -> shapely.Geometry:
    """Union of the barrier lines (EPSG:25832)."""
    work = e.out / "osm"
    work.mkdir(exist_ok=True)
    pbf = e.ctx.stage_dir(validate.STAGE) / validate.ROUTING_PBF
    exprs = osm.tag_expressions(e.settings.v01.barrier_tags, "w")
    filtered = osm.tags_filter(pbf, work / "barriers.osm.pbf", exprs)
    lines = osm.read_export(osm.export(filtered, work / "barriers.geojsonseq", ["linestring"]))
    return shapely.union_all(lines.geometry.values) if len(lines) else shapely.GeometryCollection()


def polygon_pairs(
    polygon: shapely.Geometry, points: gpd.GeoDataFrame, tree: shapely.STRtree
) -> np.ndarray:
    """Indices of facility points inside the polygon."""
    return tree.query(polygon, predicate="contains")


async def isochrones(
    e: Experiment, lonlat: np.ndarray, profile_id: str
) -> list[shapely.Geometry | None]:
    iso_cfg = e.cfg.api["isochrone"]  # the app's simplification (config.yaml api.isochrone)
    profile = e.cfg.profiles[profile_id]
    budget = e.cfg.time_budgets_min.facilities
    async with ValhallaClient(e.cfg.valhalla) as client:

        async def one(lon: float, lat: float) -> shapely.Geometry | None:
            body = await client.post(
                "isochrone",
                {
                    "locations": [{"lon": float(lon), "lat": float(lat)}],
                    "costing": profile.costing,
                    "costing_options": costing_options(profile),
                    "contours": [{"time": budget}],
                    "polygons": True,
                    "generalize": iso_cfg["generalize_m"],
                    "denoise": iso_cfg["denoise"],
                },
            )
            geoms = [shapely.geometry.shape(f["geometry"]) for f in body.get("features", [])]
            return shapely.union_all(geoms) if geoms else None

        return await asyncio.gather(*(one(lon, lat) for lon, lat in lonlat))


def compare_pairs(
    iso: pd.DataFrame, matrix: pd.DataFrame, cells: pd.DataFrame, k: pd.Series
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`iso`, `matrix`: pairs (`cell_id`, `facility_id`, `category`). Returns the pair table with
    `in_iso`, `in_matrix` and the per cell × category counts with both classes."""
    keys = ["cell_id", "facility_id", "category"]
    pairs = (
        iso[keys]
        .assign(in_iso=True)
        .merge(matrix[keys].assign(in_matrix=True), on=keys, how="outer")
    )
    pairs = pairs.fillna({"in_iso": False, "in_matrix": False}).astype(
        {"in_iso": bool, "in_matrix": bool}
    )
    full = pd.MultiIndex.from_product(
        [cells["cell_id"], list(k.index)], names=["cell_id", "category"]
    )
    counts = (
        pairs.groupby(["cell_id", "category"])[["in_iso", "in_matrix"]]
        .sum()
        .reindex(full, fill_value=0)
        .rename(columns={"in_iso": "count_iso", "in_matrix": "count_matrix"})
        .reset_index()
        .merge(cells[["cell_id", "population"]], on="cell_id")
    )
    kk = k.reindex(counts["category"]).to_numpy()
    counts["class_iso"] = scoring.classify(counts["count_iso"].to_numpy(), kk)
    counts["class_matrix"] = scoring.classify(counts["count_matrix"].to_numpy(), kk)
    return pairs, counts


def run(e: Experiment) -> dict[str, Any]:
    s = e.settings.v01
    cells = e.cells.reset_index(drop=True)
    rng = e.rng(1)
    sample = cells.iloc[
        np.sort(rng.choice(len(cells), size=min(s.sample_cells, len(cells)), replace=False))
    ]
    o_xy = common.xy(sample["origin_geom"])
    o_lonlat = count_stage._lonlat(o_xy)
    fp = e.facility_points.reset_index(drop=True)
    fp_cat = fp.merge(e.facilities[["facility_id", "category"]], on="facility_id")
    tree = shapely.STRtree(fp.geometry.values)
    barrier = barriers(e)
    k = e.k()
    rows, per_profile, all_pairs, all_counts = [], {}, [], []
    for pid in s.profiles:
        polys = asyncio.run(isochrones(e, o_lonlat, pid))
        iso_rows = []
        for cell_id, poly in zip(sample["cell_id"], polys, strict=True):
            if poly is None:
                continue
            poly_m = gpd.GeoSeries([poly], crs="EPSG:4326").to_crs(validate.METRIC_CRS).iat[0]
            hit = polygon_pairs(poly_m, fp, tree)
            ids = set(fp["facility_id"].to_numpy()[hit])
            sub = fp_cat[fp_cat["facility_id"].isin(ids)][["facility_id", "category"]]
            iso_rows.append(sub.drop_duplicates().assign(cell_id=cell_id))
        with_iso = sample["cell_id"].to_numpy()[[p is not None for p in polys]]
        iso = (
            pd.concat(iso_rows, ignore_index=True)
            if iso_rows
            else pd.DataFrame(columns=["facility_id", "category", "cell_id"])
        )
        reach = e.reachable[
            (e.reachable["profile_id"] == pid) & e.reachable["cell_id"].isin(with_iso)
        ].merge(e.facilities[["facility_id", "category"]], on="facility_id")
        pairs, counts = compare_pairs(iso, reach, sample[sample["cell_id"].isin(with_iso)], k)
        # Barrier test for every pair: straight line origin → nearest routing point.
        origin = dict(zip(sample["cell_id"], shapely.points(o_xy), strict=True))
        nearest = fp.groupby("facility_id").geometry.apply(lambda g: g.values)
        lines = [
            shapely.shortest_line(origin[c], shapely.multipoints(nearest[f]))
            for c, f in zip(pairs["cell_id"], pairs["facility_id"], strict=True)
        ]
        pairs["crosses_barrier"] = shapely.intersects(np.array(lines), barrier)
        pairs["profile_id"] = pid
        counts["profile_id"] = pid
        all_pairs.append(pairs)
        all_counts.append(counts)
        kind = np.select(
            [pairs["in_iso"] & pairs["in_matrix"], pairs["in_iso"]],
            ["both", "polygon_only"],
            "matrix_only",
        )
        changed = counts["class_iso"] != counts["class_matrix"]
        per_profile[pid] = {
            "cells": int(len(sample)),
            "isochrones_missing": int(sum(p is None for p in polys)),
            "pairs_both": int((kind == "both").sum()),
            "pairs_polygon_only": int((kind == "polygon_only").sum()),
            "pairs_matrix_only": int((kind == "matrix_only").sum()),
            "overcount_share": round(
                float((kind == "polygon_only").sum() / max(1, pairs["in_matrix"].sum())), 4
            ),
            "undercount_share": round(
                float((kind == "matrix_only").sum() / max(1, pairs["in_matrix"].sum())), 4
            ),
            "barrier_share_polygon_only": round(
                float(pairs.loc[kind == "polygon_only", "crosses_barrier"].mean()), 4
            )
            if (kind == "polygon_only").any()
            else None,
            "barrier_share_both": round(
                float(pairs.loc[kind == "both", "crosses_barrier"].mean()), 4
            )
            if (kind == "both").any()
            else None,
            "cell_category_pairs_count_differs": round(
                float((counts["count_iso"] != counts["count_matrix"]).mean()), 4
            ),
            "cell_category_pairs_class_differs": round(float(changed.mean()), 4),
            "residents_class_differs_share": round(
                float(counts.loc[changed, "population"].sum() / counts["population"].sum()), 4
            ),
            "mean_count_iso_minus_matrix": round(
                float((counts["count_iso"] - counts["count_matrix"]).mean()), 3
            ),
        }
        by_cat = counts.assign(diff=counts["count_iso"] - counts["count_matrix"], changed=changed)
        rows.append(
            by_cat.groupby("category")
            .agg(mean_diff=("diff", "mean"), class_differs=("changed", "mean"))
            .round(3)
            .reset_index()
            .assign(profile_id=pid)
        )
    pd.concat(all_pairs).to_csv(e.out / "pairs.csv", index=False)
    pd.concat(all_counts).to_csv(e.out / "counts.csv", index=False)
    return {
        "status": "done",
        "profiles": per_profile,
        "per_category": common.records(pd.concat(rows, ignore_index=True)),
    }
