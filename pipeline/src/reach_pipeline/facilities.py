"""Facilities from OSM: tag → category mapping, de-duplication and routing points (meth. §2).

- Nodes stay points (`kind = node`); polygons get one representative point (`representative`).
- Categories with `location: access_points` (parks, playgrounds) get access points on the
  outer boundary: crossings with walkable ways (a way running along the boundary gives the end
  points of the shared part), else one point every `spacing_m`; at most `max_points`, chosen
  evenly spaced around the boundary (`access`).
- A node and an area with the same category tag that overlap are one facility: for point
  categories the node is kept (it marks the shop or entrance), for access-point categories the
  area is kept (it has the boundary).
- Informative OSM tags (`facility_tags`, shown in the app, never used for counting) are kept per
  facility as a JSON object in `tags`; areas also keep a simplified `area_geometry`.
"""

from __future__ import annotations

import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from reach_pipeline.config import AccessPoints, Category

METRIC_CRS = "EPSG:25832"
_POLYGONAL = ("Polygon", "MultiPolygon")
# Access points closer than this along one boundary are the same point (metres).
_SAME_POINT_M = 1.0
# OSM tag values are at most 255 characters; control characters (jsonb rejects NUL) are dropped.
MAX_TAG_LEN = 255
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _clean(value: object) -> str:
    return _CONTROL.sub(" ", value).strip()[:MAX_TAG_LEN] if isinstance(value, str) else ""


def _tags_json(features: gpd.GeoDataFrame, keys: list[str]) -> pd.Series:
    """The informative tags of every feature as a JSON object text (`{}` if it has none)."""
    present = [k for k in keys if k in features.columns]
    if not present:
        return pd.Series("{}", index=features.index)
    records = features[present].astype(object).to_dict("records")  # one row per facility
    return pd.Series(
        [
            json.dumps(
                {k: c for k, v in r.items() if (c := _clean(v))},
                ensure_ascii=False,
                sort_keys=True,
            )
            for r in records
        ],
        index=features.index,
    )


def _area_outlines(geoms: gpd.GeoSeries, tolerance_m: float) -> np.ndarray:
    """Simplified MultiPolygon per polygonal geometry, None for points (display only)."""
    values = np.full(len(geoms), None, dtype=object)
    is_area = geoms.geom_type.isin(_POLYGONAL).to_numpy()
    if is_area.any():
        simple = shapely.simplify(geoms.values[is_area], tolerance_m, preserve_topology=True)
        parts, idx = shapely.get_parts(simple, return_index=True)
        values[is_area] = shapely.multipolygons(parts, indices=idx)
    return values


def _condition_mask(features: gpd.GeoDataFrame, conditions: list[dict[str, str]]) -> np.ndarray:
    """True where a feature matches any `key: value` condition; `;`-separated OSM values match
    if any part equals the value."""
    mask = np.zeros(len(features), dtype=bool)
    for cond in conditions:
        ((key, value),) = cond.items()
        if key in features.columns:
            pattern = rf"(?:^|;)\s*{re.escape(value)}\s*(?:;|$)"
            found = features[key].astype("string").str.contains(pattern, regex=True, na=False)
            mask |= found.to_numpy(dtype=bool)
    return mask


def _with_defining_tag(features: gpd.GeoDataFrame, cat: Category) -> gpd.GeoDataFrame:
    """Features with a defining tag of the category that pass `require` (before `exclude`)."""
    parts = []
    for tag in cat.tags:
        ((key, value),) = tag.items()
        if key in features.columns:
            parts.append(features[features[key] == value])
    if not parts:
        return features.iloc[0:0]
    hit = pd.concat(parts)
    hit = hit[~hit.index.duplicated()]
    return hit[_condition_mask(hit, cat.require)] if cat.require else hit


def exclusion_stats(
    features: gpd.GeoDataFrame, categories: list[Category]
) -> dict[str, dict[str, int]]:
    """Per category with `exclude` conditions: features dropped by them (`excluded`, a feature
    counts once) and per condition (`key=value`, informative; one feature can match several)."""
    stats: dict[str, dict[str, int]] = {}
    for cat in categories:
        if not cat.exclude:
            continue
        hit = _with_defining_tag(features, cat)
        per = {}
        for cond in cat.exclude:
            ((key, value),) = cond.items()
            per[f"{key}={value}"] = int(_condition_mask(hit, [cond]).sum())
        stats[cat.id] = {
            "excluded": int(_condition_mask(hit, cat.exclude).sum()),
            **per,
        }
    return stats


