"""Shared state of the app (config, database, Valhalla client, caches, rate limit) and the
per-request run context."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from reach_api.cache import LRUCache
from reach_api.db import TRANSIT, Database, Profile
from reach_api.ratelimit import RateLimiter, TrustedProxies, client_ip
from reach_api.settings import Config
from reach_api.valhalla import ValhallaClient


@dataclass
class Deps:
    config: Config
    db: Database
    valhalla: ValhallaClient
    live_cache: LRUCache = field(init=False)
    expansion_cache: LRUCache = field(init=False)
    read_cache: LRUCache = field(init=False)
    limiter: RateLimiter = field(init=False)
    proxies: TrustedProxies = field(init=False)

    def __post_init__(self) -> None:
        api = self.config.api
        self.live_cache = LRUCache(api.cache.live_entries)
        self.expansion_cache = LRUCache(api.cache.expansion_entries)
        self.read_cache = LRUCache(api.cache.read_entries)
        rl = api.rate_limit
        self.limiter = RateLimiter(rl.burst, rl.per_minute, rl.max_clients)
        self.proxies = TrustedProxies(api.trusted_proxies, api.resolve_interval_s)


@dataclass(frozen=True)
class Run:
    """The published run behind `current`, with its profiles and category thresholds."""

    run_id: str
    profiles: dict[str, Profile]
    categories: dict[str, int]  # category -> k
    transit_profiles: frozenset[str]  # profiles with transit supply (methodology §3)

    def profile(self, profile_id: str) -> Profile:
        if profile_id not in self.profiles:
            raise HTTPException(
                422, f"unknown profile {profile_id!r}; known: {sorted(self.profiles)}"
            )
        return self.profiles[profile_id]

    def check_category(self, category: str, profile_id: str) -> None:
        known = [*self.categories, TRANSIT]
        if category not in known:
            raise HTTPException(422, f"unknown category {category!r}; known: {known}")
        if category == TRANSIT and profile_id not in self.transit_profiles:
            raise HTTPException(
                422, f"no transit supply for profile {profile_id!r} (methodology §3)"
            )


def deps(request: Request) -> Deps:
    return request.app.state.deps


async def current_run(d: Deps) -> Run:
    """Run id of `current` (one query per request, so a new publish is visible at once); the
    profiles and categories of a run are cached by its id."""
    run_id = await d.db.run_id()
    if run_id is None:
        raise HTTPException(503, "no published run in the database yet")
    key = ("run", run_id)
    run = d.read_cache.get(key)
    if run is None:
        run = Run(
            run_id,
            await d.db.profiles(),
            await d.db.categories(),
            frozenset(await d.db.transit_profiles()),
        )
        d.read_cache.put(key, run)
    return run


async def rate_limited(request: Request) -> None:
    """Dependency of the live endpoints: one token per request and client IP. Async on
    purpose: it runs on the event loop, so the limiter's state is never shared between
    threads (a sync dependency would run in the threadpool)."""
    d = deps(request)
    peer = request.client.host if request.client else None
    ip = client_ip(peer, request.headers.get("x-forwarded-for"), d.proxies)
    allowed, retry_after = d.limiter.allow(ip)
    if not allowed:
        raise HTTPException(
            429, "too many requests", headers={"Retry-After": str(max(1, round(retry_after)))}
        )
