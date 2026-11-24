"""Async Valhalla client for the live walk and bike route (arch. §9, U2; endpoint in S1.10).

Request parameters checked against Valhalla 3.9.1 on the Tübingen tiles (archive): `route` with
`directions_type: none` (shape as polyline6 in `trip.legs[].shape`). A location without nearby
edges answers HTTP 400 (`error_code` 171).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from reach_api.settings import LiveValhalla

log = logging.getLogger(__name__)

LonLat = tuple[float, float]


class ValhallaError(Exception):
    """Valhalla is unreachable or answered 5xx after retries."""


class ValhallaTimeout(ValhallaError):
    """The last attempt timed out (`timeout_s` of the client's config)."""


class NoRouteError(Exception):
    """Valhalla rejected the request (4xx), e.g. no street near the location."""


def _loc(p: LonLat) -> dict[str, float]:
    return {"lon": round(p[0], 7), "lat": round(p[1], 7)}


def decode_polyline6(encoded: str) -> list[list[float]]:
    """Coordinates [lon, lat] of a Valhalla shape (Google polyline, precision 6)."""
    coords: list[list[float]] = []
    index = lat = lon = 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            result = shift = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append([lon / 1e6, lat / 1e6])
    return coords


class ValhallaClient:
    """One HTTP connection pool; at most `cfg.concurrency` requests in flight."""

    def __init__(
        self,
        url: str,
        cfg: LiveValhalla,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.cfg = cfg
        self._semaphore = asyncio.Semaphore(cfg.concurrency)
        self._http = httpx.AsyncClient(
            base_url=self.url, timeout=cfg.timeout_s, transport=transport
        )
        self.requests = 0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def post(self, action: str, payload: dict[str, Any]) -> Any:
        attempts = self.cfg.retries + 1
        for attempt in range(attempts):
            try:
                async with self._semaphore:
                    self.requests += 1
                    resp = await self._http.post(f"/{action}", json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                problem = f"{type(exc).__name__}: {exc}"
                timed_out = isinstance(exc, httpx.TimeoutException)
            else:
                if resp.status_code < 400:
                    return resp.json()
                if resp.status_code < 500:
                    raise NoRouteError(f"Valhalla {action}: {resp.text[:300]}")
                problem = f"HTTP {resp.status_code}: {resp.text[:200]}"
                timed_out = False
            log.warning(
                "Valhalla %s failed (%s), attempt %d/%d", action, problem, attempt + 1, attempts
            )
            if attempt + 1 < attempts:
                await asyncio.sleep(self.cfg.backoff_s * 2**attempt)
        error = ValhallaTimeout if timed_out else ValhallaError
        raise error(f"Valhalla {action} failed after {attempts} attempts: {problem}")

    async def route(
        self, origin: LonLat, target: LonLat, costing: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        """GeoJSON LineString feature with `time_s` and `length_m`."""
        body = await self.post(
            "route",
            {
                "locations": [_loc(origin), _loc(target)],
                "costing": costing,
                "costing_options": {costing: options},
                "directions_type": "none",
                "units": "kilometers",
            },
        )
        trip = body["trip"]
        coords = [c for leg in trip["legs"] for c in decode_polyline6(leg["shape"])]
        return {
            "type": "Feature",
            "properties": {
                "time_s": trip["summary"]["time"],
                "length_m": round(trip["summary"]["length"] * 1000, 1),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        }
