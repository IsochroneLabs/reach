"""Live endpoints calling Valhalla (arch. §6.5 rules 8–12, §9).

Every point is snapped to the centre of the 100 m Zensus grid cell under it, scored or not, so
answers are cached per (run, cell, profile) and polygons, routes and counts describe the same
start (rule 8). The point (or its cell centre) must lie inside the city boundary, or inside a
scored cell; anything else is rejected before any Valhalla call (rule 12). Scored cells take their
reachable facilities from `current.reachable`; live matrices (grid cells without residents,
catchments) use the costing options of `current.profiles`, the prefilter of the count stage
(O20) and their own client with the timeout and concurrency of `api.live_matrix`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator

from reach_api.cache import LRUCache
from reach_api.db import Location, Profile
from reach_api.deps import Deps, Run, current_run, deps, rate_limited
from reach_api.valhalla import LonLat

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", dependencies=[Depends(rate_limited)])

DepsDep = Annotated[Deps, Depends(deps)]
# Class order from worst to best (methodology §4); used only to pick the weakest category.
CLASS_ORDER = {"lack": 0, "insufficient": 1, "sufficient": 2}


class Point(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    profile: str


class IsochroneRequest(Point):
    # forward: where you get from the cell; reverse: from where people reach the cell
    direction: Literal["forward", "reverse"] = "forward"


class CatchmentRequest(BaseModel):
    profile: str
    facility_id: str | None = None
    lon: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    # A recommended zone (recommend stage) with the category it is recommended for.
    candidate_id: str | None = None
    category: str | None = None

    @model_validator(mode="after")
    def _one_target(self):
        has_point = self.lon is not None and self.lat is not None
        targets = [self.facility_id is not None, has_point, self.candidate_id is not None]
        if sum(targets) != 1:
            raise ValueError("give exactly one of facility_id, lon and lat, or candidate_id")
        if (self.candidate_id is None) != (self.category is None):
            raise ValueError("candidate_id needs category (and category needs candidate_id)")
        return self


async def _locate(d: Deps, lon: float, lat: float) -> Location:
    loc = await d.db.locate(lon, lat)
    if not loc.allowed:
        raise HTTPException(422, "point outside the city boundary and outside every scored cell")
    return loc


def _options(p: Profile) -> tuple[str, dict[str, Any]]:
    return p.costing, p.costing_options


def _reach_m(d: Deps, p: Profile) -> float:
    if p.profile_id not in d.config.profiles:
        raise HTTPException(500, f"profile {p.profile_id!r} of the run is missing in the config")
    return d.config.prefilter_reach_m(p.profile_id, p.speed_kmh, p.time_budget_min)


def _cell(loc: Location) -> dict[str, Any]:
    return {
        "cell_id": loc.cell_id,
        "scored": loc.scored,
        "status": loc.status,
        "population": loc.population,
        "district_id": loc.district_id,
        "origin": [round(loc.lon, 6), round(loc.lat, 6)],
    }


async def _isochrone(d: Deps, origin: LonLat, p: Profile, reverse: bool = False) -> dict:
    iso = d.config.api.isochrone
    costing, options = _options(p)
    return await d.valhalla.isochrone(
        origin, costing, options, iso.contours_min, iso.generalize_m, iso.denoise, reverse
    )


def _weakest(scores: list[dict[str, Any]]) -> str | None:
    """Category with the worst class, ties broken by the larger deficit; None if all are
    sufficient or nothing is precomputed."""
    worst = sorted(scores, key=lambda s: (CLASS_ORDER[s["class"]], -(s["deficit"] or 0)))
    return worst[0]["category"] if worst and worst[0]["class"] != "sufficient" else None


def _by_category(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Facilities per category, nearest first; `_point` (lon/lat) is the routing target."""
    by_category: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_category.setdefault(r["category"], []).append(
            {
                "facility_id": r["facility_id"],
                "name": r["name"],
                "time_s": r["time_s"],
                "time_min": round(r["time_s"] / 60, 2),
                "_point": (r["lon"], r["lat"]),
            }
        )
    for items in by_category.values():
        items.sort(key=lambda f: (f["time_s"], f["facility_id"]))
    return by_category


async def _reachable_precomputed(
    d: Deps, loc: Location, p: Profile
) -> dict[str, list[dict[str, Any]]]:
    """Scored cell: the facilities `count` found within the budget (`current.reachable`), so
    list and count match the map by construction (arch. §6.5 rule 8)."""
    return _by_category(await d.db.reachable(loc.cell_id, p.profile_id, loc.x, loc.y))


