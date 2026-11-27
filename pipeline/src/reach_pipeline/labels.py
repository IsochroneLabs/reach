"""Destination labels (meth. §3.1, arch. O22): label OSM features and cluster them.

Brands and groups for supermarkets, categories for sport and hobby, the religion for places of
worship. The rules come from `config.destination_labels`; osmium does the filtering (see
`osm_expressions`), everything here is vectorised on GeoDataFrames in EPSG:25832. One row of the
result is one destination of one label: features of the same label closer than `cluster_radius_m`
(geometry to geometry), or inside the same `leisure=sports_centre`, are merged (a tennis club with
ten courts is one place).
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd

from reach_pipeline.config import DestinationLabels

METRIC_CRS = "EPSG:25832"
COLUMNS = [
    "destination_id",
    "destination_type",
    "label_kind",
    "label",
    "name",
    "n_features",
    "osm_ids",
    "offered",
    "geometry",
]
LABEL_KEYS = ["destination_type", "label_kind", "label"]


def osm_expressions(cfg: DestinationLabels) -> list[str]:
    """`osmium tags-filter` expressions selecting every candidate feature."""
    exprs = [
        "nwr/shop=supermarket",
        "nwr/amenity=place_of_worship",
        "nwr/club=sport",
        "nwr/leisure=" + ",".join(cfg.sport.leisure),
    ]
    cats = [*cfg.sport.categories.values(), *cfg.hobby.categories.values()]
    exprs += [f"nwr/{k}={v}" for c in cats for tag in c.tags for k, v in tag.items()]
    return list(dict.fromkeys(exprs))


def _col(gdf: pd.DataFrame, key: str) -> pd.Series:
    """Tag column as strings ("" where the tag is missing)."""
    if key not in gdf.columns:
        return pd.Series("", index=gdf.index, dtype="object")
    return gdf[key].fillna("").astype(str)


def _has_value(gdf: pd.DataFrame, key: str, values: Iterable[str]) -> pd.Series:
    """True where one of the `;`-separated values of tag `key` is in `values`."""
    values = list(values)
    if not values:
        return pd.Series(False, index=gdf.index)
    alt = "|".join(re.escape(v) for v in values)
    return _col(gdf, key).str.contains(rf"(?:^|;)\s*(?:{alt})\s*(?:;|$)", regex=True)


def _tag_match(gdf: pd.DataFrame, tags: list[dict[str, str]]) -> pd.Series:
    mask = pd.Series(False, index=gdf.index)
    for tag in tags:
        for key, value in tag.items():
            mask |= _has_value(gdf, key, [value])
    return mask


def _rows(gdf: gpd.GeoDataFrame, dtype: str, kind: str, label: pd.Series) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "osm_id": gdf["osm_id"].to_numpy(),
            "destination_type": dtype,
            "label_kind": kind,
            "label": label.to_numpy(),
            "name": _col(gdf, "name").to_numpy(),
            "leisure": _col(gdf, "leisure").to_numpy(),
        },
        geometry=gdf.geometry.to_numpy(),
        crs=gdf.crs,
    )


def _grocery(gdf: gpd.GeoDataFrame, cfg: DestinationLabels) -> list[gpd.GeoDataFrame]:
    g = cfg.grocery
    shops = gdf[_col(gdf, "shop") == "supermarket"]
    qid = _col(shops, "brand:wikidata")
    text = (_col(shops, "brand") + " " + _col(shops, "name")).str.lower()
    brand = pd.Series(None, index=shops.index, dtype="object")
    for key, b in g.brands.items():
        hit = qid.isin(b.wikidata)
        if b.names:
            hit |= text.str.contains("|".join(re.escape(n.lower()) for n in b.names), regex=True)
        brand = brand.mask(brand.isna() & hit, key)
    names = [_col(shops, k).str.lower() for k in ("name", "alt_name", "short_name")]
    group = pd.Series(None, index=shops.index, dtype="object")
    for key, grp in g.groups.items():
        hit = _tag_match(shops, grp.tags) | brand.isin(grp.brands)
        if grp.name_patterns:
            pattern = "|".join(f"(?:{p})" for p in grp.name_patterns)
            with warnings.catch_warnings():  # patterns may use groups, e.g. "t(ü|ue)rk"
                warnings.filterwarnings("ignore", "This pattern .* has match groups")
                for col in names:
                    hit |= col.str.contains(pattern, regex=True)
        group = group.mask(group.isna() & hit, key)
    group = group.fillna(g.fallback)
    has_brand = brand.notna()
    return [
        _rows(shops[has_brand], "grocery", "brand", brand[has_brand]),
        _rows(shops, "grocery", "group", group),
    ]


def _public(gdf: gpd.GeoDataFrame, cfg: DestinationLabels) -> gpd.GeoDataFrame:
    return gdf[~_col(gdf, "access").isin(cfg.exclude_access)]


def _sport(gdf: gpd.GeoDataFrame, cfg: DestinationLabels) -> gpd.GeoDataFrame:
    s = cfg.sport
    leisure = _col(gdf, "leisure")
    cand = gdf[leisure.isin(s.leisure) | (_col(gdf, "club") == "sport")]
    cand = _public(cand, cfg)
    pool = _col(cand, "leisure") == "swimming_pool"
    cand = cand[~pool | _col(cand, "access").isin(s.swimming_pool_access)]
    by_sport = {
        name: _has_value(cand, "sport", c.sport) | _tag_match(cand, c.tags)
        for name, c in s.categories.items()
    }
    any_sport = pd.concat(by_sport, axis=1).any(axis=1)
    lei = _col(cand, "leisure")
    out = []
    for name, c in s.categories.items():
        hit = by_sport[name] | (~any_sport & lei.isin(c.leisure))
        sel = cand[hit]
        out.append(_rows(sel, "sport", "category", pd.Series(name, index=sel.index)))
    return pd.concat(out) if out else cand.iloc[:0]


def _hobby(gdf: gpd.GeoDataFrame, cfg: DestinationLabels) -> list[gpd.GeoDataFrame]:
    pub = _public(gdf, cfg)
    out = []
    for name, c in cfg.hobby.categories.items():
        sel = pub[_tag_match(pub, c.tags)]
        out.append(_rows(sel, "hobby", "category", pd.Series(name, index=sel.index)))
    return out


def _religion(gdf: gpd.GeoDataFrame, cfg: DestinationLabels) -> gpd.GeoDataFrame:
    pub = _public(gdf, cfg)
    sel = pub[_col(pub, "amenity") == "place_of_worship"]
    religion = _col(sel, cfg.religion_key).replace("", "unknown")
    return _rows(sel, "place_of_worship", "religion", religion)


def unique_features(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One row per OSM object: `export` writes closed ways as line and polygon; keep the polygon."""
    order = features.geometry.area.sort_values(ascending=False, kind="stable").index
    return features.loc[order].drop_duplicates("osm_id").sort_index()


