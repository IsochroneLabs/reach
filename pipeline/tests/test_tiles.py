"""tiles check (flag file from the build fingerprint) and tiles verify (mocked Valhalla)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pytest
import respx
import shapely
import yaml

from reach_pipeline.config import load_config
from reach_pipeline.context import RunContext
from reach_pipeline.errors import ExternalError, StageValidationError
from reach_pipeline.manifest import Manifest, read_manifest, write_manifest
from reach_pipeline.stages import tiles, validate

REPO = Path(__file__).resolve().parents[2]
URL = "http://valhalla.test"
RUN_ID = "20261116T030000Z"
MTIME = 1_793_658_362


@pytest.fixture
def ctx(tmp_path: Path) -> RunContext:
    data = yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))
    data["data_dir"] = str(tmp_path / "data")
    data["valhalla"].update(url=URL, retries=0)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    (tmp_path / "valhalla.json").write_text('{"mjolnir": {}}', encoding="utf-8")
    ctx = RunContext(config=load_config(cfg_path), config_path=cfg_path, run_id=RUN_ID)
    vdir = ctx.stage_dir(validate.STAGE)
    vdir.mkdir(parents=True)
    (vdir / validate.ROUTING_PBF).write_bytes(b"pbf v1")
    area = gpd.GeoSeries([shapely.box(9.0, 48.5, 9.1, 48.55)], crs="EPSG:4326").to_crs(
        validate.METRIC_CRS
    )
    gpd.GeoDataFrame(geometry=area).to_parquet(vdir / "routing_area.parquet")
    now = datetime.now(UTC)
    write_manifest(
        Manifest(
            stage=validate.STAGE,
            run_id=RUN_ID,
            status="ok",
            started_at=now,
            finished_at=now,
            runtime_s=0,
            peak_rss_mb=0,
        ),
        vdir,
    )
    return ctx


def _built(ctx: RunContext) -> None:
    """Pretend `make refresh` built the tiles from the current inputs."""
    vdir = tiles.valhalla_dir(ctx)
    vdir.mkdir(parents=True, exist_ok=True)
    tar = vdir / tiles.TILES_TAR
    tar.write_bytes(b"tar")
    os.utime(tar, (MTIME, MTIME))
    pbf = ctx.stage_dir(validate.STAGE) / validate.ROUTING_PBF
    fp = tiles.fingerprint(pbf, tiles.valhalla_config(ctx), ctx.config.tiles.elevation)
    (vdir / tiles.SOURCE_FILE).write_text(fp + "\n", encoding="utf-8")


def test_check_flags_missing_tiles(ctx: RunContext) -> None:
    assert tiles.check(ctx) is True
    flag = (ctx.stage_dir(tiles.STAGE) / tiles.FLAG).read_text(encoding="utf-8")
    values = dict(line.split("=", 1) for line in flag.splitlines())
    assert values["ELEVATION"] == "true"
    assert values["PBF"].endswith(validate.ROUTING_PBF)
    lon0, lat0, lon1, lat1 = map(float, values["BBOX"].split(","))
    assert lon0 <= 9.0 and lat0 <= 48.5 and lon1 >= 9.1 and lat1 >= 48.55


def test_check_clears_flag_when_up_to_date(ctx: RunContext) -> None:
    tiles.check(ctx)
    _built(ctx)
    assert tiles.check(ctx) is False
    assert not (ctx.stage_dir(tiles.STAGE) / tiles.FLAG).exists()


@pytest.mark.parametrize(
    "change",
    ["pbf", "valhalla.json"],
)
def test_check_flags_changed_inputs(ctx: RunContext, change: str) -> None:
    _built(ctx)
    if change == "pbf":
        (ctx.stage_dir(validate.STAGE) / validate.ROUTING_PBF).write_bytes(b"pbf v2")
    else:
        tiles.valhalla_config(ctx).write_text('{"mjolnir": {"x": 1}}', encoding="utf-8")
    assert tiles.check(ctx) is True


def _mock(router: respx.Router, length_km: float = 0.506, grade: float = 11.7) -> None:
    router.get("/status").respond(json={"version": "3.9.1", "tileset_last_modified": MTIME})
    router.post("/route").respond(
        json={"trip": {"summary": {"length": length_km, "time": 463.0}, "legs": [{"shape": "abc"}]}}
    )
    router.post("/trace_attributes").respond(
        json={
            "edges": [{"weighted_grade": grade, "max_upward_grade": 12, "max_downward_grade": -5}]
        }
    )


def test_verify_writes_manifest(ctx: RunContext) -> None:
    _built(ctx)
    with respx.mock(base_url=URL) as router:
        _mock(router)
        manifest = tiles.run(ctx)
    assert manifest.status == "ok"
    report = json.loads((ctx.stage_dir(tiles.STAGE) / tiles.VERIFY_JSON).read_text("utf-8"))
    assert report["tiles_match_run"] and report["serves_tiles_of_this_config"]
    assert report["max_abs_weighted_grade"] == 11.7
    assert read_manifest(ctx.stage_dir(tiles.STAGE)).status == "ok"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"length_km": 0.2}, "golden route length"),  # shorter than the straight line
        ({"length_km": 5.0}, "golden route length"),  # implausible detour
        ({"grade": 0.0}, "carries no grades"),
    ],
)
def test_verify_rejects_implausible_graph(ctx: RunContext, kwargs: dict, message: str) -> None:
    _built(ctx)
    with respx.mock(base_url=URL) as router:
        _mock(router, **kwargs)
        with pytest.raises(StageValidationError, match=message):
            tiles.run(ctx)
    assert read_manifest(ctx.stage_dir(tiles.STAGE)) is None


def test_verify_detects_other_tile_set(ctx: RunContext) -> None:
    _built(ctx)
    os.utime(tiles.valhalla_dir(ctx) / tiles.TILES_TAR, (MTIME + 60, MTIME + 60))
    with respx.mock(base_url=URL) as router:
        _mock(router)
        with pytest.raises(StageValidationError, match="serves another tile set"):
            tiles.run(ctx)


def test_verify_fails_clearly_without_valhalla(ctx: RunContext) -> None:
    with respx.mock(base_url=URL) as router:
        router.get("/status").respond(503)
        with pytest.raises(ExternalError, match="make up"):
            tiles.run(ctx)