async def _reachable_live(d: Deps, loc: Location, p: Profile) -> dict[str, list[dict[str, Any]]]:
    """Grid cell without residents: one live matrix (`api.live_matrix` timeout and concurrency)
    from the origin to all facility points within the prefilter reach, all categories at once,
    with the run's costing and the count stage's prefilter (O20)."""
    rows = await d.db.facility_points_near(loc.x, loc.y, _reach_m(d, p))
    points: dict[tuple[str, int], LonLat] = {}
    for r in rows:
        points.setdefault((r["facility_id"], r["point_id"]), (r["lon"], r["lat"]))
    costing, options = _options(p)
    times = await d.live_matrix.matrix(
        [(loc.lon, loc.lat)], list(points.values()), costing, options
    )
    time_of = dict(zip(points, times[0] if times else [], strict=True))
    budget_s = p.time_budget_min * 60
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        t = time_of[(r["facility_id"], r["point_id"])]
        if t is None or t > budget_s:
            continue
        key = (r["category"], r["facility_id"])
        if key not in best or t < best[key]["time_s"]:
            best[key] = {**r, "time_s": t}
    return _by_category(list(best.values()))


@router.post("/inspect")
async def inspect(body: Point, d: DepsDep) -> Response:
    """Pin-drop inspector: precomputed values of the cell (identical to the map), the 5/10/15
    minute isochrone, the facilities reachable per category with times and the route to the
    nearest one per category, all from the cell origin; plus the weakest category. Scored cells
    answer from the published run (`source: precomputed`), grid cells without residents from a
    live matrix (`source: live`)."""
    run = await current_run(d)
    p = run.profile(body.profile)
    loc = await _locate(d, body.lon, body.lat)
    key = (run.run_id, "inspect", loc.cell_id, p.profile_id)
    return await _serve(d.live_cache, key, lambda: _inspect(d, run, p, loc))


async def _inspect(d: Deps, run: Run, p: Profile, loc: Location) -> dict[str, Any]:
    scores, transit = (
        await d.db.cell_values(loc.cell_id, p.profile_id) if loc.scored else ([], None)
    )
    origin = (loc.lon, loc.lat)
    listing = _reachable_precomputed if loc.scored else _reachable_live
    isochrone, reachable = await asyncio.gather(_isochrone(d, origin, p), listing(d, loc, p))
    costing, options = _options(p)
    categories = sorted(run.categories)
    routes = await asyncio.gather(
        *(
            d.valhalla.route(origin, reachable[c][0]["_point"], costing, options)
            for c in categories
            if c in reachable
        )
    )
    route_of = dict(zip([c for c in categories if c in reachable], routes, strict=True))
    precomputed = {s["category"]: s for s in scores}
    source = "precomputed" if loc.scored else "live"
    names = {c.id: c.name for c in d.config.categories}
    return {
        "run_id": run.run_id,
        "profile_id": p.profile_id,
        "cell": _cell(loc),
        "source": source,
        "precomputed": ({"categories": scores, "transit": transit} if loc.scored else None),
        "weakest_category": _weakest(scores),
        "isochrone": isochrone,
        "categories": [
            {
                "category": c,
                "name": names.get(c, c),
                # Scored cells: count and list from the run (equal by construction).
                "count": precomputed[c]["count"] if c in precomputed else len(reachable.get(c, [])),
                "count_source": source,
                "reachable": [
                    {k: v for k, v in f.items() if k != "_point"} for f in reachable.get(c, [])
                ],
                "nearest_route": route_of.get(c),
            }
            for c in categories
        ],
    }


@router.post("/isochrone")
async def isochrone(body: IsochroneRequest, d: DepsDep) -> Response:
    """Isochrone of the cell origin in one direction (display only, rule 9): `forward` = where
    you get within the contours, `reverse` = from where the origin is reached; on slopes the two
    differ. `/api/inspect` always carries the forward one."""
    run = await current_run(d)
    p = run.profile(body.profile)
    loc = await _locate(d, body.lon, body.lat)
    key = (run.run_id, "isochrone", loc.cell_id, p.profile_id, body.direction)

    async def build() -> dict[str, Any]:
        iso = await _isochrone(d, (loc.lon, loc.lat), p, reverse=body.direction == "reverse")
        return {
            "run_id": run.run_id,
            "profile_id": p.profile_id,
            "cell": _cell(loc),
            "direction": body.direction,
            "isochrone": iso,
        }

    return await _serve(d.live_cache, key, build)


@router.post("/catchment")
async def catchment(body: CatchmentRequest, d: DepsDep) -> Response:
    """Residents reaching a facility (or a point) within the budget: matrix from the scored
    cells within the prefilter reach to the facility's routing points, plus the reverse
    5/10/15 minute isochrone (display only). A recommended zone (`candidate_id`, `category`)
    answers with the catchment the recommender used (`current.recommendation_catchments`), so
    the numbers match the recommendation; only the isochrone is live."""
    run = await current_run(d)
    p = run.profile(body.profile)
    if body.candidate_id is not None:
        return await _candidate_catchment(d, run, p, body.candidate_id, body.category)
    if body.facility_id is not None:
        facility = await d.db.facility(body.facility_id)
        if facility is None:
            raise HTTPException(404, f"unknown facility {body.facility_id!r}")
        target = {
            "kind": "facility",
            "facility_id": facility["facility_id"],
            "name": facility["name"],
            "categories": facility["categories"],
        }
        anchor = (facility["lon"], facility["lat"])
        points = facility["points"] or [
            {"x": None, "y": None, "lon": facility["lon"], "lat": facility["lat"]}
        ]
        key = (run.run_id, "catchment", "facility", facility["facility_id"], p.profile_id)
        categories = facility["categories"]
    else:
        loc = await _locate(d, body.lon, body.lat)
        target = {"kind": "cell", **_cell(loc)}
        anchor = (loc.lon, loc.lat)
        points = [{"x": loc.x, "y": loc.y, "lon": loc.lon, "lat": loc.lat}]
        key = (run.run_id, "catchment", "cell", loc.cell_id, p.profile_id)
        categories = []

    async def build() -> dict[str, Any]:
        return await _catchment(d, run, p, target, anchor, points, categories)

    return await _serve(d.live_cache, key, build)