def label_features(features: gpd.GeoDataFrame, cfg: DestinationLabels) -> gpd.GeoDataFrame:
    """One row per feature and label (a feature can carry several labels)."""
    if features.empty:
        return gpd.GeoDataFrame(
            columns=["osm_id", *LABEL_KEYS, "name", "leisure", "geometry"],
            geometry="geometry",
            crs=METRIC_CRS,
        )
    parts = [
        *_grocery(features, cfg),
        _sport(features, cfg),
        *_hobby(features, cfg),
        _religion(features, cfg),
    ]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return label_features(features.iloc[:0], cfg)
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=features.crs)


def _components(n: int, left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Connected components of an undirected graph given as edge arrays (min label propagation)."""
    comp = np.arange(n)
    while True:
        nxt = comp.copy()
        np.minimum.at(nxt, left, comp[right])
        np.minimum.at(nxt, right, comp[left])
        nxt = nxt[nxt]
        if np.array_equal(nxt, comp):
            return comp
        comp = nxt


def cluster(
    labelled: gpd.GeoDataFrame, features: gpd.GeoDataFrame, cfg: DestinationLabels
) -> gpd.GeoDataFrame:
    """Merge features of one label closer than the radius (geometry to geometry) or inside one
    `leisure=sports_centre`; the point of a destination lies inside its largest feature."""
    if labelled.empty:
        return gpd.GeoDataFrame(columns=COLUMNS, geometry="geometry", crs=METRIC_CRS)
    lab = labelled.reset_index(drop=True).copy()
    key = lab[LABEL_KEYS].astype(str).agg("|".join, axis=1).to_numpy()
    left, right = lab.sindex.query(lab.geometry, predicate="dwithin", distance=cfg.cluster_radius_m)
    same = key[left] == key[right]
    left, right = left[same], right[same]

    leisure = _col(features, "leisure")
    centres = features[(leisure == "sports_centre") & (features.geometry.area > 0)]
    sport = lab[lab["destination_type"] == "sport"]
    if not centres.empty and not sport.empty:
        pts = gpd.GeoDataFrame(geometry=sport.geometry.representative_point(), crs=lab.crs)
        inside = gpd.sjoin(pts, centres[["geometry"]], predicate="within").reset_index()
        inside["key"] = key[inside["index"].to_numpy()]
        first = inside.groupby(["index_right", "key"])["index"].transform("first")
        left = np.concatenate([left, inside["index"].to_numpy()])
        right = np.concatenate([right, first.to_numpy()])
    lab["cluster"] = _components(len(lab), left, right)

    lab["area"] = lab.geometry.area
    lab = lab.sort_values(["cluster", "area", "osm_id"], ascending=[True, False, True])
    named = lab[lab["name"] != ""].groupby("cluster")["name"].first()
    agg = lab.groupby("cluster").agg(
        destination_type=("destination_type", "first"),
        label_kind=("label_kind", "first"),
        label=("label", "first"),
        lead=("osm_id", "first"),
        n_features=("osm_id", "size"),
        osm_ids=("osm_id", lambda s: ";".join(sorted(s))),
        geom=("geometry", "first"),
    )
    agg["name"] = named.reindex(agg.index).fillna("")
    agg["destination_id"] = agg["destination_type"] + ":" + agg["label"] + ":" + agg["lead"]
    point = gpd.GeoSeries(agg["geom"].to_numpy(), crs=lab.crs).representative_point()
    out = gpd.GeoDataFrame(
        agg.drop(columns=["geom", "lead"]).reset_index(drop=True),
        geometry=point.to_numpy(),
        crs=lab.crs,
    )
    out["offered"] = _offered(out, cfg)
    return out[COLUMNS].sort_values("destination_id").reset_index(drop=True)


def _offered(dest: pd.DataFrame, cfg: DestinationLabels) -> pd.Series:
    """A label is offered with enough destinations (brands: `brand_min_stores`)."""
    size = dest.groupby(LABEL_KEYS)["destination_id"].transform("size")
    need = (
        dest["label_kind"].map({"brand": cfg.grocery.brand_min_stores}).fillna(cfg.min_destinations)
    )
    return size >= need


def counts(dest: pd.DataFrame) -> pd.DataFrame:
    """Destinations and features per label, for the report."""
    if dest.empty:
        return pd.DataFrame(columns=[*LABEL_KEYS, "destinations", "features", "offered"])
    return (
        dest.groupby(LABEL_KEYS, as_index=False)
        .agg(
            destinations=("destination_id", "size"),
            features=("n_features", "sum"),
            offered=("offered", "first"),
        )
        .sort_values(
            ["destination_type", "label_kind", "destinations"], ascending=[True, True, False]
        )
        .reset_index(drop=True)
    )


def missing_categories(dest: pd.DataFrame, cfg: DestinationLabels) -> dict[str, list[str]]:
    """Configured sport and hobby categories without any destination (not offered)."""
    found = set(zip(dest["destination_type"], dest["label"], strict=True)) if len(dest) else set()
    return {
        dtype: sorted(c for c in cats if (dtype, c) not in found)
        for dtype, cats in (("sport", cfg.sport.categories), ("hobby", cfg.hobby.categories))
    }
