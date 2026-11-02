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