async def _catchment(
    d: Deps,
    run: Run,
    p: Profile,
    target: dict[str, Any],
    anchor: LonLat,
    points: list[dict[str, Any]],
    categories: list[str],
) -> dict[str, Any]:
    xy = [(pt["x"], pt["y"]) for pt in points if pt["x"] is not None]
    cells = await d.db.cells_near(xy, _reach_m(d, p)) if xy else []
    costing, options = _options(p)
    matrix_task = d.live_matrix.matrix(
        [(c["lon"], c["lat"]) for c in cells],
        [(pt["lon"], pt["lat"]) for pt in points],
        costing,
        options,
    )
    isochrone, times = await asyncio.gather(_isochrone(d, anchor, p, reverse=True), matrix_task)
    budget_s = p.time_budget_min * 60
    reaching = [
        c
        for c, row in zip(cells, times, strict=True)
        if any(t is not None and t <= budget_s for t in row)
    ]
    ids = [c["cell_id"] for c in reaching]
    by_class = {
        c: await d.db.residents_by_class(ids, c, p.profile_id) if ids else {}
        for c in categories
        if c in run.categories
    }
    return {
        "run_id": run.run_id,
        "profile_id": p.profile_id,
        "target": target,
        "source": "live",
        "residents": sum(c["population"] for c in reaching),
        "cells": len(reaching),
        "cell_ids": ids,
        "residents_by_class": by_class,
        "isochrone": isochrone,
    }


async def _candidate_catchment(
    d: Deps, run: Run, p: Profile, candidate_id: str, category: str
) -> Response:
    if category not in run.categories:
        raise HTTPException(422, f"unknown category {category!r}")
    key = (run.run_id, "catchment", "candidate", candidate_id, category, p.profile_id)

    async def build() -> dict[str, Any]:
        # inside the cached build: a hit needs no query; a 404 is not cached (errors never are)
        r = await d.db.recommendation(candidate_id, category, p.profile_id)
        if r is None:
            raise HTTPException(
                404, f"no recommendation {candidate_id!r} for {category!r} and {p.profile_id!r}"
            )
        ids = list(r["cell_ids"])
        isochrone = await _isochrone(d, (r["lon"], r["lat"]), p, reverse=True)
        return {
            "run_id": run.run_id,
            "profile_id": p.profile_id,
            "target": {
                "kind": "candidate",
                "candidate_id": candidate_id,
                "category": category,
                "rank": r["rank"],
                "population_gain": r["population_gain"],
                "residents_gaining_access": r["residents_gaining_access"],
                "residents_to_sufficient": r["residents_to_sufficient"],
                "origin": [round(r["lon"], 6), round(r["lat"], 6)],
            },
            "source": "precomputed",
            "residents": int(r["residents"]),
            "cells": len(ids),
            "cell_ids": ids,
            "residents_by_class": {
                category: await d.db.residents_by_class(ids, category, p.profile_id) if ids else {}
            },
            "isochrone": isochrone,
        }

    return await _serve(d.live_cache, key, build)


@router.post("/expansion")
async def expansion(body: Point, d: DepsDep) -> Response:
    """Street edges reached within the facility budget from the cell origin (rule 11: only on
    demand, limited to the budget); LineStrings with `duration` in seconds."""
    run = await current_run(d)
    p = run.profile(body.profile)
    loc = await _locate(d, body.lon, body.lat)
    key = (run.run_id, "expansion", loc.cell_id, p.profile_id)

    async def build() -> dict[str, Any]:
        costing, options = _options(p)
        edges = await d.valhalla.expansion((loc.lon, loc.lat), costing, options, p.time_budget_min)
        return {
            "run_id": run.run_id,
            "profile_id": p.profile_id,
            "cell": _cell(loc),
            "budget_min": p.time_budget_min,
            **edges,
        }

    return await _serve(d.expansion_cache, key, build)


def _dumps(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


async def _serve(
    cache: LRUCache, key: tuple[str, ...], build: Callable[[], Awaitable[dict[str, Any]]]
) -> Response:
    """Answer from the cache, or build it once (concurrent misses of the same key share one
    build, rule 10). The cache holds the serialized body: JSON bytes are an order of magnitude
    smaller than the same coordinates as Python lists."""
    fresh: list[bytes] = []

    async def compute() -> bytes:
        result = await build()
        fresh.append(_dumps({**result, "cached": False}))
        return _dumps({**result, "cached": True})

    body, built_here = await cache.get_or_compute(key, compute)
    return Response(content=fresh[0] if built_here else body, media_type="application/json")
