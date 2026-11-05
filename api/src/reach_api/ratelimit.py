"""Token-bucket rate limit per client IP for the live endpoints (arch. §9), and the client IP
itself: X-Forwarded-For is only trusted when the peer is a trusted proxy (Caddy)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from socket import getaddrinfo

log = logging.getLogger(__name__)


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    """`burst` tokens per client, refilled at `per_minute`; one request takes one token."""

    def __init__(
        self,
        burst: int,
        per_minute: float,
        max_clients: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.burst = burst
        self.rate = per_minute / 60
        self.max_clients = max_clients
        self.clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def allow(self, client: str) -> tuple[bool, float]:
        """(allowed, seconds until the next token if not allowed)."""
        now = self.clock()
        b = self._buckets.get(client)
        if b is None:
            self._evict(now)
            b = self._buckets[client] = _Bucket(tokens=self.burst, updated=now)
        b.tokens = min(self.burst, b.tokens + (now - b.updated) * self.rate)
        b.updated = now
        if b.tokens >= 1:
            b.tokens -= 1
            return True, 0.0
        return False, (1 - b.tokens) / self.rate

    def _evict(self, now: float) -> None:
        if len(self._buckets) < self.max_clients:
            return
        # Drop buckets that are full again (idle clients); if none, the oldest ones.
        full_after = self.burst / self.rate
        idle = [k for k, b in self._buckets.items() if now - b.updated >= full_after]
        if not idle:
            idle = [min(self._buckets, key=lambda k: self._buckets[k].updated)]
        for k in idle:
            del self._buckets[k]


class TrustedProxies:
    """Addresses of the trusted proxy hosts, resolved by name (Compose service names)."""

    def __init__(
        self,
        hosts: list[str],
        resolve_interval_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.hosts = hosts
        self.interval = resolve_interval_s
        self.clock = clock
        self._ips: set[str] = set()
        self._resolved_at: float | None = None

    def _resolve(self) -> None:
        ips: set[str] = set()
        for host in self.hosts:
            try:
                ips |= {info[4][0] for info in getaddrinfo(host, None)}
            except OSError:
                log.debug("trusted proxy %s does not resolve", host)
        self._ips = ips
        self._resolved_at = self.clock()

    def is_trusted(self, peer: str) -> bool:
        if peer in self._ips:
            return True
        # A restarted proxy may have a new address: re-resolve, but not on every request.
        if self._resolved_at is None or self.clock() - self._resolved_at >= self.interval:
            self._resolve()
        return peer in self._ips


def client_ip(peer: str | None, forwarded_for: str | None, proxies: TrustedProxies) -> str:
    """Client address: the last X-Forwarded-For entry if the peer is a trusted proxy (Caddy
    appends the address it saw), else the peer itself."""
    peer = peer or "unknown"
    if forwarded_for and proxies.is_trusted(peer):
        last = forwarded_for.split(",")[-1].strip()
        if last:
            return last
    return peer
