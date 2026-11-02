"""Counting: blocks, prefilter (nothing within reach dropped), split by category, transit
supply, prefilter evidence, and the count stage end to end against a fake Valhalla."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import httpx
import numpy as np
import pandas as pd
import pytest
import respx
import shapely
import yaml
from pyproj import Transformer

from reach_pipeline import count
from reach_pipeline.config import load_config
from reach_pipeline.context import RunContext
from reach_pipeline.manifest import Manifest, read_manifest, write_manifest
from reach_pipeline.stages import count as count_stage
from reach_pipeline.stages import tiles, validate

REPO = Path(__file__).resolve().parents[2]
CRS = "EPSG:25832"
X0, Y0 = 503_000.0, 5_373_000.0  # Tübingen old town in EPSG:25832


def _targets(xy: np.ndarray) -> count.Targets:
    return count.Targets.build(xy, xy)


def test_make_blocks_groups_by_square() -> None:
    xy = np.array([[10, 10], [490, 20], [510, 10], [10, 600], [499.9, 499.9]])
    labels = count.make_blocks(xy, 500)
    assert labels[0] == labels[1] == labels[4]
    assert len({labels[0], labels[2], labels[3]}) == 3


def test_prefilter_never_drops_a_target_within_reach() -> None:
    rng = np.random.default_rng(1)
    targets = _targets(rng.uniform(-2000, 2500, size=(400, 2)))
    block = rng.uniform(0, 500, size=(25, 2))
    reach = 850.0
    chosen = set(count.prefilter(block, targets, reach).tolist())
    dist = np.linalg.norm(block[:, None, :] - targets.xy[None, :, :], axis=2)
    needed = set(np.flatnonzero((dist <= reach).any(axis=0)).tolist())
    assert needed <= chosen
    # ... and it stays a tight superset: nothing farther than reach from the block's box
    box = shapely.box(*block.min(axis=0), *block.max(axis=0))
    assert all(box.distance(shapely.Point(targets.xy[i])) <= reach for i in chosen)


def test_prefilter_zero_reach_is_empty() -> None:
    assert count.prefilter(np.zeros((1, 2)), _targets(np.zeros((3, 2))), 0).size == 0


def test_count_block_splits_categories_and_counts_facilities_once() -> None:
    # columns: 0,1,2 = three access points of park p1; 3 = shop s1 (grocery and pharmacy);
    # 4 = shop s2 (grocery)
    links = pd.DataFrame(
        {
            "target": [0, 1, 2, 3, 3, 4],
            "facility_id": ["p1", "p1", "p1", "s1", "s1", "s2"],
            "category": ["parks", "parks", "parks", "grocery", "pharmacy", "grocery"],
        }
    )
    times = np.array(
        [
            [950.0, 600.0, np.nan, 300.0, 300.0, 899.0],  # everything within 900 s
            [1000.0, 950.0, 990.0, np.nan, np.nan, 901.0],  # nothing within 900 s
        ]
    )
    out = count.count_block(times, links, budget_s=900).set_index(["source", "category"])
    assert out.loc[(0, "parks"), "count"] == 1  # three points, one park
    assert out.loc[(0, "parks"), "nearest_s"] == 600
    assert out.loc[(0, "grocery"), "count"] == 2
    assert out.loc[(0, "grocery"), "nearest_s"] == 300
    assert out.loc[(0, "pharmacy"), "count"] == 1
    assert out.loc[(1, "grocery"), "count"] == 0
    assert np.isnan(out.loc[(1, "grocery"), "nearest_s"])  # beyond budget → unknown


def test_transit_block_sums_departures_within_budget() -> None:
    times = np.array([[100.0, 650.0, np.nan], [700.0, 700.0, 700.0]])
    out = count.transit_block(times, np.array([10, 20, 30]), budget_s=600)
    assert out["departures"].tolist() == [10, 0]
    assert out["stops_count"].tolist() == [1, 0]
    assert out["nearest_stop_s"].iloc[0] == 100
    assert np.isnan(out["nearest_stop_s"].iloc[1])


def test_summarise_evidence() -> None:
    pairs = pd.DataFrame(
        {
            "distance_m": [100.0, 800.0, 900.0, 1500.0, 50.0],
            "time_s": [120.0, 850.0, 899.0, np.nan, 10.0],
        }
    )
    s = count.summarise_evidence(
        pairs, speed_kmh=3.6, budget_s=900, prefilter_reach_m=850, band_edges=[0.1, 0.5, 1.0]
    )
    assert s["nominal_reach_m"] == 900  # 1 m/s × 900 s
    assert s["reachable_pairs"] == 4
    assert s["max_reachable_distance_m"] == 900
    assert s["required_factor"] == 1.0
    assert s["beyond_nominal"] == 0
    assert s["beyond_prefilter"] == 1  # 900 m > 850 m prefilter reach
    # 10 s pair (snap-dominated) is below the first band; 120 s: 100 m → 0.833
    assert s["max_speed_ratio_by_band"] == {"0.10-0.50": 0.833, "0.50-1.00": 1.001}


# --- stage end to end ------------------------------------------------------------------------

RUN_ID = "20261116T030000Z"
_to_lonlat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
_to_metric = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)


def _points(xy: np.ndarray) -> gpd.GeoSeries:
    return gpd.GeoSeries(shapely.points(xy), crs=CRS)


@pytest.fixture
def stage_ctx(tmp_path: Path) -> RunContext:
    """Small synthetic run: 40 cells, facilities in 3 categories (one park with 3 access points,
    one shop in two categories), 6 stops and a one-day GTFS; validate and tiles manifests ok."""
    data = yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))
    data["data_dir"] = str(tmp_path / "data")
    data["profiles"] = {k: data["profiles"][k] for k in ("walking_339", "cycling_15")}
    data["count"]["block_size_m"] = 300
    data["valhalla"].update(url="http://valhalla.test", backoff_s=0, max_matrix_pairs=500)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    (tmp_path / "valhalla.json").write_text("{}", encoding="utf-8")
    ctx = RunContext(config=load_config(cfg_path), config_path=cfg_path, run_id=RUN_ID)

    rng = np.random.default_rng(7)
    vdir = ctx.stage_dir(validate.STAGE)
    vdir.mkdir(parents=True)
    origins = rng.uniform(0, 1200, size=(40, 2)) + [X0, Y0]
    cells = gpd.GeoDataFrame(
        {
            "cell_id": [f"c{i:02d}" for i in range(40)],
            "population": 10,
            "district_id": "r1",
            "origin_geom": _points(origins),
        },
        geometry=_points(origins).buffer(50, cap_style="square"),
        crs=CRS,
    )
    cells.to_parquet(vdir / "cells.parquet")
    fac_xy = rng.uniform(-2000, 3200, size=(30, 2)) + [X0, Y0]
    categories = ["grocery"] * 10 + ["pharmacy"] * 10 + ["school"] * 9 + ["parks"]
    fac = gpd.GeoDataFrame(
        {"facility_id": [f"n{i}" for i in range(30)], "category": categories, "name": None},
        geometry=_points(fac_xy),
        crs=CRS,
    )
    # n0 is also a pharmacy (same id, two categories)
    fac = pd.concat([fac, fac.iloc[[0]].assign(category="pharmacy")], ignore_index=True)
    fac.to_parquet(vdir / "facilities.parquet")
    park_extra = fac_xy[29] + np.array([[400.0, 0.0], [0.0, 400.0]])
    pts_xy = np.vstack([fac_xy, park_extra])
    points = gpd.GeoDataFrame(
        {
            "facility_id": [f"n{i}" for i in range(30)] + ["n29", "n29"],
            "point_id": list(range(30)) + [1, 2],
            "kind": ["node"] * 29 + ["access"] * 3,
        },
        geometry=_points(pts_xy),
        crs=CRS,
    )
    points.to_parquet(vdir / "facility_points.parquet")
    stop_xy = rng.uniform(0, 1200, size=(6, 2)) + [X0, Y0]
    gpd.GeoDataFrame(
        {"stop_id": [f"s{i}" for i in range(6)], "name": "x"}, geometry=_points(stop_xy), crs=CRS
    ).to_parquet(vdir / "stops.parquet")
    (vdir / validate.REPORT_JSON).write_text(
        json.dumps({"summary": {"reference_weekday": "2026-11-17"}}), encoding="utf-8"
    )
    (vdir / validate.ROUTING_PBF).write_bytes(b"pbf")

    gtfs = ctx.raw_dir / "gtfs"
    gtfs.mkdir(parents=True)
    (gtfs / "calendar.txt").write_text(
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "wk,1,1,1,1,1,0,0,20260101,20261231\nsun,0,0,0,0,0,0,1,20260101,20261231\n",
        encoding="utf-8",
    )
    (gtfs / "calendar_dates.txt").write_text("service_id,date,exception_type\n", encoding="utf-8")
    (gtfs / "trips.txt").write_text("route_id,service_id,trip_id\nr,wk,t1\nr,sun,t2\n", "utf-8")
    (gtfs / "stop_times.txt").write_text(
        "trip_id,stop_id,stop_sequence,pickup_type\nt1,s0,1,0\nt1,s1,2,0\nt1,s2,3,1\nt2,s0,1,0\n",
        encoding="utf-8",
    )
    now = datetime.now(UTC)
    for stage in (validate.STAGE, tiles.STAGE):
        write_manifest(
            Manifest(
                stage=stage,
                run_id=RUN_ID,
                status="ok",
                started_at=now,
                finished_at=now,
                runtime_s=0,
                peak_rss_mb=0,
            ),
            ctx.stage_dir(stage),
        )
    return ctx


def _fake_matrix(request: httpx.Request) -> httpx.Response:
    """Straight-line travel times at the requested speed (prefilter is then exact)."""
    body = json.loads(request.content)
    opts = next(iter(body["costing_options"].values()))
    speed = (opts.get("walking_speed") or opts.get("cycling_speed")) / 3.6

    def xy(locations: list[dict]) -> np.ndarray:
        x, y = _to_metric.transform([p["lon"] for p in locations], [p["lat"] for p in locations])
        return np.column_stack([x, y])

    s, t = xy(body["sources"]), xy(body["targets"])
    d = np.linalg.norm(s[:, None, :] - t[None, :, :], axis=2)
    return httpx.Response(200, json={"sources_to_targets": {"durations": (d / speed).tolist()}})


def test_count_stage_matches_brute_force(stage_ctx: RunContext) -> None:
    with respx.mock(base_url="http://valhalla.test") as router:
        router.post("/sources_to_targets").mock(side_effect=_fake_matrix)
        manifest = count_stage.run(stage_ctx)
    assert manifest.status == "ok"
    out = stage_ctx.stage_dir(count_stage.STAGE)
    access = pd.read_parquet(out / count_stage.ACCESS)
    cats = [c.id for c in stage_ctx.config.categories]
    assert len(access) == 40 * len(cats) * 2  # every cell × category × profile
    assert access.loc[access["category"] == "doctors", "count"].eq(0).all()
    assert access["count"].nunique() > 3  # the comparison below is not trivial
    # data contract (docs/data_contract.md, count/ files)
    assert list(access.columns) == ["cell_id", "category", "profile_id", "count", "nearest_min"]
    assert str(access["count"].dtype) == "int32" and str(access["nearest_min"].dtype) == "float64"
    assert access.loc[access["count"] == 0, "nearest_min"].isna().all()
    assert (access["nearest_min"].dropna() <= 15).all()

    vdir = stage_ctx.stage_dir(validate.STAGE)
    cells = gpd.read_parquet(vdir / "cells.parquet").set_geometry("origin_geom")
    points = gpd.read_parquet(vdir / "facility_points.parquet")
    fac = pd.read_parquet(vdir / "facilities.parquet")
    o = np.column_stack([cells.geometry.x, cells.geometry.y])
    p = np.column_stack([points.geometry.x, points.geometry.y])
    dist = pd.DataFrame(np.linalg.norm(o[:, None] - p[None], axis=2), columns=points.facility_id)
    per_fac = dist.T.groupby(level=0).min().T  # min over access points
    for pid, profile in stage_ctx.config.profiles.items():
        reach = profile.speed_kmh / 3.6 * 900
        got = access[access["profile_id"] == pid].set_index(["cell_id", "category"])["count"]
        for cat in ("grocery", "pharmacy", "parks"):
            ids = fac.loc[fac["category"] == cat, "facility_id"]
            expected = (per_fac[ids] <= reach).sum(axis=1).to_numpy()
            actual = got.xs(cat, level="category").reindex(cells["cell_id"]).to_numpy()
            np.testing.assert_array_equal(actual, expected, err_msg=f"{pid} {cat}")

    supply = pd.read_parquet(out / count_stage.TRANSIT)
    assert list(supply.columns) == [
        "cell_id",
        "profile_id",
        "departures",
        "stops_count",
        "nearest_stop_min",
    ]
    assert set(supply["profile_id"]) == {"walking_339"}  # cycling has no transit
    assert len(supply) == 40
    stops = pd.read_parquet(out / count_stage.STOPS).set_index("stop_id")
    # t1 runs on Tuesdays; s2 is the last stop without boarding; t2 runs on Sundays only
    assert stops["weekday_departures"].to_dict() == {
        "s0": 1,
        "s1": 1,
        "s2": 0,
        "s3": 0,
        "s4": 0,
        "s5": 0,
    }
    report = json.loads((out / count_stage.REPORT).read_text(encoding="utf-8"))
    ev = report["evidence"]["profiles"]["cycling_15"]["facilities"]
    assert ev["beyond_prefilter"] == 0 and ev["required_factor"] <= 1.0
    # unchanged inputs: the second run is a no-op
    assert count_stage.run(stage_ctx).finished_at == read_manifest(out).finished_at
