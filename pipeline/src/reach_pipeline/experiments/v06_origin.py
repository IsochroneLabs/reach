"""V6 origin point: cell centroid vs. building-based origin (notes N1).

Building origin per scored cell (N1 steps 1–5): OSM residential buildings whose centroid lies in
the cell (`v06.residential_buildings`; `building=yes` only inside `landuse=residential`),
weighted by footprint area; the origin is a point inside the building whose centroid is closest
to the weighted centroid (medoid), so it lies on a real residential building. Cells without such
a building keep the centroid. The counts are recomputed exactly as `count` does (same blocks,
targets and matrix; the recount with unchanged origins reproduces the run bit for bit) and
compared with the run's counts.
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from reach_pipeline import osm
from reach_pipeline.experiments import common
from reach_pipeline.experiments.common import Experiment
from reach_pipeline.stages import count as count_stage
from reach_pipeline.stages import validate

NAME = "v06"
TITLE = "Origin point: cell centroid vs. building-based origin"


def residential(
    buildings: gpd.GeoDataFrame, landuse: gpd.GeoSeries, types: list[str]
) -> gpd.GeoDataFrame:
    """Residential buildings (N1 step 2)."""
    b = buildings[buildings.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    typed = b["building"].isin(types)
    yes = b["building"].eq("yes")
    inside = np.zeros(len(b), dtype=bool)
    if yes.any() and len(landuse):
        hit, _ = landuse.sindex.query(b.geometry.centroid.values, predicate="within")
        inside[np.unique(hit)] = True
    return b[typed.to_numpy() | (yes.to_numpy() & inside)]


def building_origins(
    cells: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame
) -> tuple[np.ndarray, np.ndarray]:
    """Origin per cell (x, y EPSG:25832) and whether it comes from a building."""
    origin = common.xy(cells["origin_geom"]).copy()
    from_building = np.zeros(len(cells), dtype=bool)
    if buildings.empty:
        return origin, from_building
    pts = gpd.GeoDataFrame(
        {
            "area": buildings.geometry.area.to_numpy(),
            "inner": buildings.geometry.representative_point().values,
        },
        geometry=buildings.geometry.centroid.values,
        crs=buildings.crs,
    )
    joined = gpd.sjoin(
        pts, cells[["geometry"]].reset_index(names="cell"), predicate="within", how="inner"
    )
    if joined.empty:
        return origin, from_building
    bx, by = joined.geometry.x.to_numpy(), joined.geometry.y.to_numpy()
    w = joined["area"].to_numpy()
    cell = joined["cell"].to_numpy()
    sw = np.bincount(cell, weights=w, minlength=len(cells))
    cx = np.bincount(cell, weights=w * bx, minlength=len(cells))
    cy = np.bincount(cell, weights=w * by, minlength=len(cells))
    with np.errstate(invalid="ignore", divide="ignore"):
        wx, wy = cx / sw, cy / sw
    d = np.hypot(bx - wx[cell], by - wy[cell])
    order = np.lexsort((d, cell))  # nearest building to the weighted centroid first per cell
    first = order[np.r_[True, cell[order][1:] != cell[order][:-1]]]
    inner = gpd.GeoSeries(joined["inner"].to_numpy()[first])
    origin[cell[first]] = np.column_stack([inner.x.to_numpy(), inner.y.to_numpy()])
    from_building[cell[first]] = True
    return origin, from_building


def load_buildings(e: Experiment) -> tuple[gpd.GeoDataFrame, gpd.GeoSeries]:
    work = e.out / "osm"
    work.mkdir(exist_ok=True)
    vdir = e.ctx.stage_dir(validate.STAGE)
    filtered = osm.tags_filter(
        vdir / validate.ROUTING_PBF, work / "buildings.osm.pbf", ["wr/building"]
    )
    exported = osm.export(filtered, work / "buildings.geojsonseq", ["polygon"])
    bounds = gpd.GeoSeries([e.cells.union_all()], crs=e.cells.crs).to_crs("EPSG:4326")
    bbox = tuple(bounds.total_bounds)
    buildings = osm.read_export(exported, bbox=bbox)[["osm_id", "building", "geometry"]]
    landuse = osm.read_export(
        vdir / "osm" / "admin_landuse.geojsonseq", bbox=bbox, where="landuse='residential'"
    )
    landuse = landuse[landuse.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].geometry
    return buildings, landuse.reset_index(drop=True)


def run(e: Experiment) -> dict[str, Any]:
    s = e.settings.v06
    cells = e.cells.reset_index(drop=True)
    buildings, landuse = load_buildings(e)
    res = residential(buildings, landuse, s.residential_buildings)
    origin, from_building = building_origins(cells, res)
    shift = np.hypot(*(origin - common.xy(cells["origin_geom"])).T)
    pd.DataFrame(
        {
            "cell_id": cells["cell_id"],
            "x": origin[:, 0],
            "y": origin[:, 1],
            "from_building": from_building,
            "shift_m": shift.round(1),
        }
    ).to_csv(e.out / "origins.csv", index=False)

    count_stage.check_valhalla_config(e.ctx)
    data = common.load_count_data(e.ctx)
    if not np.array_equal(data.cell_ids, cells["cell_id"].to_numpy()):
        raise ValueError("cell order differs between validate's cells and the count arrays")
    data = dataclasses.replace(data, origin_xy=origin, origin_lonlat=count_stage._lonlat(origin))
    budget = e.cfg.time_budgets_min.facilities
    alt, _, stats = asyncio.run(common.recount(e.cfg, data, s.profiles, budget))
    alt.to_parquet(e.out / "access_counts.parquet", index=False)
    base = e.access[e.access["profile_id"].isin(s.profiles)]
    k = e.k()
    table = common.compare(base, alt, cells, k)
    e.write_table("classes.csv", table)
    dd = common.district_deficits(base, cells, k).merge(
        common.district_deficits(alt, cells, k),
        on=["profile_id", "category", "district_id"],
        suffixes=("_centroid", "_building"),
    )
    dd["deficit_change"] = (dd["deficit_sum_building"] - dd["deficit_sum_centroid"]).round(1)
    dd = dd.merge(e.districts[["district_id", "name"]], on="district_id")
    e.write_table("districts.csv", dd)
    tot = table.groupby("profile_id")[["residents_changed", "residents_worse", "residents"]].sum()
    pop = cells["population"].to_numpy()
    return {
        "status": "done",
        "buildings_osm": int(len(buildings)),
        "buildings_residential": int(len(res)),
        "building_yes_share": round(float(buildings["building"].eq("yes").mean()), 4),
        "cells_with_building_origin": int(from_building.sum()),
        "residents_with_building_origin_share": round(
            float(pop[from_building].sum() / pop.sum()), 4
        ),
        "shift_m": {
            "median": round(float(np.median(shift[from_building])), 1),
            "p90": round(float(np.percentile(shift[from_building], 90)), 1),
            "max": round(float(shift.max()), 1),
        },
        "recount": stats,
        "profiles": {
            pid: {
                "share_resident_class_changes": round(
                    float(r["residents_changed"] / r["residents"]), 4
                ),
                "share_resident_worse": round(float(r["residents_worse"] / r["residents"]), 4),
            }
            for pid, r in tot.iterrows()
        },
        "per_category": common.records(
            table[
                [
                    "profile_id",
                    "category",
                    "share_residents_changed",
                    "share_lack_base",
                    "share_lack_alt",
                    "deficit_base",
                    "deficit_alt",
                ]
            ]
        ),
        "largest_district_changes": common.records(
            dd.reindex(dd["deficit_change"].abs().sort_values(ascending=False).index).head(10)[
                [
                    "profile_id",
                    "category",
                    "name",
                    "deficit_sum_centroid",
                    "deficit_sum_building",
                    "deficit_change",
                ]
            ]
        ),
    }
