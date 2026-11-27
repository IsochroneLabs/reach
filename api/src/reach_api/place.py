"""Live point routing for one address (F4.5, architecture O25, methodology V11).

One point → the nearest k destinations per chosen type and label plus all campus sites, routed
with Valhalla (walk and bike, one costmatrix request each) and OpenTripPlanner (transit and
bike + transit, one query per target and trip window). The fit is derived from these times with
the same code as `/api/cell`; nothing is cached (O25).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from reach_api import db as q
from reach_api.deps import Deps
from reach_api.fit import ProfileError, cell_summary
from reach_api.model import CAMPUS, MODES, Model, Term
from reach_api.otp import OtpError, OtpTrip
from reach_api.pois import campus_shares, decorate
from reach_api.valhalla import costing_options

LonLat = tuple[float, float]


@dataclass(frozen=True)
class Target:
    """One destination to route to, for one profile key and its trip window."""

    destination_id: str
    destination_type: str
    key: str
    window: str
    point: LonLat


@dataclass
class Routed:
    """Times of one point (seconds); transit trips keep their legs for the response."""

    walk_s: float | None = None
    bike_s: float | None = None
    transit: OtpTrip | None = None
    bike_transit: OtpTrip | None = None


def _window_time(row: dict[str, Any], tz: str) -> tuple[datetime, bool]:
    day = row["reference_date"]
    day = day.date() if isinstance(day, datetime) else day
    if isinstance(day, str):
        day = date.fromisoformat(day)
    at = row["time"]
    at = time.fromisoformat(at) if isinstance(at, str) else at
    return datetime.combine(day, at, tzinfo=ZoneInfo(tz)), row["kind"] == "arrive_by"


async def targets(d: Deps, model: Model, profile: dict[str, Any], point: LonLat) -> list[Target]:
    """Nearest k per weighted key (type or label), all campus sites; unknown keys are 422."""
    k_label = d.config.destination_labels.nearest_k_label if d.config.destination_labels else 1
    lon, lat = point
    out: dict[tuple[str, str], Target] = {}

    def add(rows: list[dict[str, Any]], key: str, dtype: str, window: str) -> None:
        for r in rows:
            if r.get("lon") is None or r.get("lat") is None:
                continue
            target = Target(
                destination_id=r["destination_id"],
                destination_type=dtype,
                key=key,
                window=window,
                point=(float(r["lon"]), float(r["lat"])),
            )
            out[(target.destination_id, key)] = target

    for key, pref in (profile.get("destinations") or {}).items():
        if not pref.get("importance"):
            continue
        info = model.key_info(key)
        if info is None:
            raise ProfileError(f"destinations.{key}: unknown destination type or category")
        if key == CAMPUS:
            # only the student's campus sites (programme, campus days or default mix), never the
            # nearest site of another programme (notes N29)
            mine = campus_shares(model, profile)
            rows = await d.db.fetch(q.Q_SITES)
            for r in rows:
                destination_id = f"campus_site:{r['site_id']}"
                if destination_id not in mine:
                    continue
                out[(destination_id, key)] = Target(
                    destination_id=destination_id,
                    destination_type=CAMPUS,
                    key=key,
                    window=info["trip_window"],
                    point=(float(r["lon"]), float(r["lat"])),
                )
            continue
        foods = (profile.get("labels") or {}).get("grocery") or []
        if key == "grocery" and foods:
            for label in foods:
                rows = await d.db.fetch(q.Q_NEAREST_LABEL, [lon, lat, "grocery", label, k_label])
                add(rows, key, "grocery", info["trip_window"])
            continue
        if ":" in key:
            dtype, label = key.split(":", 1)
            rows = await d.db.fetch(q.Q_NEAREST_LABEL, [lon, lat, dtype, label, k_label])
            add(rows, key, dtype, info["trip_window"])
            continue
        k = int(model.types.at[key, "nearest_k"])
        add(await d.db.fetch(q.Q_NEAREST_TYPE, [lon, lat, key, k]), key, key, info["trip_window"])
    return list(out.values())


def _at(matrix: np.ndarray, index: dict[LonLat, int], point: LonLat) -> float | None:
    value = float(matrix[0, index[(round(point[0], 7), round(point[1], 7))]])
    return None if np.isnan(value) else value


async def route(d: Deps, profile: dict[str, Any], targets: list[Target], point: LonLat) -> dict:
    """Times per (destination_id, key, mode); walk is always routed to cap the transit modes."""
    modes = list(dict.fromkeys(["walk", *profile["modes"]]))
    points = sorted({(round(t.point[0], 7), round(t.point[1], 7)) for t in targets})
    index = {p: i for i, p in enumerate(points)}
    source = [(round(point[0], 7), round(point[1], 7))]
    out: dict[tuple[str, str, str], float | OtpTrip | None] = {}

    walk_profile = d.config.routing_profiles["walk"]
    walk = await d.valhalla.matrix(
        source, points, walk_profile.costing or "", costing_options(walk_profile)
    )
    for t in targets:
        out[(t.destination_id, t.key, "walk")] = _at(walk, index, t.point)

    if "bike" in modes:
        bike_profile = d.config.routing_profiles["bike"]
        bike = await d.valhalla.matrix(
            source, points, bike_profile.costing or "", costing_options(bike_profile)
        )
        for t in targets:
            out[(t.destination_id, t.key, "bike")] = _at(bike, index, t.point)

    otp_modes = [m for m in ("transit", "bike_transit") if m in modes]
    if otp_modes:
        if d.otp is None:
            raise OtpError("OTP_URL is not set; the transit modes are unavailable")
        windows = {r["trip_window"]: r for r in await d.db.fetch(q.Q_WINDOWS)}
        jobs = []
        keys = []
        for t in targets:
            row = windows.get(t.window)
            if row is None:
                raise ProfileError(f"trip window {t.window!r} is not published")
            when, arrive_by = _window_time(row, d.config.timezone)
            origin, dest = (
                (t.point, source[0]) if row["direction"] == "back" else (source[0], t.point)
            )
            for mode in otp_modes:
                access = d.config.routing_profiles[mode].access
                if not access:
                    raise OtpError(f"routing profile {mode!r} has no OTP access mode")
                jobs.append(d.otp.plan(origin, dest, when, arrive_by, access))
                keys.append((t.destination_id, t.key, mode))
        trips = await asyncio.gather(*jobs)
        for key, trip in zip(keys, trips, strict=True):
            out[key] = trip

    # transit is never slower than walking the whole way (meth. §4); keep walk_only
    for t in targets:
        walk_s = out.get((t.destination_id, t.key, "walk"))
        for mode in otp_modes:
            key = (t.destination_id, t.key, mode)
            trip = out.get(key)
            if not isinstance(trip, OtpTrip):
                continue
            if walk_s is not None and (trip.time_s is None or walk_s < trip.time_s):
                out[key] = OtpTrip(time_s=round(walk_s), walk_only=True)
    return out


def _terms(model: Model, targets: list[Target], out: dict) -> tuple[dict[str, Term], list[str]]:
    terms: dict[str, Term] = {}
    modes: set[str] = set()
    for t in targets:
        dtype = t.destination_type
        term = model.term_of(t.destination_id, dtype)
        for mode in MODES:
            value = out.get((t.destination_id, t.key, mode))
            if value is None:
                continue
            if isinstance(value, OtpTrip):
                if value.time_s is None:
                    continue
                seconds: float = float(value.time_s)
                departure = value.departure
            else:
                seconds = float(value)
                departure = None
            if term not in terms:
                terms[term] = Term(
                    minutes=np.full((1, len(MODES)), np.nan, dtype=np.float32),
                    destination=np.full((1, len(MODES)), None, dtype=object),
                    departure=np.full((1, len(MODES)), None, dtype=object),
                )
            mi = MODES.index(mode)
            minutes = seconds / 60
            current = terms[term].minutes[0, mi]
            if np.isnan(current) or minutes < current:
                terms[term].minutes[0, mi] = minutes
                terms[term].destination[0, mi] = t.destination_id
                terms[term].departure[0, mi] = departure
            modes.add(mode)
    return terms, [m for m in MODES if m in modes]


def _legs(trip: OtpTrip, window: str) -> dict[str, Any]:
    walk_only = trip.walk_only or trip.first_stop is None
    return {
        "access_min": 0 if walk_only else round((trip.access_s or 0) / 60),
        "wait_min": 0 if walk_only else round((trip.wait_s or 0) / 60),
        "in_vehicle_min": 0 if walk_only else round((trip.in_vehicle_s or 0) / 60),
        "egress_min": 0 if walk_only else round((trip.egress_s or 0) / 60),
        "transfers": 0 if walk_only else int(trip.transfers or 0),
        "first_stop": None if walk_only else trip.first_stop,
        "first_route": None if walk_only else trip.first_route,
        "walk_only": walk_only,
        "last_departure": trip.departure if window == "night_return" and not walk_only else None,
    }


def trips(
    model: Model, profile: dict[str, Any], targets: list[Target], out: dict
) -> list[dict[str, Any]]:
    order = {k: i for i, k in enumerate(profile.get("destinations") or {})}
    rows = []
    for t in targets:
        for mode in profile["modes"]:
            value = out.get((t.destination_id, t.key, mode))
            if value is None:
                continue
            trip: dict[str, Any] = {
                "destination_type": t.key,
                "destination_id": t.destination_id,
                "name": model.names.get(t.destination_id) or None,
                "mode": mode,
                "trip_window": t.window,
                "minutes": None,
            }
            if isinstance(value, OtpTrip):
                if value.time_s is None:
                    continue
                trip["minutes"] = round(value.time_s / 60)
                trip["legs"] = _legs(value, t.window)
            else:
                trip["minutes"] = round(float(value) / 60)
            rows.append(trip)
    rows.sort(
        key=lambda x: (
            order.get(x["destination_type"], 99),
            x["destination_id"],
            MODES.index(x["mode"]),
        )
    )
    return rows


async def place_detail(
    d: Deps,
    model: Model,
    profile: dict[str, Any],
    point: LonLat,
    a: float,
    p: float,
) -> dict[str, Any]:
    """Body of POST /api/place: exact times from one point and the fit derived from them."""
    cell = await d.db.fetch(q.Q_CELL_AT, [point[0], point[1]])
    if not cell:
        raise LookupError("point outside the routing area")
    row = cell[0]
    chosen = await targets(d, model, profile, point)
    if not chosen:
        raise ProfileError("destinations: mark at least one destination as important")
    out = await route(d, profile, chosen, point)
    terms, _ = _terms(model, chosen, out)
    modes = list(dict.fromkeys(["walk", *profile["modes"]]))
    one = replace(
        model,
        cell_ids=np.array([row["cell_id"]]),
        cell_index={row["cell_id"]: 0},
        district=np.array([row["district_id"]], dtype=object),
        populated=np.array([bool(row["populated"])]),
        point=np.array([[point[0], point[1]]]),
        terms=terms,
        modes=modes,
    )
    summary = cell_summary(one, profile, row["cell_id"], a, p)
    district = row["district_id"]
    return {
        "cell_id": row["cell_id"],
        "district": model.district_names.get(district) if district else None,
        "point": [round(point[0], 6), round(point[1], 6)],
        "populated": bool(row["populated"]),
        "trips": await decorate(d.db, model, profile, trips(model, profile, chosen, out)),
        "fit": summary["fit"],
        "weekly_min": summary["weekly_min"],
        "reasons": summary["reasons"],
        "fit_parts": summary["fit_parts"],
    }