def subtype_gap(
    features: gpd.GeoDataFrame, base: dict[str, str], type_keys: list[str]
) -> tuple[int, list[str]]:
    """Number of features with the `base` tag and the `name`/OSM id of those without any of the
    `type_keys` (a type tag with a non-blank value)."""
    ((key, value),) = base.items()
    if key not in features.columns:
        return 0, []
    sites = features[features[key] == value]
    typed = np.zeros(len(sites), dtype=bool)
    for k in type_keys:
        if k in sites.columns:
            typed |= sites[k].astype("string").str.strip().fillna("").ne("").to_numpy(dtype=bool)
    untyped = sites[~typed]
    ids = untyped["osm_id"].astype(str)
    labels = untyped["name"].where(untyped["name"].notna(), ids) if "name" in untyped else ids
    return len(sites), sorted(labels.astype(str))


def match_categories(
    features: gpd.GeoDataFrame,
    categories: list[Category],
    tag_keys: list[str] | tuple = (),
    outline_simplify_m: float = 2.0,
) -> gpd.GeoDataFrame:
    """One row per (feature, category, tag) that matches; columns `facility_id`, `category`,
    `tag` (`key=value`), `name`, `tags` (JSON of `tag_keys`), `area_geometry` (display outline of
    areas, else None), `is_area`, geometry."""
    frames = []
    for cat in categories:
        for tag in cat.tags:
            ((key, value),) = tag.items()
            if key not in features.columns:
                continue
            hit = features[features[key] == value]
            if cat.require:
                hit = hit[_condition_mask(hit, cat.require)]
            if cat.exclude:
                hit = hit[~_condition_mask(hit, cat.exclude)]
            # tags and outlines only for the matched rows, not for every exported feature
            info = _tags_json(hit, list(tag_keys))
            outline = _area_outlines(hit.geometry, outline_simplify_m)
            frames.append(
                gpd.GeoDataFrame(
                    {
                        "facility_id": hit["osm_id"].to_numpy(),
                        "category": cat.id,
                        "tag": f"{key}={value}",
                        "name": hit["name"].to_numpy() if "name" in hit else None,
                        "tags": info.to_numpy(),
                        "area_geometry": outline,
                    },
                    geometry=hit.geometry.values,
                    crs=METRIC_CRS,
                )
            )
    if not frames:
        return gpd.GeoDataFrame(
            columns=[
                "facility_id",
                "category",
                "tag",
                "name",
                "tags",
                "area_geometry",
                "is_area",
                "geometry",
            ],
            geometry="geometry",
            crs=METRIC_CRS,
        )
    matched = pd.concat(frames, ignore_index=True)
    matched["is_area"] = matched.geom_type.isin(_POLYGONAL)
    # A feature with two tags of the same category (amenity=kindergarten + childcare) counts once.
    return matched.drop_duplicates(["facility_id", "category"], ignore_index=True)


def dedupe(matched: gpd.GeoDataFrame, categories: list[Category]) -> gpd.GeoDataFrame:
    """Drop the duplicate of a node + area pair with the same category and tag (module doc)."""
    access_cats = {c.id for c in categories if c.location == "access_points"}
    nodes = matched[~matched["is_area"]]
    areas = matched[matched["is_area"]]
    pairs = gpd.sjoin(nodes, areas, predicate="within", lsuffix="node", rsuffix="area")
    pairs = pairs[
        (pairs["category_node"] == pairs["category_area"])
        & (pairs["tag_node"] == pairs["tag_area"])
    ]
    is_access = pairs["category_node"].isin(access_cats)
    drop_nodes = pairs.index[is_access]
    drop_areas = pairs.loc[~is_access, "index_area"]
    return matched.drop(index=drop_nodes.union(pd.Index(drop_areas))).reset_index(drop=True)


def _outer_boundaries(polygons: gpd.GeoSeries) -> np.ndarray:
    """Exterior rings of each (Multi)Polygon as one MultiLineString per input row."""
    parts, idx = shapely.get_parts(polygons.values, return_index=True)
    rings = shapely.get_exterior_ring(parts)
    return shapely.multilinestrings(rings, indices=idx)


