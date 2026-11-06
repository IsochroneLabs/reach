"""Recommender: candidate grid, land-use exclusion, greedy (against brute force), replay, and the
recommend stage end to end against a fake Valhalla (straight-line times)."""

from __future__ import annotations

import json
import subprocess
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

from reach_pipeline import recommend as rec
from reach_pipeline import zensus
from reach_pipeline.config import load_config
from reach_pipeline.context import RunContext
from reach_pipeline.manifest import Manifest, read_manifest, write_manifest
from reach_pipeline.stages import count, score, tiles, validate
from reach_pipeline.stages import recommend as stage

REPO = Path(__file__).resolve().parents[2]
CRS = "EPSG:25832"
RUN_ID = "20261116T030000Z"
X0, Y0 = 503_000.0, 5_373_000.0  # Tübingen old town in EPSG:25832
_to_metric = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
_to_lonlat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


# --- candidates ------------------------------------------------------------------------------


def test_candidate_grid_uses_zensus_ids_and_centres() -> None:
    area = shapely.box(X0, Y0, X0 + 450, Y0 + 350)
    grid = rec.candidate_grid(area, 100)
    assert len(grid) > 10 and grid["candidate_id"].is_unique
    assert shapely.contains_xy(area, grid.geometry.x, grid.geometry.y).all()
    # id = lower-left corner in EPSG:3035, centre = corner + 50 m (same as the Zensus cells)
    first = grid.iloc[0]
    n, e = (int(v) for v in first["candidate_id"].removeprefix("CRS3035RES100mN").split("E"))
    cell = zensus.cell_geometries(
        pd.DataFrame({"cell_id": ["x"], "x": [e + 50], "y": [n + 50], "population": [1]})
    )
    assert cell["origin_geom"].iloc[0].distance(first.geometry) < 1e-6
    assert cell.geometry.iloc[0].equals_exact(first["zone_geom"], 1e-6)
    # every second grid cell in both directions
    coarse = rec.candidate_grid(area, 200)
    assert set(coarse["candidate_id"]) < set(grid["candidate_id"])
    assert len(coarse) <= len(grid) / 3


def test_outside_and_near_any() -> None:
    pts = gpd.GeoSeries(shapely.points([[0, 0], [10, 10], [50, 50]]), crs=CRS)
    poly = gpd.GeoSeries([shapely.box(5, 5, 20, 20)], crs=CRS)
    assert rec.outside(pts, poly).tolist() == [True, False, True]
    assert rec.outside(pts, gpd.GeoSeries([], crs=CRS)).all()
    xy = np.array([[0.0, 0.0], [100.0, 0.0]])
    assert rec.near_any(xy, np.array([[0.0, 30.0]]), 50).tolist() == [True, False]
    assert not rec.near_any(xy, np.empty((0, 2)), 50).any()


def test_catchment_pairs_keeps_times_within_budget() -> None:
    times = np.array([[100.0, np.nan], [900.0, 901.0]])
    pairs = rec.catchment_pairs(times, 900)
    assert pairs[["source", "target"]].values.tolist() == [[0, 0], [1, 0]]
    assert pairs["time_s"].tolist() == [100, 900] and str(pairs["time_s"].dtype) == "int16"


# --- greedy ----------------------------------------------------------------------------------


def _naive(cover, pop, counts, k, top_n, min_gain):
    """Loop version of the greedy (methodology §5) for comparison."""
    a, used, out = list(counts), set(), []
    for _ in range(top_n):
        best, best_gain = None, -1.0
        for x in range(len(cover)):
            if x in used:
                continue
            g = sum(
                pop[i] * (min(1, (a[i] + 1) / k) - min(1, a[i] / k))
                for i in range(len(a))
                if cover[x][i]
            )
            if g > best_gain + 1e-9:
                best, best_gain = x, g
        if best is None or best_gain < min_gain:
            break
        out.append((best, round(best_gain, 2)))
        used.add(best)
        for i in range(len(a)):
            a[i] += int(cover[best][i])
    return out


@pytest.mark.parametrize("k", [1, 2, 3])
def test_greedy_matches_the_loop_version(k: int) -> None:
    rng = np.random.default_rng(k)
    cover = rng.random((30, 60)) < 0.15
    pop = rng.integers(0, 80, 60)
    counts = rng.integers(0, 3, 60)
    picks = rec.greedy(cover, pop, counts, k, 6, 1.0)
    assert [(p.candidate, p.population_gain) for p in picks] == _naive(
        cover, pop, counts, k, 6, 1.0
    )
    gains = [p.population_gain for p in picks]
    assert gains == sorted(gains, reverse=True)  # submodular: gains never grow
    assert [p.rank for p in picks] == list(range(1, len(picks) + 1))


