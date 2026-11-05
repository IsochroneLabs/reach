"""Units: LRU cache, token bucket, trusted-proxy client IP, polyline6, settings."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from reach_api.cache import LRUCache
from reach_api.ratelimit import RateLimiter, TrustedProxies, client_ip
from reach_api.settings import LiveValhalla, load_config
from reach_api.valhalla import ValhallaClient, ValhallaError, decode_polyline6

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
    assert cfg.api.isochrone.contours_min == [5, 10, 15]
    # Same prefilter reach as the pipeline: 850 m for walking 3.39 km/h in 15 min.
    assert cfg.prefilter_reach_m("walking_339", 3.39, 15) == pytest.approx(847.5)


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


async def test_matrix_too_large_on_both_axes() -> None:
    cfg = LiveValhalla(concurrency=1, timeout_s=1, retries=0, backoff_s=0)
    client = ValhallaClient("http://valhalla.test", cfg, max_matrix_pairs=2)
    with pytest.raises(ValhallaError, match="both axes"):
        await client.matrix([(9.0, 48.5)] * 3, [(9.0, 48.5)] * 3, "pedestrian", {})
    await client.aclose()
