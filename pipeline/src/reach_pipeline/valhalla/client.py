"""Async Valhalla client: bounded concurrency, retries, compact matrix output (arch. §6.5).

Requests use the compact matrix format (`verbose: false`, Valhalla ≥ 3.5; checked on 3.9.1):
`{"sources_to_targets": {"durations": [[s, …], …], "distances": …}}`, `null` = unreachable.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
import numpy as np

from reach_pipeline.config import Profile, Valhalla
from reach_pipeline.errors import BadRequestError, ConfigError, ExternalError

log = logging.getLogger(__name__)

URL_ENV = "VALHALLA_URL"
# Valhalla's speed option per costing; the value comes from Profile.speed_kmh only.
SPEED_OPTION = {"pedestrian": "walking_speed", "bicycle": "cycling_speed"}


def resolve_url(cfg: Valhalla) -> str:
    """Base URL: $VALHALLA_URL if set, else `valhalla.url` from the config."""
    return (os.environ.get(URL_ENV) or cfg.url).rstrip("/")


def costing_options(profile: Profile) -> dict[str, Any]:
    """`costing_options` of a request: the profile's options plus its speed."""
    options = {**profile.costing_options, SPEED_OPTION[profile.costing]: profile.speed_kmh}
    return {profile.costing: options}


def _locations(lonlat: np.ndarray) -> list[dict[str, float]]:
    return [{"lon": round(float(x), 7), "lat": round(float(y), 7)} for x, y in lonlat]


class ValhallaClient:
    """One HTTP connection pool; at most `cfg.concurrency` requests in flight."""

    def __init__(
        self,
        cfg: Valhalla,
        url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.cfg = cfg
        self.url = url or resolve_url(cfg)
        self._semaphore = asyncio.Semaphore(cfg.concurrency)
        self._http = httpx.AsyncClient(
            base_url=self.url, timeout=cfg.timeout_s, transport=transport
        )
        self.requests = 0

    async def __aenter__(self) -> ValhallaClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    async def _send(self, method: str, action: str, payload: dict[str, Any] | None) -> Any:
        what = f"Valhalla {action} ({self.url})"
        attempts = self.cfg.retries + 1
        for attempt in range(attempts):
            try:
                async with self._semaphore:
                    self.requests += 1
                    resp = await self._http.request(method, f"/{action}", json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                problem = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code < 400:
                    return resp.json()
                if resp.status_code < 500:
                    # Bad request (e.g. a location without nearby edges): retrying cannot help.
                    raise BadRequestError(f"{what} answered {resp.status_code}: {resp.text[:500]}")
                problem = f"HTTP {resp.status_code}: {resp.text[:200]}"
            if attempt + 1 < attempts:
                wait = self.cfg.backoff_s * 2**attempt
                log.warning("%s failed (%s), retry %d in %.0f s", what, problem, attempt + 1, wait)
                await asyncio.sleep(wait)
        raise ExternalError(f"{what} failed after {attempts} attempts: {problem}")

    async def get(self, action: str) -> Any:
        return await self._send("GET", action, None)

    async def post(self, action: str, payload: dict[str, Any]) -> Any:
        return await self._send("POST", action, payload)

    async def matrix(
        self,
        sources: np.ndarray,
        targets: np.ndarray,
        costing: str,
        options: dict[str, Any],
    ) -> np.ndarray:
        """Travel times in seconds, shape (sources, targets); NaN = unreachable.

        `sources` and `targets` are (n, 2) arrays of lon/lat (EPSG:4326). Target sets larger than
        `max_matrix_pairs / len(sources)` are split into several requests.
        """
        n_src, n_tgt = len(sources), len(targets)
        if n_src == 0 or n_tgt == 0:
            return np.full((n_src, n_tgt), np.nan)
        per_request = self.cfg.max_matrix_pairs // n_src
        if per_request < 1:
            raise ConfigError(
                f"{n_src} sources exceed valhalla.max_matrix_pairs "
                f"({self.cfg.max_matrix_pairs}); use a smaller count.block_size_m or "
                "recommend.group_size_m"
            )
        src = _locations(sources)
        chunks = [targets[i : i + per_request] for i in range(0, n_tgt, per_request)]
        parts = await asyncio.gather(
            *(self._matrix_chunk(src, chunk, costing, options) for chunk in chunks)
        )
        return np.hstack(parts)

    async def _matrix_chunk(
        self, src: list[dict[str, float]], targets: np.ndarray, costing: str, options: dict
    ) -> np.ndarray:
        payload = {
            "sources": src,
            "targets": _locations(targets),
            "costing": costing,
            "costing_options": options,
            "verbose": False,
        }
        body = await self.post("sources_to_targets", payload)
        try:
            durations = body["sources_to_targets"]["durations"]
        except (KeyError, TypeError) as exc:
            raise ExternalError(f"unexpected matrix response: {str(body)[:300]}") from exc
        times = np.array(durations, dtype=float)  # None -> nan
        if times.shape != (len(src), len(targets)):
            raise ExternalError(
                f"matrix response has shape {times.shape}, expected {(len(src), len(targets))}"
            )
        return times
