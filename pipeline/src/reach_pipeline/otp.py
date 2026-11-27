"""OpenTripPlanner (arch. O17): graph inputs and an async client for per-pair transit queries.

Inputs (`prepare_inputs`): the GTFS feed clipped to the stops of the routing area (DuckDB, the
naldo feed is far larger than the city), the routing-area OSM extract and the two OTP config
files with speeds from `routing_profiles` and the service period around the reference dates.
The graph itself is built by the official OTP image (`make refresh`, one-shot `--build --save`).

Client (`OtpClient.plan`): one GraphQL `planConnection` per pair and window; depart-at windows
keep the itinerary that arrives first, arrive-by windows the one that leaves last (meth. §4, M6:
the wait at home counts). Bounded concurrency and retries as in the Valhalla client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pandas as pd

from reach_pipeline.config import Config, Otp
from reach_pipeline.errors import ConfigError, ExternalError, StageValidationError

log = logging.getLogger(__name__)

URL_ENV = "OTP_URL"
GRAPHQL_PATH = "/otp/gtfs/v1"
GTFS_FILES = (
    "stops.txt",
    "stop_times.txt",
    "trips.txt",
    "routes.txt",
    "agency.txt",
    "calendar.txt",
    "calendar_dates.txt",
    "transfers.txt",
    "feed_info.txt",
)
# Extra days of service around the reference dates in the graph (night trips of the day before).
SERVICE_MARGIN_DAYS = 1

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


# --- graph inputs ----------------------------------------------------------------------------


def clip_gtfs(src: Path, dst: Path, stop_ids: list[str]) -> dict[str, int]:
    """Keep the given stops (and their parent stations), their stop times, trips with at least
    two kept stops and the routes, agencies, services and transfers those use."""
    missing = [f for f in GTFS_FILES if not (src / f).exists()]
    if missing:
        raise StageValidationError(f"GTFS files missing for the transit build: {missing}")
    dst.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    def read(name: str) -> str:
        return f"read_csv('{src / name}', all_varchar=true, header=true)"

    con.register("keep_ids", pd.DataFrame({"stop_id": stop_ids}, dtype=str))
    con.execute(
        f"CREATE TABLE stops AS SELECT * FROM {read('stops.txt')} "
        "WHERE stop_id IN (SELECT stop_id FROM keep_ids)"
    )
    cols = {r[0] for r in con.execute("DESCRIBE stops").fetchall()}
    if "parent_station" in cols:
        con.execute(
            f"INSERT INTO stops SELECT * FROM {read('stops.txt')} WHERE stop_id IN "
            "(SELECT parent_station FROM stops WHERE coalesce(parent_station, '') <> '') "
            "AND stop_id NOT IN (SELECT stop_id FROM stops)"
        )
    con.execute(f"""
        CREATE TABLE st0 AS SELECT * FROM {read("stop_times.txt")}
        WHERE stop_id IN (SELECT stop_id FROM stops);
        CREATE TABLE keep_trips AS SELECT trip_id FROM st0 GROUP BY trip_id HAVING count(*) >= 2;
        CREATE TABLE stop_times AS SELECT * FROM st0
        WHERE trip_id IN (SELECT trip_id FROM keep_trips);
        CREATE TABLE trips AS SELECT * FROM {read("trips.txt")}
        WHERE trip_id IN (SELECT trip_id FROM keep_trips);
        CREATE TABLE routes AS SELECT * FROM {read("routes.txt")}
        WHERE route_id IN (SELECT route_id FROM trips);
        CREATE TABLE agency AS SELECT * FROM {read("agency.txt")};
        CREATE TABLE calendar AS SELECT * FROM {read("calendar.txt")}
        WHERE service_id IN (SELECT service_id FROM trips);
        CREATE TABLE calendar_dates AS SELECT * FROM {read("calendar_dates.txt")}
        WHERE service_id IN (SELECT service_id FROM trips);
        CREATE TABLE transfers AS SELECT * FROM {read("transfers.txt")}
        WHERE from_stop_id IN (SELECT stop_id FROM stops)
          AND to_stop_id IN (SELECT stop_id FROM stops);
        CREATE TABLE feed_info AS SELECT * FROM {read("feed_info.txt")};
    """)
    counts = {}
    for f in GTFS_FILES:
        table = f.removesuffix(".txt")
        con.execute(f"COPY {table} TO '{dst / f}' (HEADER, QUOTE '\"')")
        counts[table] = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    if counts["trips"] == 0:
        raise StageValidationError("clipped GTFS feed has no trips with two stops in the area")
    return counts


def build_config(reference_dates: list[date]) -> dict[str, Any]:
    """`build-config.json`: German OSM tag mapping, bike parking for bike + transit (M5) and a
    service period that covers every reference date."""
    start = min(reference_dates) - timedelta(days=SERVICE_MARGIN_DAYS)
    end = max(reference_dates) + timedelta(days=SERVICE_MARGIN_DAYS)
    return {
        "osmDefaults": {"osmTagMapping": "germany"},
        "staticBikeParkAndRide": True,
        "transitServiceStart": start.isoformat(),
        "transitServiceEnd": end.isoformat(),
    }


def router_config(cfg: Config) -> dict[str, Any]:
    """`router-config.json`: walking and cycling speeds (m/s) from the routing profiles."""
    by_access = {p.access: p for p in cfg.routing_profiles.values() if p.engine == "otp"}
    if "WALK" not in by_access:
        raise ConfigError("routing_profiles: an otp profile with access WALK is required")
    defaults: dict[str, Any] = {"walk": {"speed": round(by_access["WALK"].speed_kmh / 3.6, 3)}}
    if "BICYCLE_PARKING" in by_access:
        speed = by_access["BICYCLE_PARKING"].speed_kmh / 3.6
        defaults["bicycle"] = {"speed": round(speed, 3)}
    defaults["numItineraries"] = cfg.otp.itineraries if cfg.otp else 3
    return {"routingDefaults": defaults}


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


# --- client ----------------------------------------------------------------------------------


def resolve_url(cfg: Otp) -> str:
    """Base URL: $OTP_URL if set, else `otp.url`; fails if neither is set."""
    url = os.environ.get(URL_ENV) or cfg.url
    if not url:
        raise ConfigError(f"{URL_ENV} is not set and otp.url is null: set it in .env")
    return url.rstrip("/")


@dataclass(frozen=True)
class Trip:
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


def parse_plan(body: dict[str, Any], when: datetime, arrive_by: bool) -> Trip:
    """Turn a `planConnection` answer into a `Trip`, counting the wait at home (M6)."""
    if body.get("errors"):
        raise ExternalError(f"OTP answered errors: {json.dumps(body['errors'])[:300]}")
    edges = (((body.get("data") or {}).get("planConnection") or {}).get("edges")) or []
    its = [e["node"] for e in edges]
    if not its:
        return Trip(time_s=None)
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
        return Trip(time_s=round(total), departure=start.strftime("%H:%M"), walk_only=True)
    first, last = rides[0], rides[-1]
    access = sum(leg["duration"] for leg in legs[:first])
    egress = sum(leg["duration"] for leg in legs[last + 1 :])
    in_vehicle = sum(legs[i]["duration"] for i in rides)
    trip_s = (end - start).total_seconds()
    wait_home = total - trip_s
    return Trip(
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
        self, cfg: Otp, url: str | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.cfg = cfg
        self.url = url or resolve_url(cfg)
        self._semaphore = asyncio.Semaphore(cfg.concurrency)
        self._http = httpx.AsyncClient(
            base_url=self.url, timeout=cfg.timeout_s, transport=transport
        )
        self.requests = 0

    async def __aenter__(self) -> OtpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        what = f"OTP planConnection ({self.url})"
        attempts = self.cfg.retries + 1
        problem = ""
        for attempt in range(attempts):
            try:
                async with self._semaphore:
                    self.requests += 1
                    resp = await self._http.post(GRAPHQL_PATH, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                problem = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code < 400:
                    return resp.json()
                problem = f"HTTP {resp.status_code}: {resp.text[:200]}"
                if resp.status_code < 500:
                    raise ExternalError(f"{what} answered {problem}")
            if attempt + 1 < attempts:
                wait = self.cfg.backoff_s * 2**attempt
                log.warning("%s failed (%s), retry %d in %.0f s", what, problem, attempt + 1, wait)
                await asyncio.sleep(wait)
        raise ExternalError(f"{what} failed after {attempts} attempts: {problem}")

    async def plan(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        when: datetime,
        arrive_by: bool,
        access: str,
    ) -> Trip:
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
