"""Housing potential: candidate cells and the housing stage on a synthetic run."""

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

from reach_pipeline import housing
from reach_pipeline import recommend as rec
from reach_pipeline.config import load_config
from reach_pipeline.context import RunContext
from reach_pipeline.manifest import Manifest, read_manifest, write_manifest
from reach_pipeline.stages import acquire, count, score, tiles, validate
from reach_pipeline.stages import housing as stage

REPO = Path(__file__).resolve().parents[2]
CRS = "EPSG:25832"
X0, Y0 = 503_000.0, 5_373_000.0
RUN_ID = "20261116T030000Z"
_to_metric = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
AREA = shapely.box(X0, Y0, X0 + 700, Y0 + 500)


def _districts() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"district_id": ["west"]},
        geometry=[shapely.box(X0 - 100, Y0 - 100, X0 + 350, Y0 + 700)],
        crs=CRS,
    )


def test_candidate_cells_drop_populated_and_excluded() -> None:
    grid = rec.candidate_grid(AREA, 100)
    populated = grid["candidate_id"].to_numpy()[:5]
    forest = gpd.GeoSeries([grid["zone_geom"].iat[10].buffer(-10)], crs=CRS)
    out, stats = housing.candidate_cells(AREA, populated, forest, _districts())
    ids = set(out["cell_id"])
    assert not ids & set(populated)
    assert grid["candidate_id"].iat[10] not in ids
    assert stats == {
        "grid_in_area": len(grid),
        "populated": 5,
        "excluded_landuse": 1,
        "kept": len(grid) - 6,
    }
    assert out["cell_id"].is_unique and out["cell_id"].is_monotonic_increasing
    # the centre decides the district; cells east of the district polygon have none
    west = out["origin_geom"].x < X0 + 350
    assert out.loc[west, "district_id"].eq("west").all()
    assert out.loc[~west, "district_id"].isna().all()
    assert out.geometry.geom_type.eq("Polygon").all() and out.crs == CRS


def test_candidate_cells_empty_when_everything_is_populated() -> None:
    grid = rec.candidate_grid(AREA, 100)
    out, stats = housing.candidate_cells(
        AREA, grid["candidate_id"].to_numpy(), gpd.GeoSeries([], crs=CRS), _districts()
    )
    assert out.empty and stats["kept"] == 0
    assert list(out.columns[:2]) == housing.COLUMNS


@pytest.fixture
def stage_ctx(tmp_path: Path) -> RunContext:
    """Synthetic run: urban boundary = AREA, 6 populated cells, 24 facilities in two
    categories around it; validate, count and score manifests ok. No land-use exclusions."""
    data = yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))
    data["data_dir"] = str(tmp_path / "data")
    data["profiles"] = {k: data["profiles"][k] for k in ("walking_339", "walking_500")}
    data["validation"]["results"]["monotonic"] = []
    data["recommend"].update(
        profiles=[], profile_overrides={}, exclude_tags=[], exclude_protect_classes=[]
    )
    data["housing"].update(profiles=["walking_339"], edge_buffer_m=0, exclude_tags=[])
    data["count"]["block_size_m"] = 300
    data["valhalla"].update(url="http://valhalla.test", backoff_s=0, max_matrix_pairs=500)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    vjson = json.dumps({"thor": {"source_to_target_algorithm": "costmatrix"}})
    (tmp_path / "valhalla.json").write_text(vjson, encoding="utf-8")
    ctx = RunContext(config=load_config(cfg_path), config_path=cfg_path, run_id=RUN_ID)
    tiles.effective_config(ctx).parent.mkdir(parents=True)
    tiles.effective_config(ctx).write_text(vjson, encoding="utf-8")

    vdir = ctx.stage_dir(validate.STAGE)
    vdir.mkdir(parents=True)
    grid = rec.candidate_grid(AREA, 100)
    pop = grid.iloc[:6]
    gpd.GeoDataFrame(
        {
            "cell_id": pop["candidate_id"].to_numpy(),
            "population": 10,
            "district_id": "west",
            "origin_geom": gpd.GeoSeries(pop.geometry.values, crs=CRS),
        },
        geometry=gpd.GeoSeries(pop["zone_geom"].values, crs=CRS),
        crs=CRS,
    ).to_parquet(vdir / "cells.parquet")
    # Zensus CSV: the six scored cells plus one populated cell outside the scoring scope (not in
    # cells.parquet, e.g. a neighbouring municipality): it must not become a candidate either
    outside = grid["candidate_id"].iat[6]
    ids = [*pop["candidate_id"], outside]
    csv = acquire.raw_path(ctx.raw_dir, "zensus", cfg_members(ctx))
    csv.parent.mkdir(parents=True)
    rows = ["GITTER_ID_100m;x_mp_100m;y_mp_100m;Einwohner"]
    for cid in ids:
        n, e = cid.removeprefix("CRS3035RES100mN").split("E")
        rows.append(f"{cid};{int(e) + 50};{int(n) + 50};7")
    csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    _districts().to_parquet(vdir / "districts.parquet")
    gpd.GeoDataFrame({"part_id": [1], "name": [None]}, geometry=[AREA], crs=CRS).to_parquet(
        vdir / "urban_boundary.parquet"
    )
    rng = np.random.default_rng(5)
    xy = rng.uniform([X0 - 600, Y0 - 600], [X0 + 1300, Y0 + 1100], size=(24, 2))
    pts = gpd.GeoSeries(shapely.points(xy), crs=CRS)
    ids = [f"n{i}" for i in range(24)]
    gpd.GeoDataFrame(
        {
            "facility_id": ids,
            "category": ["grocery"] * 12 + ["pharmacy"] * 12,
            "name": None,
        },
        geometry=pts,
        crs=CRS,
    ).to_parquet(vdir / "facilities.parquet")
    gpd.GeoDataFrame(
        {"facility_id": ids, "point_id": range(24), "kind": "node"}, geometry=pts, crs=CRS
    ).to_parquet(vdir / "facility_points.parquet")
    gpd.GeoDataFrame(
        {"stop_id": pd.Series(dtype=object), "name": pd.Series(dtype=object)},
        geometry=gpd.GeoSeries([], crs=CRS),
        crs=CRS,
    ).to_parquet(vdir / "stops.parquet")
    (vdir / validate.REPORT_JSON).write_text("{}", encoding="utf-8")
    (vdir / validate.ROUTING_PBF).write_bytes(b"pbf")
    now = datetime.now(UTC)
    for name in (validate.STAGE, tiles.STAGE, count.STAGE, score.STAGE):
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


