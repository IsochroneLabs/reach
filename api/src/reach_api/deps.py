"""Shared state of the app (config, database, Valhalla client, cache, rate limit)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request

from reach_api.cache import LRUCache
from reach_api.db import Database
from reach_api.otp import OtpClient
from reach_api.ratelimit import RateLimiter, TrustedProxies, client_ip
from reach_api.settings import Config
from reach_api.store import ModelStore
from reach_api.valhalla import ValhallaClient


@dataclass
class Deps:
    config: Config
    db: Database
    valhalla: ValhallaClient
    otp: OtpClient | None = None
    build_sha: str = "dev"
    label_names: dict[str, dict[str, str]] = field(default_factory=dict)
    personas: dict[str, Any] = field(default_factory=dict)
    # Serialized fit answers, keyed by run and weight vector only (AGENTS.md rule 9).
    fit_cache: LRUCache = field(init=False)
    limiter: RateLimiter = field(init=False)
    proxies: TrustedProxies = field(init=False)
    models: ModelStore = field(init=False)

    def __post_init__(self) -> None:
        api = self.config.api
        self.fit_cache = LRUCache(api.cache.fit_entries)
        rl = api.rate_limit
        self.limiter = RateLimiter(rl.burst, rl.per_minute, rl.max_clients)
        self.proxies = TrustedProxies(api.trusted_proxies, api.resolve_interval_s)
        self.models = ModelStore(self.db, self.label_names, api.model_refresh_s)


def deps(request: Request) -> Deps:
    return request.app.state.deps


async def rate_limited(request: Request) -> None:
    """Dependency of the computing endpoints: one token per request and client IP. Async on
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