def test_greedy_gain_is_the_deficit_reduction() -> None:
    # cells: population 100 / 50 / 10, counts 0 / 1 / 2, k = 2
    pop, counts = np.array([100, 50, 10]), np.array([0, 1, 2])
    cover = np.array([[1, 1, 1], [0, 1, 0], [1, 0, 0]], dtype=bool)
    deficit = lambda a: (pop * np.maximum(0, 1 - a / 2)).sum()  # noqa: E731 (methodology §4)
    picks = rec.greedy(cover, pop, counts, 2, 3, 0)
    first = picks[0]
    assert first.candidate == 0
    assert first.population_gain == deficit(counts) - deficit(counts + cover[0]) == 75
    assert first.residents_gaining_access == 100  # only cell 0 had A = 0
    assert first.residents_to_sufficient == 50  # cell 1: 1 → 2
    assert (first.catchment_residents, first.catchment_cells) == (160, 3)
    # k = 2: a second site for the same cells still helps (pure objective, each zone once)
    assert picks[1].candidate == 2 and picks[1].population_gain == 50
    replayed = rec.replay([np.flatnonzero(cover[p.candidate]) for p in picks], pop, counts, 2)
    assert replayed == [
        (p.population_gain, p.residents_gaining_access, p.residents_to_sufficient) for p in picks
    ]


def test_greedy_stops_below_min_gain_and_when_saturated() -> None:
    pop, counts = np.array([100, 40]), np.array([0, 0])
    cover = np.array([[1, 0], [1, 0], [0, 1]], dtype=bool)
    picks = rec.greedy(cover, pop, counts, 1, 5, 50)
    assert [p.candidate for p in picks] == [0]  # 100; then 0 (saturated) and 40 < 50
    assert rec.greedy(cover, pop, np.array([1, 1]), 1, 5, 0.5) == []  # nothing left to gain
    # min_gain 0 still stops at zero gain (no zones without effect)
    assert [p.candidate for p in rec.greedy(cover, pop, counts, 1, 5, 0)] == [0, 2]


# --- stage -----------------------------------------------------------------------------------


def _osm_with_forest(path: Path, box: tuple[float, float, float, float]) -> None:
    """Tiny OSM file: a forest polygon over `box` (EPSG:25832) and a park next to it."""
    x0, y0, x1, y1 = box
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    park = [(x + 2000, y) for x, y in corners]
    nodes, ways = [], []
    for w, (ring, tag) in enumerate(
        ((corners, ("landuse", "forest")), (park, ("leisure", "park")))
    ):
        refs = []
        for i, (x, y) in enumerate(ring):
            nid = 10 * (w + 1) + i
            lon, lat = _to_lonlat.transform(x, y)
            nodes.append(f'<node id="{nid}" version="1" lat="{lat:.7f}" lon="{lon:.7f}"/>')
            refs.append(nid)
        nds = "".join(f'<nd ref="{r}"/>' for r in [*refs, refs[0]])
        ways.append(f'<way id="{w + 1}" version="1">{nds}<tag k="{tag[0]}" v="{tag[1]}"/></way>')
    xml = path.with_suffix(".osm")
    xml.write_text(
        '<?xml version="1.0"?><osm version="0.6">' + "".join(nodes + ways) + "</osm>",
        encoding="utf-8",
    )
    subprocess.run(["osmium", "cat", str(xml), "-o", str(path), "--overwrite"], check=True)


