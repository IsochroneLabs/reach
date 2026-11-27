"""Reference data, address search, fit and cell detail (data contract v1.1.0, S1.10).

Shapes match `web/src/api/types.ts`. POST bodies are never logged (AGENTS.md rule 9); the fit
cache keys only on the run and the profile (the weight vector).
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from reach_api import db as q
from reach_api.deps import Deps, deps, rate_limited
from reach_api.fit import ProfileError, cell_summary, fit_response
from reach_api.model import MODES, Model
from reach_api.otp import OtpError
from reach_api.place import place_detail
from reach_api.pois import decorate
from reach_api.valhalla import NoRouteError, ValhallaError, costing_options

router = APIRouter(prefix="/api")
D = Annotated[Deps, Depends(deps)]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Preference(_Body):
    importance: int = Field(ge=0, le=3)
    fine_time_min: float | None = Field(default=None, gt=0, le=180)


class FitRequest(_Body):
    programme: str | None = None
    campus_days: dict[str, float] | None = None
    modes: list[Literal["walk", "bike", "transit", "bike_transit"]] = Field(min_length=1)
    destinations: dict[str, Preference]
    labels: dict[str, list[str]] | None = None
    area_level: Literal["district", "teilort"] | None = None

    def profile(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class SearchRequest(_Body):
    q: str = Field(max_length=200)


class PlaceRequest(_Body):
    """F4.5: a point in EPSG:4326 and the student profile; no cache (O25)."""

    point: tuple[float, float]
    profile: FitRequest

    @field_validator("point")
    @classmethod
    def _point(cls, value: tuple[float, float]) -> tuple[float, float]:
        lon, lat = value
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("point must be [lon, lat] in EPSG:4326")
        return value


class RouteRequest(_Body):
    """F4.5: one walk or bike route from a point to a published destination."""

    origin: tuple[float, float]
    destination_id: str = Field(max_length=100)
    mode: Literal["walk", "bike"]

    @field_validator("origin")
    @classmethod
    def _origin(cls, value: tuple[float, float]) -> tuple[float, float]:
        lon, lat = value
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("origin must be [lon, lat] in EPSG:4326")
        return value


async def _model(d: Deps) -> Model:
    return await d.models.get()


def _label(row: dict) -> dict[str, str]:
    return {"en": row["label_en"], "de": row["label_de"]}


@router.get("/meta")
async def meta(d: D) -> dict[str, Any]:
    m = await _model(d)
    sources = await d.db.fetch(q.Q_SOURCES, [m.run_id])
    windows = await d.db.fetch(q.Q_WINDOWS)
    b = (await d.db.fetch(q.Q_BOUNDS))[0]
    return {
        "run_id": m.run_id,
        "sources": [
            {"source": s["source"], "date": str(s["date"])}
            | ({"valid_to": str(s["gtfs_valid_to"])} if s["source"] == "gtfs" else {})
            for s in sources
            if s["source"] in ("osm", "gtfs", "zensus")
        ],
        "trip_windows": [
            {
                "trip_window": w["trip_window"],
                "weekday": w["weekday"],
                "time": w["time"],
                "kind": w["kind"],
                "direction": w["direction"],
                "reference_date": str(w["reference_date"]),
            }
            for w in windows
        ],
        "bounds": [[b["w"], b["s"]], [b["e"], b["n"]]],
        "modes": m.modes,
    }


@router.get("/destination-types")
async def destination_types(d: D) -> list[dict[str, Any]]:
    m = await _model(d)
    out = []
    for dtype, row in m.types.iterrows():
        item = {
            "destination_type": dtype,
            "label": {"en": row["label_en"], "de": row["label_de"]},
            "trip_window": row["trip_window"],
            "fine_time_min": float(row["fine_time_min"]),
        }
        labs = m.labels[m.labels["destination_type"] == dtype] if len(m.labels) else m.labels
        if len(labs):
            item["labels"] = [
                {
                    "label": r["label"],
                    "kind": r["label_kind"] if r["label_kind"] != "religion" else "group",
                    "name": m.label_names.get(
                        f"{dtype}:{r['label']}",
                        {"en": r["label"].replace("_", " ").title()}
                        | {"de": r["label"].replace("_", " ").title()},
                    ),
                    "destinations": int(r["destinations"]),
                }
                for r in labs.to_dict("records")
            ]
        out.append(item)
    return out


@router.get("/label-destinations")
async def label_destinations(d: D) -> list[dict[str, Any]]:
    rows = await d.db.fetch(q.Q_LABEL_DESTINATIONS)
    merged: dict[tuple, dict] = {}
    for r in rows:
        # one entry per place: brand and group rows of the same supermarket share a point
        key = (r["destination_type"], round(r["lon"], 6), round(r["lat"], 6))
        item = merged.setdefault(
            key,
            {
                "destination_id": r["destination_id"],
                "destination_type": r["destination_type"],
                "labels": [],
                "name": r["name"] or None,
                "point": [round(r["lon"], 6), round(r["lat"], 6)],
            },
        )
        item["labels"].append(r["label"])
    return list(merged.values())


@router.get("/campus-sites")
async def campus_sites(d: D) -> list[dict[str, Any]]:
    m = await _model(d)
    rows = await d.db.fetch(q.Q_SITES)
    progs = m.programmes
    return [
        {
            "site_id": r["site_id"],
            "name": r["name"],
            "programmes": sorted(p for p, sites in progs["sites"].items() if r["site_id"] in sites),
            "point": [round(r["lon"], 6), round(r["lat"], 6)],
            "default_share": float(r["default_share"]),
        }
        for r in rows
    ]


@router.get("/programmes")
async def programmes(d: D) -> list[dict[str, Any]]:
    m = await _model(d)
    return [
        {"programme": p, "label": _label(row), "sites": list(row["sites"])}
        | ({"shares": list(row["shares"])} if _has(row.get("shares")) else {})
        for p, row in m.programmes.sort_index().iterrows()
    ]


def _has(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) > 0


def persona_profile(raw: dict[str, Any]) -> dict[str, Any]:
    dests = {
        k: ({"importance": v} if isinstance(v, int) else dict(v))
        for k, v in (raw.get("destinations") or {}).items()
    }
    prof: dict[str, Any] = {"modes": raw.get("modes", ["walk"]), "destinations": dests}
    for key in ("programme", "campus_days", "labels"):
        if raw.get(key):
            prof[key] = raw[key]
    return prof


@router.get("/personas")
async def personas(d: D) -> list[dict[str, Any]]:
    return [
        {"persona": k, "label": v.get("label", {"en": k, "de": k}), "profile": persona_profile(v)}
        for k, v in d.personas.items()
    ]


def _words(text: str) -> list[str]:
    t = text.lower()
    t = t.replace("straße", "str").replace("strasse", "str").replace("str.", "str")
    words = [w for w in re.split(r"[^a-z0-9äöüß]+", t) if w]
    return [f"%{w.replace('%', '').replace('_', '')}%" for w in words]


@router.post("/addresses/search", dependencies=[Depends(rate_limited)])
async def search(body: SearchRequest, d: D) -> list[dict[str, Any]]:
    cfg = d.config.api.address_search
    words = _words(body.q)
    if len(body.q.strip()) < cfg.min_chars or not words:
        raise HTTPException(422, f"q: at least {cfg.min_chars} characters")
    rows = await d.db.fetch(q.Q_SEARCH, [words, cfg.limit])
    return [
        {
            "label": r["label"],
            "cell_id": r["cell_id"],
            "point": [round(r["lon"], 6), round(r["lat"], 6)],
        }
        for r in rows
    ]


@router.post("/fit", dependencies=[Depends(rate_limited)])
async def fit(body: FitRequest, d: D) -> Any:
    m = await _model(d)
    profile = body.profile()
    key = m.run_id + json.dumps(profile, sort_keys=True)
    cached = d.fit_cache.get(key)
    if cached is not None:
        return json.loads(cached)
    f = d.config.api.fit
    try:
        out = fit_response(m, profile, f.a, f.p)
    except ProfileError as exc:
        raise HTTPException(422, str(exc)) from exc
    d.fit_cache.put(key, json.dumps(out))
    return out


def _min(s: Any) -> int | None:
    return None if s is None else int(round(s / 60))


@router.post("/cell/{cell_id}", dependencies=[Depends(rate_limited)])
async def cell(cell_id: str, body: FitRequest, d: D) -> dict[str, Any]:
    m = await _model(d)
    if cell_id not in m.cell_index:
        raise HTTPException(404, f"cell {cell_id} not found")
    f = d.config.api.fit
    try:
        summary = cell_summary(m, body.profile(), cell_id, f.a, f.p)
    except ProfileError as exc:
        raise HTTPException(422, str(exc)) from exc
    wanted = {dest: key for key, ids in summary["targets"].items() for dest in ids}
    rows = await d.db.fetch(q.Q_CELL_TRIPS, [cell_id, list(wanted)])
    modes = set(body.modes) | {"walk", "bike", "transit"}
    trips = []
    for r in rows:
        if r["mode"] not in modes:
            continue
        key = wanted[r["destination_id"]]
        trip = {
            "destination_type": key,
            "destination_id": r["destination_id"],
            "name": m.names.get(r["destination_id"]) or None,
            "mode": r["mode"],
            "trip_window": r["trip_window"],
            "minutes": _min(r["time_s"]),
        }
        if r["mode"] in ("transit", "bike_transit"):
            walk_only = bool(r["walk_only"]) or r["first_stop"] is None
            trip["legs"] = {
                "access_min": 0 if walk_only else _min(r["access_s"]),
                "wait_min": 0 if walk_only else _min(r["wait_s"]),
                "in_vehicle_min": 0 if walk_only else _min(r["in_vehicle_s"]),
                "egress_min": 0 if walk_only else _min(r["egress_s"]),
                "transfers": 0 if walk_only else int(r["transfers"] or 0),
                "first_stop": None if walk_only else r["first_stop"],
                "first_route": None if walk_only else r["first_route"],
                "walk_only": walk_only,
                "last_departure": (
                    r["departure"] if r["trip_window"] == "night_return" and not walk_only else None
                ),
            }
        trips.append(trip)
    order = {k: i for i, k in enumerate(summary["targets"])}
    trips.sort(
        key=lambda t: (
            order.get(t["destination_type"], 99),
            t["destination_id"],
            MODES.index(t["mode"]),
        )
    )
    await decorate(d.db, m, body.profile(), trips)
    ci = m.cell_index[cell_id]
    district = m.district[ci]
    return {
        "cell_id": cell_id,
        "district": m.district_names.get(district) if district else None,
        "point": [round(float(m.point[ci, 0]), 6), round(float(m.point[ci, 1]), 6)],
        "populated": bool(m.populated[ci]),
        "trips": trips,
        "fit": summary["fit"],
        "reasons": summary["reasons"],
        "fit_parts": summary["fit_parts"],
    }


@router.post("/place", dependencies=[Depends(rate_limited)])
async def place(body: PlaceRequest, d: D) -> dict[str, Any]:
    """F4.5: exact times from one point (listing address or dropped pin), no cache."""
    model = await _model(d)
    f = d.config.api.fit
    try:
        return await place_detail(d, model, body.profile.profile(), body.point, f.a, f.p)
    except ProfileError as exc:
        raise HTTPException(422, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except NoRouteError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (ValhallaError, OtpError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/route", dependencies=[Depends(rate_limited)])
async def route(body: RouteRequest, d: D) -> dict[str, Any]:
    """Geometry of one walk or bike route (F4.5); transit has no geometry in the API yet."""
    rows = await d.db.fetch(
        q.Q_DESTINATION_POINT, [body.destination_id, body.destination_id, body.destination_id]
    )
    if not rows:
        raise HTTPException(404, f"destination {body.destination_id} not found")
    profile = d.config.routing_profiles[body.mode]
    try:
        feature = await d.valhalla.route(
            body.origin,
            (float(rows[0]["lon"]), float(rows[0]["lat"])),
            profile.costing or "",
            costing_options(profile),
        )
    except NoRouteError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValhallaError as exc:
        raise HTTPException(503, str(exc)) from exc
    feature["properties"]["mode"] = body.mode
    return feature
