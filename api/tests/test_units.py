"""Units: LRU cache, token bucket, trusted-proxy client IP, polyline6, route, settings."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx

from reach_api.cache import LRUCache
from reach_api.ratelimit import RateLimiter, TrustedProxies, client_ip
from reach_api.settings import LiveValhalla, load_config
from reach_api.valhalla import NoRouteError, ValhallaClient, ValhallaError, decode_polyline6

REPO = Path(__file__).resolve().parents[2]


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_lru_drops_least_recently_used() -> None:
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1  # a is now most recent
    c.put("c", 3)
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3
    assert len(c) == 2 and c.hits == 3 and c.misses == 1


def test_token_bucket_refills() -> None:
    clock = Clock()
    rl = RateLimiter(burst=2, per_minute=60, max_clients=10, clock=clock)
    assert rl.allow("x")[0] and rl.allow("x")[0]
    allowed, retry = rl.allow("x")
    assert not allowed and retry == pytest.approx(1.0)
    assert rl.allow("y")[0]  # other clients have their own bucket
    clock.t = 1.0
    assert rl.allow("x")[0]


def test_token_bucket_bounded_clients() -> None:
    clock = Clock()
    rl = RateLimiter(burst=1, per_minute=60, max_clients=2, clock=clock)
    rl.allow("a")
    clock.t = 0.5
    rl.allow("b")
    rl.allow("c")  # evicts the oldest bucket (a)
    assert set(rl._buckets) == {"b", "c"}


def test_client_ip_trusts_only_proxies() -> None:
    proxies = TrustedProxies(["localhost"], resolve_interval_s=30)
    # Caddy appends the address it saw; earlier entries can be forged by the client.
    assert client_ip("127.0.0.1", "6.6.6.6, 9.9.9.9", proxies) == "9.9.9.9"
    assert client_ip("172.18.0.9", "9.9.9.9", proxies) == "172.18.0.9"
    assert client_ip("127.0.0.1", None, proxies) == "127.0.0.1"
    assert client_ip(None, "9.9.9.9", proxies) == "unknown"


def test_trusted_proxies_reresolve_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    clock, lookups = Clock(), []

    def fake(host: str, port: None) -> list:
        lookups.append(host)
        return [(None, None, None, None, ("10.0.0.2", 0))]

    monkeypatch.setattr("reach_api.ratelimit.getaddrinfo", fake)
    proxies = TrustedProxies(["caddy"], resolve_interval_s=30, clock=clock)
    assert proxies.is_trusted("10.0.0.2")
    assert not proxies.is_trusted("10.0.0.3") and len(lookups) == 1
    clock.t = 31
    assert not proxies.is_trusted("10.0.0.3") and len(lookups) == 2


def test_decode_polyline6_recorded_route(rec: dict) -> None:
    coords = decode_polyline6(rec["route"]["trip"]["legs"][0]["shape"])
    summary = rec["route"]["trip"]["summary"]
    lons, lats = [c[0] for c in coords], [c[1] for c in coords]
    assert min(lons) == pytest.approx(summary["min_lon"], abs=1e-6)
    assert max(lats) == pytest.approx(summary["max_lat"], abs=1e-6)


@pytest.mark.parametrize("name", ["config.yaml", "test_clip.yaml"])
def test_load_config(name: str) -> None:
    cfg = load_config(REPO / "config" / name)
    assert cfg.api.cors_origins == ["http://localhost:5173"]
    assert cfg.api.rate_limit.burst == 10


def test_load_config_rejects_bad_api_section(tmp_path: Path) -> None:
    text = (REPO / "config" / "config.yaml").read_text().replace("burst: 10", "burst: 0")
    (tmp_path / "c.yaml").write_text(text)
    with pytest.raises(ValueError, match="burst"):
        load_config(tmp_path / "c.yaml")


async def test_concurrent_misses_share_one_computation() -> None:
    cache, calls = LRUCache(4), []

    async def compute() -> str:
        calls.append(1)
        await asyncio.sleep(0.01)
        return "body"

    results = await asyncio.gather(*(cache.get_or_compute("k", compute) for _ in range(3)))
    assert len(calls) == 1
    assert sorted(built for _, built in results) == [False, False, True]
    assert await cache.get_or_compute("k", compute) == ("body", False)


async def test_failed_computation_is_shared_and_not_cached() -> None:
    cache = LRUCache(4)

    async def fail() -> str:
        await asyncio.sleep(0.01)
        raise ValhallaError("down")

    results = await asyncio.gather(
        *(cache.get_or_compute("k", fail) for _ in range(2)), return_exceptions=True
    )
    assert all(isinstance(r, ValhallaError) for r in results)
    assert cache.get("k") is None


CFG = LiveValhalla(concurrency=1, timeout_s=1, retries=1, backoff_s=0)
URL = "http://valhalla.test"


async def test_route_from_recorded_answer(rec: dict) -> None:
    with respx.mock(base_url=URL) as router:
        route = router.post("/route").respond(json=rec["route"])
        client = ValhallaClient(URL, CFG)
        feature = await client.route((9.0568, 48.5204), (9.0506, 48.5193), "pedestrian", {})
        await client.aclose()
    sent = json.loads(route.calls.last.request.content)
    assert sent["directions_type"] == "none" and sent["costing"] == "pedestrian"
    summary = rec["route"]["trip"]["summary"]
    assert feature["properties"]["time_s"] == summary["time"]
    assert feature["geometry"]["type"] == "LineString"


async def test_route_errors() -> None:
    with respx.mock(base_url=URL) as router:
        router.post("/route").respond(400, json={"error_code": 171})
        client = ValhallaClient(URL, CFG)
        with pytest.raises(NoRouteError):
            await client.route((0, 0), (0, 0), "pedestrian", {})
        route = router.post("/route").mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(ValhallaError, match="after 2 attempts"):
            await client.route((0, 0), (0, 0), "pedestrian", {})
        await client.aclose()
    assert route.call_count == 3  # the 400 once (no retry), then 2 attempts
