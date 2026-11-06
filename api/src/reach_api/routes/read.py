"""Read endpoints from the `current` schema (arch. §9). Every answer belongs to one published
run: the ETag carries its run id, so browsers revalidate and get 304 until the next publish,
and the larger bodies are cached in process per run."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from reach_api.db import TRANSIT
from reach_api.deps import Deps, current_run, deps

router = APIRouter(prefix="/api")
# Every read endpoint also answers HEAD (same headers incl. ETag, no body).
GET_HEAD = ["GET", "HEAD"]

GEOJSON = "application/geo+json"
# Revalidate on every use (cheap 304), so a new run shows up at once.
CACHE_CONTROL = "no-cache"


def _etag(*parts: str) -> str:
    return 'W/"' + ":".join(parts) + '"'


def _not_modified(request: Request, etag: str) -> bool:
    sent = request.headers.get("if-none-match", "")
    return etag in [t.strip() for t in sent.split(",")] or sent.strip() == "*"


async def _cached_body(
    request: Request,
    d: Deps,
    key: tuple[str, ...],
    media_type: str,
    build: Callable[[], Awaitable[str]],
) -> Response:
    """304 if the client has this run's version, else the body (from the read cache)."""
    etag = _etag(*key)
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if _not_modified(request, etag):
        return Response(status_code=304, headers=headers)
    body = d.read_cache.get(key)
    if body is None:
        body = await build()
        d.read_cache.put(key, body)
    return Response(content=body, media_type=media_type, headers=headers)


def _json(request: Request, etag: str, content: Any) -> Response:
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if _not_modified(request, etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=content, headers=headers)


DepsDep = Annotated[Deps, Depends(deps)]


@router.api_route("/meta", methods=GET_HEAD)
async def meta(request: Request, d: DepsDep) -> Response:
    """Run id, data dates and sources, validation summary, profiles, categories, classes.

    `transit_budget_min` (walking time to stops) is null for profiles without transit."""
    run = await current_run(d)
    m = await d.db.meta(run.run_id)
    names = {c.id: c.name for c in d.config.categories}
    transit_budget = d.config.time_budgets_min.transit
    checks = m["checks"]
    counts = {s: sum(1 for c in checks if c["status"] == s) for s in ("ok", "warn", "fail")}
    content = {
        "run": m["run"],
        "data_sources": m["data_sources"],
        "validation": {**counts, "issues": [c for c in checks if c["status"] != "ok"]},
        "profiles": [
            {
                "profile_id": p.profile_id,
                "costing": p.costing,
                "speed_kmh": p.speed_kmh,
                "time_budget_min": p.time_budget_min,
                "transit": p.profile_id in run.transit_profiles,
                "transit_budget_min": (
                    transit_budget if p.profile_id in run.transit_profiles else None
                ),
            }
            for p in run.profiles.values()
        ],
        "categories": [
            {"id": c, "name": names.get(c, c), "k": k} for c, k in run.categories.items()
        ],
        "transit_classes": [
            {"class": t["class"], "lower": t["lower"], "upper": t["upper"]}
            for t in m["thresholds"]
            if t["category"] == TRANSIT
        ],
    }
    # Category names and the transit budget come from the config, not the run: they are part
    # of the version.
    tagged = {"names": names, "transit_budget_min": transit_budget}
    names_tag = hashlib.sha256(json.dumps(tagged, sort_keys=True).encode()).hexdigest()[:8]
    return _json(request, _etag(run.run_id, "meta", names_tag), _jsonable(content))


@router.api_route("/districts", methods=GET_HEAD)
async def districts(request: Request, d: DepsDep) -> Response:
    """District polygons (EPSG:4326) with residents and cell counts."""
    run = await current_run(d)
    return await _cached_body(
        request, d, (run.run_id, "districts"), GEOJSON, lambda: d.db.districts_geojson(run.run_id)
    )


@router.api_route("/districts/{district_id}/scores", methods=GET_HEAD)
async def district_scores(
    request: Request,
    d: DepsDep,
    district_id: str,
    profile: Annotated[str | None, Query()] = None,
) -> Response:
    """Shares per class, deficit sum, residents lacking access and ranks among districts, per
    category × profile (from `district_scores`)."""
    run = await current_run(d)
    if profile is not None:
        run.profile(profile)
    result = await d.db.district_scores(district_id, profile)
    if result is None:
        raise HTTPException(404, f"unknown district {district_id!r}")
    etag = _etag(run.run_id, "district", district_id, profile or "*")
    return _json(request, etag, _jsonable({"run_id": run.run_id, **result}))


@router.api_route("/cells", methods=GET_HEAD)
async def cells(
    request: Request,
    d: DepsDep,
    category: Annotated[str, Query()],
    profile: Annotated[str, Query()],
) -> Response:
    """Scored cells as GeoJSON polygons (EPSG:4326, 6 decimals) with count, nearest time, class
    and deficit; `category=transit` gives departures, stops and the transit class."""
    run = await current_run(d)
    run.profile(profile)
    run.check_category(category, profile)
    return await _cached_body(
        request,
        d,
        (run.run_id, "cells", category, profile),
        GEOJSON,
        lambda: d.db.cells_geojson(run.run_id, category, profile),
    )


@router.api_route("/recommendations", methods=GET_HEAD)
async def recommendations(
    request: Request,
    d: DepsDep,
    category: Annotated[str | None, Query()] = None,
    profile: Annotated[str | None, Query()] = None,
) -> Response:
    """Ranked recommendation zones; empty until the recommender exists (P7)."""
    run = await current_run(d)
    if profile is not None:
        run.profile(profile)
        if category is not None:
            run.check_category(category, profile)
    content = {
        "type": "FeatureCollection",
        "run_id": run.run_id,
        "available": False,
        "features": [],
    }
    return _json(request, _etag(run.run_id, "recommendations"), content)


def _jsonable(value: Any) -> Any:
    """Dates and timestamps (psycopg `date`/`datetime`) as ISO strings."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