@pytest.fixture
def stage_ctx(tmp_path: Path) -> RunContext:
    """Synthetic run: 60 cells over 1.5 km × 1 km, urban boundary = their extent, a forest in
    the lower-left corner; counts with deficits; validate, count and score manifests ok."""
    data = yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))
    data["data_dir"] = str(tmp_path / "data")
    data["profiles"] = {k: data["profiles"][k] for k in ("walking_339", "walking_500")}
    data["validation"]["results"]["monotonic"] = []
    data["recommend"].update(profiles=["walking_339", "walking_500"], min_gain=1, top_n=3)
    data["valhalla"].update(url="http://valhalla.test", backoff_s=0, max_matrix_pairs=500)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    vjson = json.dumps({"thor": {"source_to_target_algorithm": "costmatrix"}})
    (tmp_path / "valhalla.json").write_text(vjson, encoding="utf-8")
    ctx = RunContext(config=load_config(cfg_path), config_path=cfg_path, run_id=RUN_ID)
    tiles.effective_config(ctx).parent.mkdir(parents=True)
    tiles.effective_config(ctx).write_text(vjson, encoding="utf-8")

    rng = np.random.default_rng(3)
    vdir = ctx.stage_dir(validate.STAGE)
    vdir.mkdir(parents=True)
    origins = rng.uniform([0, 0], [1500, 1000], size=(60, 2)) + [X0, Y0]
    pts = gpd.GeoSeries(shapely.points(origins), crs=CRS)
    gpd.GeoDataFrame(
        {
            "cell_id": [f"c{i:02d}" for i in range(60)],
            "population": rng.integers(5, 120, 60),
            "district_id": "r1",
            "origin_geom": pts,
        },
        geometry=pts.buffer(50, cap_style="square"),
        crs=CRS,
    ).to_parquet(vdir / "cells.parquet")
    gpd.GeoDataFrame(
        {"part_id": [1], "name": [None]},
        geometry=[shapely.box(X0, Y0, X0 + 1500, Y0 + 1000)],
        crs=CRS,
    ).to_parquet(vdir / "urban_boundary.parquet")
    _osm_with_forest(vdir / validate.ROUTING_PBF, (X0 - 10, Y0 - 10, X0 + 300, Y0 + 300))

    cdir = ctx.stage_dir(count.STAGE)
    cdir.mkdir(parents=True)
    rows = [
        {
            "cell_id": f"c{i:02d}",
            "category": c.id,
            "profile_id": p,
            "count": int(rng.integers(0, 3)),
            "nearest_min": None,
        }
        for p in ctx.config.profiles
        for c in ctx.config.categories
        for i in range(60)
    ]
    pd.DataFrame(rows).astype({"count": "int32", "nearest_min": float}).to_parquet(
        cdir / count.ACCESS
    )
    now = datetime.now(UTC)
    for name in (validate.STAGE, count.STAGE, score.STAGE):
        write_manifest(
            Manifest(
                stage=name,
                run_id=RUN_ID,
                status="ok",
                started_at=now,
                finished_at=now,
                runtime_s=0,
                peak_rss_mb=0,
            ),
            ctx.stage_dir(name),
        )
    return ctx


def _fake_matrix(request: httpx.Request) -> httpx.Response:
    """Straight-line travel times at the requested speed."""
    body = json.loads(request.content)
    opts = next(iter(body["costing_options"].values()))
    speed = opts["walking_speed"] / 3.6

    def xy(locations: list[dict]) -> np.ndarray:
        x, y = _to_metric.transform([p["lon"] for p in locations], [p["lat"] for p in locations])
        return np.column_stack([x, y])

    s, t = xy(body["sources"]), xy(body["targets"])
    d = np.linalg.norm(s[:, None, :] - t[None, :, :], axis=2)
    return httpx.Response(200, json={"sources_to_targets": {"durations": (d / speed).tolist()}})


