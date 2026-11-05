"""Async Valhalla client for the live endpoints (arch. §6.2, §6.5 rules 8–11).

Request parameters checked against Valhalla 3.9.1 (P5, local tiles): `isochrone` with
`contours`, `polygons`, `denoise`, `generalize` and `reverse`; `route` with
`directions_type: none` (shape as polyline6 in `trip.legs[].shape`); `expansion` with
`action: isochrone`, `skip_opposites`, `dedupe`, `expansion_properties`; `sources_to_targets`
with `verbose: false` (durations in whole seconds, `null` = unreachable). A location without
nearby edges answers HTTP 400 (`error_code` 171).
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
        max_matrix_pairs: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.cfg = cfg
        self.max_matrix_pairs = max_matrix_pairs
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
            else:
                if resp.status_code < 400:
                    return resp.json()
                if resp.status_code < 500:
                    raise NoRouteError(f"Valhalla {action}: {resp.text[:300]}")
                problem = f"HTTP {resp.status_code}: {resp.text[:200]}"
            log.warning(
                "Valhalla %s failed (%s), attempt %d/%d", action, problem, attempt + 1, attempts
            )
            if attempt + 1 < attempts:
                await asyncio.sleep(self.cfg.backoff_s * 2**attempt)
        raise ValhallaError(f"Valhalla {action} failed after {attempts} attempts: {problem}")

    async def isochrone(
        self,
        origin: LonLat,
        costing: str,
        options: dict[str, Any],
        contours_min: list[float],
        generalize_m: float,
        denoise: float,
        reverse: bool = False,
    ) -> dict[str, Any]:
        """GeoJSON FeatureCollection, one polygon per contour; only `contour` kept as property."""
        body = await self.post(
            "isochrone",
            {
                "locations": [_loc(origin)],
                "costing": costing,
                "costing_options": {costing: options},
                "contours": [{"time": t} for t in contours_min],
                "polygons": True,
                "generalize": generalize_m,
                "denoise": denoise,
                "reverse": reverse,
            },
        )
        features = [
            {
                "type": "Feature",
                "properties": {"contour_min": f["properties"]["contour"]},
                "geometry": f["geometry"],
            }
            for f in body.get("features", [])
        ]
        features.sort(key=lambda f: f["properties"]["contour_min"])
        return {"type": "FeatureCollection", "features": features}

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

    async def expansion(
        self, origin: LonLat, costing: str, options: dict[str, Any], budget_min: float
    ) -> dict[str, Any]:
        """Street edges reached within the budget, LineStrings with `duration` (seconds)."""
        body = await self.post(
            "expansion",
            {
                "locations": [_loc(origin)],
                "costing": costing,
                "costing_options": {costing: options},
                "action": "isochrone",
                "contours": [{"time": budget_min}],
                "skip_opposites": True,
                "dedupe": True,
                "expansion_properties": ["duration"],
            },
        )
        return {"type": "FeatureCollection", "features": body.get("features", [])}

    async def matrix(
        self,
        sources: list[LonLat],
        targets: list[LonLat],
        costing: str,
        options: dict[str, Any],
    ) -> list[list[float | None]]:
        """Seconds (sources × targets), None = unreachable; split along the longer side so a
        request never exceeds `max_matrix_pairs` (`valhalla.max_matrix_pairs`)."""
        if not sources or not targets:
            return [[None] * len(targets) for _ in sources]
        if min(len(sources), len(targets)) > self.max_matrix_pairs:
            raise ValhallaError(
                f"{len(sources)} × {len(targets)} locations exceed max_matrix_pairs "
                f"({self.max_matrix_pairs}) along both axes"
            )
        if len(targets) >= len(sources):
            step = max(1, self.max_matrix_pairs // len(sources))
            parts = await asyncio.gather(
                *(
                    self._matrix(sources, targets[i : i + step], costing, options)
                    for i in range(0, len(targets), step)
                )
            )
            return [sum((p[r] for p in parts), []) for r in range(len(sources))]
        step = max(1, self.max_matrix_pairs // len(targets))
        parts = await asyncio.gather(
            *(
                self._matrix(sources[i : i + step], targets, costing, options)
                for i in range(0, len(sources), step)
            )
        )
        return [row for p in parts for row in p]

    async def _matrix(
        self, sources: list[LonLat], targets: list[LonLat], costing: str, options: dict
    ) -> list[list[float | None]]:
        body = await self.post(
            "sources_to_targets",
            {
                "sources": [_loc(p) for p in sources],
                "targets": [_loc(p) for p in targets],
                "costing": costing,
                "costing_options": {costing: options},
                "verbose": False,
            },
        )
        try:
            durations = body["sources_to_targets"]["durations"]
        except (KeyError, TypeError) as exc:
            raise ValhallaError(f"unexpected matrix response: {str(body)[:300]}") from exc
        if len(durations) != len(sources) or any(len(r) != len(targets) for r in durations):
            raise ValhallaError("matrix response does not match the request size")
        return durations
