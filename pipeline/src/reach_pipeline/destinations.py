"""Destinations per type (meth. §3, docs/osm_tagging.md) and the address index for the search.

OSM types match `tags` (any pair), then `require` (at least one, if given) and `exclude` (none).
Points: polygons by a point inside; parks (`location: access_points`) by the points where a
walkable way crosses or touches the park boundary, merged on a `spacing_m` grid and capped at
`max_points` (config `access_points`), so one park has several points but counts once
(`destination_id` per park, `point_id` per access point).
Campus types come from `config/campus.yaml`. Everything is vectorised on GeoDataFrames in
EPSG:25832.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from reach_pipeline import campus as campus_mod
from reach_pipeline.config import Config, DestinationType
from reach_pipeline.labels import _col, _has_value, _tag_match

METRIC_CRS = "EPSG:25832"
COLUMNS = ["destination_id", "destination_type", "name", "osm_id", "point_id", "geometry"]
ADDRESS_COLUMNS = [
    "address_id",
    "street",
    "housenumber",
    "postcode",
    "city",
    "label",
    "residential",
    "geometry",
]


def osm_expressions(cfg: Config) -> list[str]:
    """`tags-filter` expressions for every OSM destination type plus the ways that give park
    access points and addressed objects."""
    exprs = [
        f"nwr/{k}={v}"
        for t in cfg.destination_types.values()
        if t.source == "osm"
        for tag in t.tags
        for k, v in tag.items()
    ]
    if any(t.location == "access_points" for t in cfg.destination_types.values()):
        exprs.append("w/highway=" + ",".join(cfg.access_points.walkable_highways))
    exprs.append("nwr/addr:housenumber")
    return list(dict.fromkeys(exprs))


def _match(features: gpd.GeoDataFrame, t: DestinationType) -> gpd.GeoDataFrame:
    hit = _tag_match(features, t.tags)
    if t.require:
        req = pd.Series(False, index=features.index)
        for cond in t.require:
            for k, v in cond.items():
                req |= _has_value(features, k, [v])
        hit &= req
    for cond in t.exclude:
        for k, v in cond.items():
            hit &= ~_has_value(features, k, [v])
    return features[hit]


def merge_same_name(sel: gpd.GeoDataFrame, radius_m: float) -> gpd.GeoDataFrame:
    """Drop features that repeat a larger feature of the same name within `radius_m` (a station
    mapped as node and as area is one destination)."""
    if len(sel) < 2:
        return sel
    sel = sel.assign(_area=sel.geometry.area).sort_values("_area", ascending=False, kind="stable")
    sel = sel.reset_index(drop=True)
    name = _col(sel, "name").to_numpy()
    left, right = sel.sindex.query(sel.geometry, predicate="dwithin", distance=radius_m)
    dup = (left < right) & (name[left] == name[right]) & (name[left] != "")
    return sel.drop(index=np.unique(right[dup])).drop(columns="_area")


def _point_rows(sel: gpd.GeoDataFrame, dtype: str) -> gpd.GeoDataFrame:
    ids = dtype + ":" + sel["osm_id"]
    return gpd.GeoDataFrame(
        {
            "destination_id": ids.to_numpy(),
            "destination_type": dtype,
            "name": _col(sel, "name").to_numpy(),
            "osm_id": sel["osm_id"].to_numpy(),
            "point_id": ids.to_numpy(),
        },
        geometry=sel.geometry.representative_point().to_numpy(),
        crs=METRIC_CRS,
    )


def access_points(
    parks: gpd.GeoDataFrame,
    ways: gpd.GeoDataFrame,
    dtype: str,
    merge_m: float,
    max_points: int,
) -> gpd.GeoDataFrame:
    """Points where walkable ways meet the boundary of each park; a park without any such point
    falls back to a point inside."""
    polys = parks[parks.geometry.area > 0].reset_index(drop=True)
    if polys.empty:
        return _point_rows(parks, dtype)
    rings = gpd.GeoDataFrame(
        {"osm_id": polys["osm_id"]}, geometry=polys.geometry.boundary, crs=METRIC_CRS
    )
    pts = gpd.GeoDataFrame(geometry=[], crs=METRIC_CRS)
    if not ways.empty:
        ways = ways.reset_index(drop=True)
        hits = gpd.sjoin(ways[["geometry"]], rings, predicate="intersects").reset_index()
        cross = shapely.intersection(
            ways.geometry.to_numpy()[hits["index"].to_numpy()],
            rings.geometry.to_numpy()[hits["index_right"].to_numpy()],
        )
        pts = gpd.GeoDataFrame(
            {"osm_id": hits["osm_id"].to_numpy()}, geometry=cross, crs=METRIC_CRS
        ).explode(index_parts=False)
        pts = pts[pts.geom_type == "Point"]
        # One point per park and merge cell (snap to a grid of merge_m).
        cell = np.floor(np.column_stack([pts.geometry.x, pts.geometry.y]) / merge_m)
        pts = pts.assign(cx=cell[:, 0], cy=cell[:, 1]).drop_duplicates(["osm_id", "cx", "cy"])
    names = polys.set_index("osm_id")["name"] if "name" in polys else None
    found = set(pts["osm_id"]) if len(pts) else set()
    rest = parks[~parks["osm_id"].isin(found)]
    out = [_point_rows(rest, dtype)]
    if len(pts):
        pts = pts.sort_values(["osm_id", "cx", "cy"]).reset_index(drop=True)
        n = pts.groupby("osm_id").cumcount()
        pts, n = pts[n < max_points], n[n < max_points]
        ids = dtype + ":" + pts["osm_id"]
        out.append(
            gpd.GeoDataFrame(
                {
                    "destination_id": ids.to_numpy(),
                    "destination_type": dtype,
                    "name": (
                        pts["osm_id"].map(names).fillna("").to_numpy() if names is not None else ""
                    ),
                    "osm_id": pts["osm_id"].to_numpy(),
                    "point_id": (ids + "#" + n.astype(str)).to_numpy(),
                },
                geometry=pts.geometry.to_numpy(),
                crs=METRIC_CRS,
            )
        )
    return gpd.GeoDataFrame(pd.concat(out, ignore_index=True), crs=METRIC_CRS)


def osm_destinations(features: gpd.GeoDataFrame, cfg: Config) -> gpd.GeoDataFrame:
    """Destinations of every OSM type (one row per point; parks have several)."""
    ways = features[
        _col(features, "highway").isin(cfg.access_points.walkable_highways)
        & features.geom_type.isin(["LineString", "MultiLineString"])
    ]
    parts = []
    for dtype, t in cfg.destination_types.items():
        if t.source != "osm":
            continue
        sel = merge_same_name(_match(features, t), cfg.destination_merge_m)
        if sel.empty:
            continue
        if t.location == "access_points":
            ap = cfg.access_points
            parts.append(access_points(sel, ways, dtype, ap.spacing_m, ap.max_points))
        else:
            parts.append(_point_rows(sel, dtype))
    if not parts:
        return gpd.GeoDataFrame(columns=COLUMNS, geometry="geometry", crs=METRIC_CRS)
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=METRIC_CRS)


def campus_destinations(c: campus_mod.Campus) -> gpd.GeoDataFrame:
    dest = campus_mod.destinations(c)
    dest["point_id"] = dest["destination_id"]
    return dest[COLUMNS]


def build(
    features: gpd.GeoDataFrame, c: campus_mod.Campus, cfg: Config, area: shapely.Geometry
) -> gpd.GeoDataFrame:
    """All destinations inside the routing area, sorted by id."""
    dest = pd.concat([osm_destinations(features, cfg), campus_destinations(c)], ignore_index=True)
    dest = gpd.GeoDataFrame(dest, crs=METRIC_CRS)
    dest = dest[dest.within(area)]
    return dest[COLUMNS].sort_values(["destination_type", "point_id"]).reset_index(drop=True)


def counts(dest: pd.DataFrame, cfg: Config) -> dict[str, int]:
    """Destinations (not points) per configured type, 0 where none was found."""
    n = dest.groupby("destination_type")["destination_id"].nunique()
    return {t: int(n.get(t, 0)) for t, d in cfg.destination_types.items() if d.source != "labels"}


def residential(features: gpd.GeoDataFrame, cfg: Config) -> pd.Series:
    """Addressed objects that may be homes (address cells, arch. O13): no shop, office or similar
    tag, and no non-residential building type."""
    ac = cfg.address_cells
    shared = pd.Series(False, index=features.index)
    for key in ac.exclude_keys:
        shared |= _col(features, key) != ""
    return ~shared & ~_col(features, "building").isin(ac.non_residential_buildings)


def addresses(features: gpd.GeoDataFrame, area: shapely.Geometry, cfg: Config) -> gpd.GeoDataFrame:
    """Address index (arch. rule 8: searched in PostGIS, no geocoder at runtime): one row per
    street, house number and postcode, at a point inside the addressed object; `residential`
    marks the ones that create address cells."""
    hn = _col(features, "addr:housenumber")
    street = _col(features, "addr:street").where(
        _col(features, "addr:street") != "", _col(features, "addr:place")
    )
    sel = features[(hn != "") & (street != "")]
    if sel.empty:
        return gpd.GeoDataFrame(columns=ADDRESS_COLUMNS, geometry="geometry", crs=METRIC_CRS)
    out = gpd.GeoDataFrame(
        {
            "street": street[sel.index].str.strip().to_numpy(),
            "housenumber": hn[sel.index].str.strip().to_numpy(),
            "postcode": _col(sel, "addr:postcode").to_numpy(),
            "city": _col(sel, "addr:city").to_numpy(),
            "area": sel.geometry.area.to_numpy(),
            "residential": residential(sel, cfg).to_numpy(),
        },
        geometry=sel.geometry.representative_point().to_numpy(),
        crs=METRIC_CRS,
    )
    out = out[out.within(area)]
    out = out.sort_values(["street", "housenumber", "area"], ascending=[True, True, False])
    res = out.groupby(["street", "housenumber", "postcode"])["residential"].transform("any")
    out = out.assign(residential=res)
    out = out.drop_duplicates(["street", "housenumber", "postcode"]).reset_index(drop=True)
    place = (out["postcode"] + " " + out["city"]).str.strip()
    out["label"] = (
        out["street"] + " " + out["housenumber"] + np.where(place != "", ", " + place, "")
    )
    out["address_id"] = np.arange(1, len(out) + 1)
    return out[ADDRESS_COLUMNS]
