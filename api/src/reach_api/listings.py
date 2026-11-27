"""Listings (F4.6, architecture O24): the latest WG-Gesucht snapshot from `listings.listings`.

The fit of a listing is the fit of its Zensus cell (same model and profile as POST /api/fit);
point routing per listing (F4.5) is not built yet, so every listing says `approximate`.
Without a published snapshot both endpoints answer with an empty list.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from reach_api.deps import Deps, deps, rate_limited
from reach_api.fit import ProfileError, fit_response
from reach_api.routes import FitRequest

router = APIRouter(prefix="/api")
D = Annotated[Deps, Depends(deps)]

Q_EXISTS = "SELECT to_regclass('listings.listings') IS NOT NULL AS ok"
Q_LISTINGS = """
SELECT listing_id, source_url, kind, title, rent_total_eur, rent_cold_eur, deposit_eur,
       size_m2, flat_size_m2, rooms, household_size, available_from::text AS available_from,
       available_to::text AS available_to, furnished, features, district, postcode,
       address_text, geocode_precision, cell_id, image_urls, description_excerpt,
       first_seen::text AS first_seen, last_seen::text AS last_seen,
       ST_X(ST_Transform(geom, 4326)) AS lon, ST_Y(ST_Transform(geom, 4326)) AS lat
FROM listings.listings
ORDER BY first_seen DESC, listing_id
"""


def shape(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in row.items() if k not in ("lon", "lat")}
    out["point"] = None if row.get("lon") is None else [round(row["lon"], 6), round(row["lat"], 6)]
    for key in ("size_m2", "flat_size_m2", "rooms"):
        if out.get(key) is not None:
            out[key] = float(out[key])
    out["approximate"] = True
    return out


async def rows(d: Deps) -> list[dict[str, Any]]:
    exists = await d.db.fetch(Q_EXISTS)
    if not exists or not exists[0]["ok"]:
        return []
    return [shape(r) for r in await d.db.fetch(Q_LISTINGS)]


@router.get("/listings")
async def listings(d: D) -> list[dict[str, Any]]:
    return await rows(d)


@router.post("/listings/fit", dependencies=[Depends(rate_limited)])
async def listings_fit(body: FitRequest, d: D) -> list[dict[str, Any]]:
    """Listings with the fit and weekly travel time of their cell, best first."""
    items = await rows(d)
    if not items:
        return []
    model = await d.models.get()
    f = d.config.api.fit
    try:
        cells = fit_response(model, body.profile(), f.a, f.p)["cells"]
    except ProfileError as exc:
        raise HTTPException(422, str(exc)) from exc
    for item in items:
        fit, weekly, _ = cells.get(item["cell_id"] or "", (None, None, 0))
        item["fit"], item["weekly_min"] = fit, weekly
    items.sort(key=lambda x: (x["fit"] is None, -(x["fit"] or 0), x["rent_total_eur"] or 1e9))
    return items