def test_recommend_stage_end_to_end(stage_ctx: RunContext) -> None:
    with respx.mock(base_url="http://valhalla.test") as router:
        router.post("/sources_to_targets").mock(side_effect=_fake_matrix)
        manifest = stage.run(stage_ctx)
    assert manifest.status == "ok"
    out = stage_ctx.stage_dir(stage.STAGE)
    cand = gpd.read_parquet(out / stage.CANDIDATES)
    report = json.loads((out / stage.REPORT).read_text(encoding="utf-8"))
    # land use: candidates in the forest corner are dropped, the park is not excluded
    assert report["candidates"]["excluded_landuse"] > 0
    forest = shapely.box(X0 - 10, Y0 - 10, X0 + 300, Y0 + 300)
    assert not shapely.contains_xy(forest, cand.geometry.x, cand.geometry.y).any()

    recs = gpd.read_parquet(out / stage.RECOMMENDATIONS)
    rc = pd.read_parquet(out / stage.REC_CATCHMENTS)
    # data contract (docs/data_contract.md, recommend/ files)
    assert list(recs.columns) == [*stage.REC_COLUMNS, "point_geom", "geometry"]
    assert list(rc.columns) == ["candidate_id", "profile_id", "cell_id", "time_s"]
    assert set(recs["profile_id"]) == {"walking_339", "walking_500"}
    assert recs.groupby(["category", "profile_id"])["rank"].max().le(3).all()
    assert recs.geometry.area.between(9_950, 10_050).all()  # 100 m zone (3035 → 25832)
    assert recs.geometry.contains(gpd.GeoSeries(recs["point_geom"], crs=CRS)).all()

    # brute force: catchment = cells within speed × budget of the candidate centre
    cells = gpd.read_parquet(stage_ctx.stage_dir(validate.STAGE) / "cells.parquet")
    o = np.column_stack([cells["origin_geom"].x, cells["origin_geom"].y])
    c = np.column_stack([cand.geometry.x, cand.geometry.y])
    access = pd.read_parquet(stage_ctx.stage_dir(count.STAGE) / count.ACCESS)
    for pid, profile in stage_ctx.config.profiles.items():
        reach = profile.speed_kmh / 3.6 * 900
        cover = np.linalg.norm(c[:, None] - o[None], axis=2) <= reach
        for cat in stage_ctx.config.categories:
            counts = (
                access[(access["profile_id"] == pid) & (access["category"] == cat.id)]
                .set_index("cell_id")["count"]
                .reindex(cells["cell_id"])
                .to_numpy()
            )
            # candidates far from any deficit cell are not routed; they cannot gain anything
            expected = _naive(cover, cells["population"].to_numpy(), counts, cat.k, 3, 1)
            got = recs[(recs["profile_id"] == pid) & (recs["category"] == cat.id)]
            assert got["candidate_id"].tolist() == [
                cand["candidate_id"].iat[x] for x, _ in expected
            ]
            assert got["population_gain"].tolist() == [g for _, g in expected]
        # stored catchments of the picks are exactly the brute-force catchments
        for cid in recs.loc[recs["profile_id"] == pid, "candidate_id"].unique():
            x = int(np.flatnonzero(cand["candidate_id"] == cid)[0])
            stored = set(rc[(rc["profile_id"] == pid) & (rc["candidate_id"] == cid)]["cell_id"])
            assert stored == set(cells["cell_id"][cover[x]])
    sums = rc.merge(cells[["cell_id", "population"]]).groupby(["candidate_id", "profile_id"])
    merged = recs.merge(sums["population"].sum().rename("pop").reset_index())
    assert (merged["pop"] == merged["catchment_residents"]).all()
    assert report["profiles"]["walking_339"]["requests"] > 0
    # unchanged inputs: the second run is a no-op
    assert stage.run(stage_ctx).finished_at == read_manifest(out).finished_at


def test_recommend_stage_without_profiles_writes_empty_tables(stage_ctx: RunContext) -> None:
    data = yaml.safe_load(stage_ctx.config_path.read_text(encoding="utf-8"))
    data["recommend"]["profiles"] = []
    stage_ctx.config_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    ctx = RunContext(load_config(stage_ctx.config_path), stage_ctx.config_path, RUN_ID)
    with respx.mock(base_url="http://valhalla.test", assert_all_called=False) as router:
        matrix = router.post("/sources_to_targets").mock(side_effect=_fake_matrix)
        stage.run(ctx)
    assert not matrix.called
    out = ctx.stage_dir(stage.STAGE)
    assert len(gpd.read_parquet(out / stage.RECOMMENDATIONS)) == 0
    assert len(pd.read_parquet(out / stage.REC_CATCHMENTS)) == 0


def test_unroutable_candidate_is_dropped(stage_ctx: RunContext) -> None:
    bad: list[dict] = []  # the first target Valhalla sees cannot be snapped

    def flaky(request: httpx.Request) -> httpx.Response:
        targets = json.loads(request.content)["targets"]
        bad[:] = bad or targets[:1]
        if bad[0] in targets:
            return httpx.Response(400, json={"error_code": 171, "error": "No suitable edges"})
        return _fake_matrix(request)

    with respx.mock(base_url="http://valhalla.test") as router:
        router.post("/sources_to_targets").mock(side_effect=flaky)
        stage.run(stage_ctx)
    report = json.loads(
        (stage_ctx.stage_dir(stage.STAGE) / stage.REPORT).read_text(encoding="utf-8")
    )
    dropped = [c for s in report["profiles"].values() for c in s["not_routable"]]
    assert len(dropped) == 2 and len(set(dropped)) == 1  # one per profile
    assert dropped[0].startswith("CRS3035RES100mN")