def access_points(
    areas: gpd.GeoDataFrame, ways: gpd.GeoSeries, cfg: AccessPoints
) -> gpd.GeoDataFrame:
    """Access points per area (`facility_id` column); returns `facility_id`, geometry."""
    if areas.empty:
        return gpd.GeoDataFrame({"facility_id": []}, geometry=[], crs=METRIC_CRS)
    bounds = _outer_boundaries(areas.geometry)
    ids = areas["facility_id"].to_numpy()

    # Crossings of walkable ways with the boundary; shared stretches give their end points.
    way_arr = ways.values
    a_idx, w_idx = shapely.STRtree(way_arr).query(bounds, predicate="intersects")
    inter = shapely.intersection(bounds[a_idx], way_arr[w_idx])
    parts, p_idx = shapely.get_parts(inter, return_index=True)
    is_line = shapely.get_type_id(parts) == 1
    parts = np.where(is_line, shapely.boundary(parts), parts)
    points, q_idx = shapely.get_parts(parts, return_index=True)
    owner = a_idx[p_idx[q_idx]]
    keep = shapely.get_type_id(points) == 0
    crossings = pd.DataFrame({"area": owner[keep], "geometry": points[keep]})

    # Fallback for areas without any crossing: one point every spacing_m along the boundary.
    without = np.setdiff1d(np.arange(len(areas)), crossings["area"].unique())
    lengths = shapely.length(bounds[without])
    n = np.maximum(1, np.floor(lengths / cfg.spacing_m).astype(int))
    rep = np.repeat(without, n)
    dist = (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)) * cfg.spacing_m
    fallback = pd.DataFrame(
        {"area": rep, "geometry": shapely.line_interpolate_point(bounds[rep], dist)}
    )

    pts = pd.concat([crossings, fallback], ignore_index=True)
    pts["pos"] = shapely.line_locate_point(
        bounds[pts["area"].to_numpy()], pts["geometry"].to_numpy()
    )
    pts["key"] = np.round(pts["pos"] / _SAME_POINT_M)
    pts = pts.drop_duplicates(["area", "key"]).sort_values(["area", "pos"], ignore_index=True)

    # At most max_points per area, evenly spaced around the closed boundary: split the ranks
    # 0..size-1 into max_points buckets of size/max_points and keep the first rank of each
    # (positions ceil(j * size / max_points)), so the wrap-around gap is no smaller than others.
    rank = pts.groupby("area").cumcount().to_numpy()
    size = pts.groupby("area")["pos"].transform("size").to_numpy()
    m = cfg.max_points
    bucket = np.floor(rank * m / size)
    prev_bucket = np.floor((rank - 1) * m / size)
    selected = (size <= m) | (rank == 0) | (bucket != prev_bucket)
    pts = pts[selected]
    return gpd.GeoDataFrame(
        {"facility_id": ids[pts["area"].to_numpy()]},
        geometry=pts["geometry"].values,
        crs=METRIC_CRS,
    )


def build(
    features: gpd.GeoDataFrame,
    ways: gpd.GeoSeries,
    categories: list[Category],
    cfg: AccessPoints,
    tag_keys: list[str] | tuple = (),
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Facilities (`facility_id`, `category`, `name`, `tags`, point geometry, `area_geometry`)
    and their routing points (`facility_id`, `point_id`, `kind`, geometry), from exported points
    and polygons."""
    matched = dedupe(
        match_categories(features, categories, tag_keys, cfg.outline_simplify_m), categories
    )
    access_cats = {c.id for c in categories if c.location == "access_points"}

    facilities = gpd.GeoDataFrame(
        matched[["facility_id", "category", "name", "tags"]],
        geometry=matched.representative_point().values,  # a point stays itself
        crs=METRIC_CRS,
    )
    facilities["area_geometry"] = gpd.GeoSeries(
        matched["area_geometry"].to_numpy(), index=facilities.index, crs=METRIC_CRS
    )

    # Routing points per facility id (shared by all its categories).
    geoms = matched.drop_duplicates("facility_id").set_index("facility_id")
    with_access = matched.loc[
        matched["is_area"] & matched["category"].isin(access_cats), "facility_id"
    ].unique()
    access = access_points(
        gpd.GeoDataFrame(
            {"facility_id": with_access},
            geometry=geoms.loc[with_access].geometry.values,
            crs=METRIC_CRS,
        ),
        ways,
        cfg,
    ).assign(kind="access")
    single = geoms.drop(index=with_access)
    single = gpd.GeoDataFrame(
        {
            "facility_id": single.index.to_numpy(),
            "kind": np.where(single["is_area"], "representative", "node"),
        },
        geometry=single.representative_point().values,
        crs=METRIC_CRS,
    )
    points = pd.concat([single, access], ignore_index=True).sort_values(
        "facility_id", kind="stable", ignore_index=True
    )
    points.insert(1, "point_id", points.groupby("facility_id").cumcount().astype("int32"))
    return facilities.reset_index(drop=True), points[
        ["facility_id", "point_id", "kind", "geometry"]
    ]
