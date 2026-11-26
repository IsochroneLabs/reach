"""Count destination labels on an OSM extract (exploration for F2.1, not pipeline code).

Usage (repo root):
    osmium tags-filter -O -o sel.osm.pbf <routing-area>.osm.pbf nwr/shop=supermarket \
        nwr/leisure nwr/club nwr/sport nwr/amenity=music_school,arts_centre,place_of_worship
    osmium export -O -f geojsonseq --add-unique-id=type_id -o sel.geojsonseq sel.osm.pbf
    uv run --package reach-pipeline python label_counts.py sel.geojsonseq config/config.yaml

Applies the `destination_labels` taxonomy of the config: access filter, grocery brands and
groups, sport and hobby categories, religion; clusters features of one label within
`cluster_radius_m` or inside the same leisure=sports_centre; prints Markdown tables.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict

import geopandas as gpd
from shapely.geometry import shape

from reach_pipeline.config import load_config


def values(props: dict, key: str) -> list[str]:
    raw = props.get(key)
    return [v.strip() for v in raw.split(";")] if raw else []


def tag_match(props: dict, tags: list[dict[str, str]]) -> bool:
    return any(val in values(props, k) for t in tags for k, val in t.items())


def grocery_labels(props: dict, cfg) -> tuple[str | None, str]:
    brand = None
    qid = props.get("brand:wikidata")
    text = " ".join(props.get(k, "") for k in ("brand", "name")).lower()
    for key, b in cfg.brands.items():
        if (qid and qid in b.wikidata) or any(n.lower() in text for n in b.names):
            brand = key
            break
    names = [props[k].lower() for k in ("name", "alt_name", "short_name") if props.get(k)]
    for key, g in cfg.groups.items():
        if (
            tag_match(props, g.tags)
            or (brand is not None and brand in g.brands)
            or any(re.search(p, n) for p in g.name_patterns for n in names)
        ):
            return brand, key
    return brand, cfg.fallback


def sport_labels(props: dict, cfg) -> set[str]:
    leisure = props.get("leisure")
    if leisure not in cfg.leisure and props.get("club") != "sport":
        return set()
    if leisure == "swimming_pool" and props.get("access") not in cfg.swimming_pool_access:
        return set()
    sports = set(values(props, "sport"))
    out = {name for name, cat in cfg.categories.items() if sports & set(cat.sport)}
    if not out:  # leisure only decides when no sport value maps to a category
        out = {name for name, cat in cfg.categories.items() if leisure in cat.leisure}
    return out


def main(geojsonseq: str, config_path: str) -> None:
    cfg = load_config(config_path).destination_labels
    rows, unmapped = [], Counter()
    with open(geojsonseq, encoding="utf-8") as fh:
        lines = fh.readlines()
    for line in lines:
        f = json.loads(line.lstrip("\x1e"))
        p = f["properties"]
        if p.get("access") in cfg.exclude_access:
            continue
        labels: list[tuple[str, str]] = []
        if p.get("shop") == "supermarket":
            brand, group = grocery_labels(p, cfg.grocery)
            if brand:
                labels.append(("grocery_brand", brand))
            labels.append(("grocery_group", group))
        sports = sport_labels(p, cfg.sport)
        labels += [("sport", s) for s in sorted(sports)]
        if p.get("leisure") in cfg.sport.leisure:
            known = {v for c in cfg.sport.categories.values() for v in c.sport}
            for v in values(p, "sport"):
                if v not in known and v not in cfg.sport.ignore_values and v != "chess":
                    unmapped[v] += 1
        for name, cat in cfg.hobby.categories.items():
            if tag_match(p, cat.tags):
                labels.append(("hobby", name))
        if p.get("amenity") == "place_of_worship":
            labels.append(("religion", p.get(cfg.religion_key, "unknown")))
        for kind, label in labels:
            rows.append(
                {
                    "kind": kind,
                    "label": label,
                    "name": p.get("name", ""),
                    "leisure": p.get("leisure"),
                    "geometry": shape(f["geometry"]),
                }
            )

    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326").to_crs(25832)
    gdf["pt"] = gdf.geometry.representative_point()
    centres = gdf[
        (gdf.leisure == "sports_centre") & gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    ]
    centres = centres.drop_duplicates(subset=centres.geometry.name).reset_index(drop=True)

    result = defaultdict(dict)
    for (kind, label), grp in gdf.groupby(["kind", "label"]):
        grp = grp.reset_index(drop=True)
        parent = list(range(len(grp)))

        def find(i: int, parent: list[int] = parent) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        pts = gpd.GeoSeries(grp.pt, crs=25832)
        left, right = pts.sindex.query(pts, predicate="dwithin", distance=cfg.cluster_radius_m)
        for a, b in zip(left, right, strict=True):
            parent[find(a)] = find(b)
        if kind == "sport" and len(centres):
            inside = gpd.sjoin(
                gpd.GeoDataFrame(geometry=pts), centres[["geometry"]], predicate="within"
            )
            first = {}
            for i, c in zip(inside.index, inside["index_right"], strict=True):
                if c in first:
                    parent[find(i)] = find(first[c])
                else:
                    first[c] = i
        clusters = len({find(i) for i in range(len(grp))})
        result[kind][label] = (len(grp), clusters, sorted({n for n in grp.name if n})[:4])

    for kind in ("grocery_brand", "grocery_group", "sport", "hobby", "religion"):
        print(f"\n### {kind}\n\n| label | features | destinations | examples |\n|---|---|---|---|")
        for label, (n, c, ex) in sorted(result[kind].items(), key=lambda kv: -kv[1][1]):
            print(f"| {label} | {n} | {c} | {', '.join(ex)} |")
    if unmapped:
        print("\nsport values without a category:", dict(unmapped.most_common()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
