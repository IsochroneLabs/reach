"""Async OpenTripPlanner client for the live point route (F4.5, arch. O17).

One GraphQL `planConnection` per point × destination × trip window; the query and the itinerary
selection are the same as `reach_pipeline.otp` (kept small here so the API image does not pull in
DuckDB and GeoPandas). A fake client answers the unit tests; the live graph is the same service the
pipeline uses.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from reach_api.settings import LiveOtp

log = logging.getLogger(__name__)

GRAPHQL_PATH = "/otp/gtfs/v1"
QUERY = """
query($o: PlanCoordinateInput!, $d: PlanCoordinateInput!, $dt: PlanDateTimeInput!,
      $access: [PlanAccessMode!], $first: Int!) {
  planConnection(origin: {location: {coordinate: $o}}, destination: {location: {coordinate: $d}},
                 dateTime: $dt, first: $first,
                 modes: {direct: [WALK],
                         transit: {access: $access, egress: [WALK], transfer: [WALK]}}) {
    edges { node {
      start end duration waitingTime walkTime numberOfTransfers
      legs { mode duration start { scheduledTime } end { scheduledTime }
             from { name } route { shortName } }
    } }
  }
}"""

LonLat = tuple[float, float]


class OtpError(Exception):
    """OpenTripPlanner is unreachable or answered 5xx after retries."""


class OtpTimeout(OtpError):
    """The last attempt timed out."""


@dataclass(frozen=True)
class OtpTrip:
    """The kept itinerary of one query (seconds; None where OTP found nothing)."""

    time_s: int | None
    access_s: int | None = None
    wait_s: int | None = None
    in_vehicle_s: int | None = None
    egress_s: int | None = None
    transfers: int | None = None
    first_stop: str | None = None
    first_route: str | None = None
    departure: str | None = None
    walk_only: bool = False


def _ms(value: Any) -> datetime:
    return datetime.fromisoformat(value) if isinstance(value, str) else datetime.fromtimestamp(0)


def parse_plan(body: dict[str, Any], when: datetime, arrive_by: bool) -> OtpTrip:
    """Turn a `planConnection` answer into an `OtpTrip`, counting the wait at home (M6)."""
    if body.get("errors"):
        raise OtpError(f"OTP answered errors: {json.dumps(body['errors'])[:300]}")
    edges = (((body.get("data") or {}).get("planConnection") or {}).get("edges")) or []
    its = [e["node"] for e in edges]
    if not its:
        return OtpTrip(time_s=None)
    if arrive_by:
        best = max(its, key=lambda i: _ms(i["start"]))
        total = (when - _ms(best["start"])).total_seconds()
    else:
        best = min(its, key=lambda i: _ms(i["end"]))
        total = (_ms(best["end"]) - when).total_seconds()
    legs = best["legs"]
    rides = [i for i, leg in enumerate(legs) if leg["mode"] not in ("WALK", "BICYCLE")]
    start, end = _ms(best["start"]), _ms(best["end"])
    if not rides:
        return OtpTrip(time_s=round(total), departure=start.strftime("%H:%M"), walk_only=True)
    first, last = rides[0], rides[-1]
    access = sum(leg["duration"] for leg in legs[:first])
    egress = sum(leg["duration"] for leg in legs[last + 1 :])
    in_vehicle = sum(legs[i]["duration"] for i in rides)
    trip_s = (end - start).total_seconds()
    wait_home = total - trip_s
    return OtpTrip(
        time_s=round(total),
        access_s=round(access),
        wait_s=round(wait_home + max(trip_s - access - egress - in_vehicle, 0)),
        in_vehicle_s=round(in_vehicle),
        egress_s=round(egress),
        transfers=int(best["numberOfTransfers"]),
        first_stop=legs[first]["from"]["name"],
        first_route=(legs[first].get("route") or {}).get("shortName"),
        departure=_ms(legs[first]["start"]["scheduledTime"]).strftime("%H:%M"),
    )


class OtpClient:
    """One HTTP pool; at most `cfg.concurrency` queries in flight."""

    def __init__(
        self,
        cfg: LiveOtp,
        url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.cfg = cfg
        self.url = url.rstrip("/")
        self._semaphore = asyncio.Semaphore(cfg.concurrency)
        self._http = httpx.AsyncClient(
            base_url=self.url, timeout=cfg.timeout_s, transport=transport
        )
        self.requests = 0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        what = f"OTP planConnection ({self.url})"
        attempts = self.cfg.retries + 1
        problem = ""
        timed_out = False
        for attempt in range(attempts):
            try:
                async with self._semaphore:
                    self.requests += 1
                    resp = await self._http.post(GRAPHQL_PATH, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                problem = f"{type(exc).__name__}: {exc}"
                timed_out = isinstance(exc, httpx.TimeoutException)
            else:
                if resp.status_code < 400:
                    return resp.json()
                problem = f"HTTP {resp.status_code}: {resp.text[:200]}"
                if resp.status_code < 500:
                    raise OtpError(f"{what} answered {problem}")
                timed_out = False
            if attempt + 1 < attempts:
                wait = self.cfg.backoff_s * 2**attempt
                log.warning("%s failed (%s), retry %d in %.0f s", what, problem, attempt + 1, wait)
                await asyncio.sleep(wait)
        error = OtpTimeout if timed_out else OtpError
        raise error(f"{what} failed after {attempts} attempts: {problem}")

    async def plan(
        self,
        origin: LonLat,
        destination: LonLat,
        when: datetime,
        arrive_by: bool,
        access: str,
    ) -> OtpTrip:
        """Best itinerary from `origin` to `destination` ([lon, lat]) for the window time."""
        variables = {
            "o": {"latitude": origin[1], "longitude": origin[0]},
            "d": {"latitude": destination[1], "longitude": destination[0]},
            "dt": {("latestArrival" if arrive_by else "earliestDeparture"): when.isoformat()},
            "access": [access],
            "first": self.cfg.itineraries,
        }
        body = await self._post({"query": QUERY, "variables": variables})
        return parse_plan(body, when, arrive_by)
