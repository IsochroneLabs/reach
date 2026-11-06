"""Valhalla client: recorded matrix replayed with respx, target splitting, retries, options."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import numpy as np
import pytest
import respx

from reach_pipeline.config import Profile, Valhalla
from reach_pipeline.errors import ConfigError, ExternalError
from reach_pipeline.valhalla.client import ValhallaClient, costing_options, resolve_url

FIXTURES = Path(__file__).parent / "fixtures" / "valhalla"
URL = "http://valhalla.test"
CFG = Valhalla(url=URL, concurrency=2, timeout_s=5, retries=2, backoff_s=0, max_matrix_pairs=6)


def _lonlat(locations: list[dict]) -> np.ndarray:
    return np.array([[p["lon"], p["lat"]] for p in locations])


async def test_recorded_matrix_is_parsed() -> None:
    rec = json.loads((FIXTURES / "matrix_wheelchair_clip.json").read_text(encoding="utf-8"))
    req = rec["request"]
    with respx.mock(base_url=URL) as router:
        route = router.post("/sources_to_targets").respond(json=rec["response"])
        async with ValhallaClient(CFG) as client:
            times = await client.matrix(
                _lonlat(req["sources"]),
                _lonlat(req["targets"]),
                req["costing"],
                req["costing_options"],
            )
    sent = json.loads(route.calls.last.request.content)
    assert sent == req  # compact output, costing options and locations as recorded
    assert times.shape == (2, 3)
    assert np.isnan(times[:, 0]).all()  # Schloss: unreachable by wheelchair (null)
    np.testing.assert_array_equal(times[:, 1:], [[176, 229], [357, 753]])


async def test_large_target_sets_are_split_in_order() -> None:
    sources = np.zeros((2, 2))
    targets = np.column_stack([np.arange(7.0), np.zeros(7)])  # 2 × 7 = 14 pairs > 6

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        lons = [t["lon"] for t in body["targets"]]
        return httpx.Response(200, json={"sources_to_targets": {"durations": [lons, lons]}})

    with respx.mock(base_url=URL) as router:
        route = router.post("/sources_to_targets").mock(side_effect=answer)
        async with ValhallaClient(CFG) as client:
            times = await client.matrix(sources, targets, "pedestrian", {})
    assert route.call_count == 3  # 3 targets per request (6 pairs / 2 sources)
    np.testing.assert_array_equal(times, [np.arange(7.0)] * 2)


async def test_too_many_sources_is_a_config_error() -> None:
    async with ValhallaClient(CFG) as client:
        with pytest.raises(ConfigError, match="max_matrix_pairs"):
            await client.matrix(np.zeros((7, 2)), np.zeros((1, 2)), "pedestrian", {})


async def test_retries_on_5xx_then_succeeds() -> None:
    with respx.mock(base_url=URL) as router:
        route = router.get("/status").mock(
            side_effect=[
                httpx.Response(503),
                httpx.ConnectError("down"),
                httpx.Response(200, json={}),
            ]
        )
        async with ValhallaClient(CFG) as client:
            assert await client.get("status") == {}
    assert route.call_count == 3


async def test_gives_up_after_retries() -> None:
    with respx.mock(base_url=URL) as router:
        router.get("/status").respond(502)
        async with ValhallaClient(CFG) as client:
            with pytest.raises(ExternalError, match="failed after 3 attempts"):
                await client.get("status")


async def test_bad_request_is_not_retried() -> None:
    with respx.mock(base_url=URL) as router:
        route = router.post("/sources_to_targets").respond(
            400, json={"error": "No suitable edges near location"}
        )
        async with ValhallaClient(CFG) as client:
            with pytest.raises(ExternalError, match="No suitable edges"):
                await client.matrix(np.zeros((1, 2)), np.zeros((1, 2)), "pedestrian", {})
    assert route.call_count == 1


def test_costing_options_add_the_speed() -> None:
    walk = Profile(
        costing="pedestrian",
        speed_kmh=3.39,
        costing_options={"type": "wheelchair"},
        max_speed_factor=1,
        prefilter_margin_m=0,
        transit=True,
    )
    bike = Profile(
        costing="bicycle",
        speed_kmh=15,
        costing_options={"bicycle_type": "Hybrid"},
        max_speed_factor=1,
        prefilter_margin_m=0,
        transit=False,
    )
    assert costing_options(walk) == {"pedestrian": {"type": "wheelchair", "walking_speed": 3.39}}
    assert costing_options(bike) == {"bicycle": {"bicycle_type": "Hybrid", "cycling_speed": 15}}


def test_url_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VALHALLA_URL", raising=False)
    assert resolve_url(CFG) == URL
    monkeypatch.setenv("VALHALLA_URL", "http://valhalla:8002/")
    assert resolve_url(CFG) == "http://valhalla:8002"


async def test_route_times_takes_fastest_point_and_skips_no_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VALHALLA_URL", raising=False)
    import pandas as pd

    from reach_pipeline.config import load_config
    from reach_pipeline.stages import validate_results

    cfg = load_config(Path(__file__).resolve().parents[2] / "config" / "config.yaml")
    cfg = cfg.model_copy(
        update={"valhalla": cfg.valhalla.model_copy(update={"url": "http://valhalla.test"})}
    )
    pairs = pd.DataFrame(
        {
            "cell_id": ["c1", "c2"],
            "profile_id": ["walking_339"] * 2,
            "facility_id": ["park", "shop"],
            "time_s": [500, 300],
        }
    )
    origins = {"c1": (9.05, 48.52), "c2": (9.06, 48.52)}
    points = {"park": [(9.051, 48.52), (9.052, 48.52)], "shop": [(9.061, 48.52)]}

    def answer(request: httpx.Request) -> httpx.Response:
        target = json.loads(request.content)["locations"][1]["lon"]
        if target == 9.061:
            return httpx.Response(400, json={"error_code": 171})
        return httpx.Response(
            200, json={"trip": {"summary": {"time": 510 if target == 9.051 else 498}}}
        )

    with respx.mock(base_url="http://valhalla.test") as router:
        router.post("/route").mock(side_effect=answer)
        times = await validate_results.route_times(cfg, pairs, origins, points)
    assert times == [498.0, None]


async def test_route_times_aborts_on_valhalla_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only 4xx means "no route"; 5xx and timeouts after retries must not look like a clean check.
    import pandas as pd

    from reach_pipeline.config import load_config
    from reach_pipeline.stages import validate_results

    monkeypatch.delenv("VALHALLA_URL", raising=False)
    cfg = load_config(Path(__file__).resolve().parents[2] / "config" / "config.yaml")
    vcfg = cfg.valhalla.model_copy(update={"url": "http://valhalla.test", "retries": 0})
    cfg = cfg.model_copy(update={"valhalla": vcfg})
    pairs = pd.DataFrame(
        {"cell_id": ["c1"], "profile_id": ["walking_339"], "facility_id": ["shop"], "time_s": [300]}
    )
    for failure in (httpx.Response(503, text="busy"), httpx.ReadTimeout("slow")):
        with respx.mock(base_url="http://valhalla.test") as router:
            router.post("/route").mock(side_effect=[failure])
            with pytest.raises(ExternalError, match="failed after 1 attempts"):
                await validate_results.route_times(
                    cfg, pairs, {"c1": (9.05, 48.52)}, {"shop": [(9.06, 48.52)]}
                )


def test_check_routes_reports_known_limitation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    import geopandas as gpd
    import pandas as pd
    import shapely

    from reach_pipeline import results
    from reach_pipeline.config import load_config
    from reach_pipeline.stages import validate_results

    monkeypatch.delenv("VALHALLA_URL", raising=False)
    cfg = load_config(Path(__file__).resolve().parents[2] / "config" / "config.yaml")
    cfg = cfg.model_copy(
        update={"valhalla": cfg.valhalla.model_copy(update={"url": "http://valhalla.test"})}
    )
    gpd.GeoDataFrame(
        {"facility_id": ["f1", "f1", "f2"], "point_id": [0, 1, 0], "kind": "access"},
        geometry=[
            shapely.Point(503000, 5374000),
            shapely.Point(503100, 5374000),
            shapely.Point(503500, 5374200),
        ],
        crs="EPSG:25832",
    ).to_parquet(tmp_path / "facility_points.parquet")
    monkeypatch.setattr(
        validate_results,
        "_paths",
        lambda ctx: {"facility_points": tmp_path / "facility_points.parquet"},
    )
    origins = gpd.GeoDataFrame(
        {"cell_id": ["c1", "c2"]},
        geometry=[shapely.Point(502900, 5374000), shapely.Point(503400, 5374100)],
        crs="EPSG:25832",
    )
    reachable = pd.DataFrame(
        {
            "cell_id": ["c1", "c2", "c1"],
            "profile_id": ["walking_339"] * 3,
            "facility_id": ["f1", "f2", "f2"],
            "time_s": [120, 880, 700],
        }
    )
    t = results.Tables(cells=None, access=None, transit=None, thresholds=None, reachable=reachable)
    ctx = types.SimpleNamespace(config=cfg, run_id="20261105T203945Z")
    with respx.mock(base_url="http://valhalla.test") as router:
        router.post("/route").mock(
            return_value=httpx.Response(200, json={"trip": {"summary": {"time": 905.0}}})
        )
        check, rc = validate_results.check_routes(ctx, t, origins)
    walk = rc["profiles"]["walking_339"]
    assert walk["pairs"] == 3 and walk["no_route"] == 0 and walk["flips"] == 3
    assert check.check == "matrix_vs_route" and check.status == "warn"  # 785 s > 60 s
    md = validate_results._markdown(
        {
            "run_id": "x",
            "status": "ok",
            "generated_at": "now",
            "checks": [],
            "summary": None,
            "samples": [],
            "route_check": rc,
            "runtime_s": 0,
            "peak_rss_mb": 0,
        }
    )
    assert "Known limitation: matrix times vs. /route" in md and "| walking_339 | 3 | 0 |" in md


def test_check_false_negatives_routes_unreached_pairs_within_reach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    import geopandas as gpd
    import pandas as pd
    import shapely

    from reach_pipeline import results
    from reach_pipeline.config import load_config
    from reach_pipeline.stages import validate_results

    monkeypatch.delenv("VALHALLA_URL", raising=False)
    cfg = load_config(Path(__file__).resolve().parents[2] / "config" / "config.yaml")
    cfg = cfg.model_copy(
        update={
            "valhalla": cfg.valhalla.model_copy(update={"url": "http://valhalla.test"}),
            "profiles": {"walking_339": cfg.profiles["walking_339"]},  # reach 847.5 m
        }
    )
    gpd.GeoDataFrame(
        {"facility_id": ["shop", "far"], "point_id": [0, 0], "kind": "node"},
        geometry=[shapely.Point(503600, 5374000), shapely.Point(506000, 5374000)],
        crs="EPSG:25832",
    ).to_parquet(tmp_path / "facility_points.parquet")
    monkeypatch.setattr(
        validate_results,
        "_paths",
        lambda ctx: {"facility_points": tmp_path / "facility_points.parquet"},
    )
    origins = gpd.GeoDataFrame(
        {"cell_id": ["c1", "c2"]},
        geometry=[shapely.Point(503000, 5374000), shapely.Point(503500, 5374000)],
        crs="EPSG:25832",
    )
    # c2 reaches the shop (in reachable); c1 is 600 m away and was not counted
    reachable = pd.DataFrame(
        {"cell_id": ["c2"], "profile_id": ["walking_339"], "facility_id": ["shop"], "time_s": [110]}
    )
    facilities = pd.DataFrame({"facility_id": ["shop", "far"], "category": "grocery"})
    t = results.Tables(
        cells=None,
        access=None,
        transit=None,
        thresholds=None,
        reachable=reachable,
        facilities=facilities,
    )
    ctx = types.SimpleNamespace(config=cfg, run_id="20261106T120000Z")
    with respx.mock(base_url="http://valhalla.test") as router:
        route = router.post("/route").mock(
            return_value=httpx.Response(200, json={"trip": {"summary": {"time": 640.0}}})
        )
        check, detail = validate_results.check_false_negatives(ctx, t, origins)
    assert route.call_count == 1  # only (c1, shop): reachable and out-of-reach pairs are skipped
    assert check.check == "false_negatives" and check.status == "fail"  # 1 of 1 > 2 %
    assert detail["profiles"]["walking_339"]["grocery"]["false_negatives"] == 1
    assert detail["examples"][0] == {
        "profile_id": "walking_339",
        "category": "grocery",
        "cell_id": "c1",
        "facility_id": "shop",
        "distance_m": 600.0,
        "route_s": 640.0,
    }
    md = validate_results._markdown(
        {
            "run_id": "x",
            "status": "fail",
            "generated_at": "now",
            "checks": [],
            "summary": None,
            "samples": [],
            "route_check": None,
            "false_negatives": detail,
            "budget_flips": {
                "warn_above": 0.05,
                "profiles": {
                    "walking_339": {
                        "within_to_beyond": {"routed": 25, "flips": 0, "rate": 0.0},
                        "beyond_to_within": {"routed": 1, "flips": 1, "rate": 1.0},
                    }
                },
            },
            "runtime_s": 0,
            "peak_rss_mb": 0,
        }
    )
    assert "## Missed facilities" in md and "| walking_339 | grocery | 1 | 0 | 1 | 100.0% |" in md
    assert "## Budget flips" in md and "| walking_339 | 0 of 25 (0.0%) | 1 of 1 (100.0%) |" in md