def cfg_members(ctx: RunContext) -> str:
    return ctx.config.sources.zensus.members[0]


def _fake_matrix(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    opts = next(iter(body["costing_options"].values()))
    speed = opts["walking_speed"] / 3.6

    def xy(locations: list[dict]) -> np.ndarray:
        x, y = _to_metric.transform([p["lon"] for p in locations], [p["lat"] for p in locations])
        return np.column_stack([x, y])

    s, t = xy(body["sources"]), xy(body["targets"])
    d = np.linalg.norm(s[:, None, :] - t[None, :, :], axis=2)
    return httpx.Response(200, json={"sources_to_targets": {"durations": (d / speed).tolist()}})


def test_housing_stage_matches_brute_force(stage_ctx: RunContext) -> None:
    with respx.mock(base_url="http://valhalla.test") as router:
        router.post("/sources_to_targets").mock(side_effect=_fake_matrix)
        manifest = stage.run(stage_ctx)
    assert manifest.status == "ok"
    out = stage_ctx.stage_dir(stage.STAGE)
    cells = gpd.read_parquet(out / stage.CELLS)
    counts = pd.read_parquet(out / stage.COUNTS)
    reachable = pd.read_parquet(out / stage.REACHABLE)
    report = json.loads((out / stage.REPORT).read_text(encoding="utf-8"))
    populated = set(
        gpd.read_parquet(stage_ctx.stage_dir(validate.STAGE) / "cells.parquet")["cell_id"]
    )
    # unpopulated cells only; one row per cell x configured category
    assert len(cells) > 0 and not set(cells["cell_id"]) & populated
    # a populated cell outside the scoring scope is no candidate
    assert report["candidates"]["populated"] == 7
    grid_ids = rec.candidate_grid(AREA, 100)["candidate_id"].tolist()
    assert grid_ids[6] not in set(cells["cell_id"])
    assert len(counts) == len(cells) * len(stage_ctx.config.categories)
    assert set(counts["profile_id"]) == {"walking_339"}
    # brute force: straight-line time = distance / speed, budget 15 min
    cfg = stage_ctx.config
    reach_m = cfg.profiles["walking_339"].speed_kmh / 3.6 * cfg.time_budgets_min.facilities * 60
    fac = gpd.read_parquet(stage_ctx.stage_dir(validate.STAGE) / "facilities.parquet")
    origin = cells.set_geometry("origin_geom").geometry
    for cell_id, o in zip(cells["cell_id"], origin, strict=True):
        near = fac[fac.geometry.distance(o) <= reach_m]
        for cat in ("grocery", "pharmacy"):
            got = counts[(counts["cell_id"] == cell_id) & (counts["category"] == cat)]
            assert int(got["count"].iat[0]) == int((near["category"] == cat).sum())
    pairs = reachable.groupby("cell_id").size()
    expected = sum(int((fac.geometry.distance(o) <= reach_m).sum()) for o in origin)
    assert int(pairs.sum()) == expected
    assert report["candidates"]["kept"] == len(cells)
    assert report["profiles"]["walking_339"]["requests"] > 0
    # unchanged inputs: the second run is a no-op
    assert stage.run(stage_ctx).finished_at == read_manifest(out).finished_at


def test_housing_stage_without_profiles_writes_empty_tables(stage_ctx: RunContext) -> None:
    data = yaml.safe_load(stage_ctx.config_path.read_text(encoding="utf-8"))
    data["housing"]["profiles"] = []
    stage_ctx.config_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    ctx = RunContext(load_config(stage_ctx.config_path), stage_ctx.config_path, RUN_ID)
    with respx.mock(base_url="http://valhalla.test", assert_all_called=False) as router:
        matrix = router.post("/sources_to_targets").mock(side_effect=_fake_matrix)
        stage.run(ctx)
    assert not matrix.called
    out = ctx.stage_dir(stage.STAGE)
    assert len(gpd.read_parquet(out / stage.CELLS)) == 0
    assert len(pd.read_parquet(out / stage.COUNTS)) == 0
    assert len(pd.read_parquet(out / stage.REACHABLE)) == 0
