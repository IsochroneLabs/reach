"""acquire with mocked HTTP: downloads, provenance, skip unchanged (md5, 304, SHA-256), retries."""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx
import yaml

from reach_pipeline.config import load_config
from reach_pipeline.context import RunContext
from reach_pipeline.errors import ExternalError, StageValidationError
from reach_pipeline.manifest import read_manifest
from reach_pipeline.stages import acquire

REPO = Path(__file__).resolve().parents[2]
PBF = b"fake pbf bytes"


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def cfg_path(tmp_path: Path) -> Path:
    data = yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))
    data["data_dir"] = str(tmp_path / "data")
    data["download"] = {"retries": 2, "backoff_s": 0, "timeout_s": 5}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _ctx(cfg_path: Path, run_id: str) -> RunContext:
    return RunContext(config=load_config(cfg_path), config_path=cfg_path, run_id=run_id)


@pytest.fixture
def server(cfg_path: Path):
    cfg = load_config(cfg_path).sources
    gtfs = _zip({m: f"{m} data".encode() for m in cfg.gtfs.members} | {"shapes.txt": b"x"})
    zensus = _zip(
        {m: b"GITTER_ID_100m;x_mp_100m;y_mp_100m;Einwohner\n" for m in cfg.zensus.members}
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(cfg.osm.md5_url).respond(text=f"{hashlib.md5(PBF).hexdigest()}  x.osm.pbf\n")
        router.get(cfg.osm.url).respond(content=PBF)

        def gtfs_route(request: httpx.Request) -> httpx.Response:
            if request.headers.get("if-modified-since") == "Sun, 11 Oct 2026 21:18:26 GMT":
                return httpx.Response(304)
            return httpx.Response(
                200, content=gtfs, headers={"Last-Modified": "Sun, 11 Oct 2026 21:18:26 GMT"}
            )

        router.get(cfg.gtfs.url).mock(side_effect=gtfs_route)
        router.get(cfg.zensus.url).respond(content=zensus)  # no caching headers
        yield router, cfg


def test_first_run_downloads_and_unpacks(cfg_path: Path, server) -> None:
    manifest = acquire.run(_ctx(cfg_path, "20261102T120000Z"))
    raw = cfg_path.parent / "data" / "raw" / "20261102T120000Z"
    assert (raw / "osm" / "tuebingen-regbez-latest.osm.pbf").read_bytes() == PBF
    assert (raw / "gtfs" / "stops.txt").read_text() == "stops.txt data"
    assert not (raw / "gtfs" / "shapes.txt").exists()
    assert (raw / "zensus" / "Zensus2022_Bevoelkerungszahl_100m-Gitter.csv").exists()

    prov = pd.read_parquet(
        cfg_path.parent / "data/runs/20261102T120000Z/acquire/data_sources.parquet"
    )
    assert list(prov["source"]) == ["osm", "gtfs", "zensus"]
    assert prov.loc[0, "checksum"] == hashlib.sha256(PBF).hexdigest()
    assert prov.loc[0, "licence"] == "ODbL 1.0"
    assert not prov["reused"].any()
    assert manifest.status == "ok" and "unchanged (linked): none" in manifest.message


def test_second_run_links_unchanged_files(cfg_path: Path, server) -> None:
    router, cfg = server
    acquire.run(_ctx(cfg_path, "20261102T120000Z"))
    calls_before = router.routes[1].call_count  # the PBF itself
    manifest = acquire.run(_ctx(cfg_path, "20261109T120000Z"))

    assert router.routes[1].call_count == calls_before  # md5 unchanged: no PBF download
    assert "['osm', 'gtfs', 'zensus']" in manifest.message  # md5, 304, same SHA-256
    old = cfg_path.parent / "data" / "raw" / "20261102T120000Z"
    new = cfg_path.parent / "data" / "raw" / "20261109T120000Z"
    for rel in [
        "osm/tuebingen-regbez-latest.osm.pbf",
        "gtfs/naldo.zip",
        "gtfs/stop_times.txt",
        "zensus/Zensus2022_Bevoelkerungszahl_100m-Gitter.csv",
    ]:
        assert os.path.samefile(old / rel, new / rel), rel
    prov = pd.read_parquet(
        cfg_path.parent / "data/runs/20261109T120000Z/acquire/data_sources.parquet"
    )
    assert prov["reused"].all() and (prov["run_id"] == "20261109T120000Z").all()


def test_rerun_same_run_is_noop(cfg_path: Path, server) -> None:
    router, _ = server
    first = acquire.run(_ctx(cfg_path, "20261102T120000Z"))
    calls = sum(r.call_count for r in router.routes)
    assert acquire.run(_ctx(cfg_path, "20261102T120000Z")) == first
    assert sum(r.call_count for r in router.routes) == calls
    assert read_manifest(cfg_path.parent / "data/runs/20261102T120000Z/acquire") == first


def test_retries_on_5xx_then_succeeds(cfg_path: Path, server) -> None:
    router, cfg = server
    router.get(cfg.zensus.url).mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectTimeout("slow"),
            httpx.Response(200, content=_zip({cfg.zensus.members[0]: b"a"})),
        ]
    )
    assert acquire.run(_ctx(cfg_path, "20261102T120000Z")).status == "ok"


def test_gives_up_after_retries(cfg_path: Path, server) -> None:
    router, cfg = server
    router.get(cfg.gtfs.url).respond(500)
    with pytest.raises(ExternalError, match="failed after 3 attempts"):
        acquire.run(_ctx(cfg_path, "20261102T120000Z"))


def test_client_error_is_not_retried(cfg_path: Path, server) -> None:
    router, cfg = server
    route = router.get(cfg.gtfs.url).respond(404)
    with pytest.raises(ExternalError, match="HTTP 404"):
        acquire.run(_ctx(cfg_path, "20261102T120000Z"))
    assert route.call_count == 1


def test_md5_mismatch_fails(cfg_path: Path, server) -> None:
    router, cfg = server
    router.get(cfg.osm.url).respond(content=b"truncated")
    with pytest.raises(ExternalError, match="md5 of the download"):
        acquire.run(_ctx(cfg_path, "20261102T120000Z"))


def test_missing_zip_member_fails(cfg_path: Path, server) -> None:
    router, cfg = server
    router.get(cfg.zensus.url).respond(content=_zip({"other.csv": b"x"}))
    with pytest.raises(StageValidationError, match="missing members"):
        acquire.run(_ctx(cfg_path, "20261102T120000Z"))
