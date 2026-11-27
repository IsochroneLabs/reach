"""Points of interest of a trip list: where each destination is, the campus share and the OSM
details (opening hours, website, wheelchair) so the app can show and label the places it routes
to (notes N29). Details come from `current.destination_details`; older runs without that table
give points only.
"""

from __future__ import annotations

from typing import Any

from reach_api.db import Database
from reach_api.fit import campus_weights
from reach_api.model import CAMPUS, Model

Q_DETAILS_EXIST = "SELECT to_regclass('current.destination_details') IS NOT NULL AS ok"
_POINTS = """
SELECT destination_id, geom FROM current.destinations WHERE destination_id = ANY(%(ids)s)
UNION ALL
SELECT destination_id, geom FROM current.destination_labels WHERE destination_id = ANY(%(ids)s)
"""
Q_POINTS = f"""
SELECT p.destination_id,
       ST_X(ST_Transform(p.geom, 4326)) AS lon, ST_Y(ST_Transform(p.geom, 4326)) AS lat
FROM ({_POINTS}) p
"""
Q_POINTS_DETAILS = f"""
SELECT p.destination_id,
       ST_X(ST_Transform(p.geom, 4326)) AS lon, ST_Y(ST_Transform(p.geom, 4326)) AS lat,
       dd.opening_hours, dd.website, dd.wheelchair, dd.open_in_window
FROM ({_POINTS}) p
LEFT JOIN current.destination_details dd USING (destination_id)
"""
DETAILS = ("opening_hours", "website", "wheelchair")


def campus_shares(model: Model, profile: dict[str, Any]) -> dict[str, float]:
    """`campus_site:<id>` → share of the student's campus time (weights normalised to 1)."""
    weights = campus_weights(model, profile)
    total = sum(w for _, w in weights) or 1.0
    return {f"{CAMPUS}:{site}": w / total for site, w in weights if w > 0}


async def decorate(
    db: Database, model: Model, profile: dict[str, Any], trips: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Add `point`, campus `share` and OSM details to each trip (in place, also returned)."""
    ids = sorted({t["destination_id"] for t in trips})
    if not ids:
        return trips
    exists = await db.fetch(Q_DETAILS_EXIST)
    with_details = bool(exists and exists[0]["ok"])
    rows = await db.fetch(Q_POINTS_DETAILS if with_details else Q_POINTS, {"ids": ids})
    info = {r["destination_id"]: r for r in rows}
    shares = campus_shares(model, profile)
    for t in trips:
        r = info.get(t["destination_id"])
        if r is not None and r.get("lon") is not None:
            t["point"] = [round(float(r["lon"]), 6), round(float(r["lat"]), 6)]
            for key in DETAILS:
                if r.get(key):
                    t[key] = r[key]
            if r.get("open_in_window") is not None:
                t["open_in_window"] = bool(r["open_in_window"])
        if t["destination_id"] in shares:
            t["share"] = round(shares[t["destination_id"]], 3)
    return trips
