"""Excluded land use for candidate sites (recommender and housing potential)."""

from __future__ import annotations

import logging
from typing import Any

import geopandas as gpd

from reach_pipeline import osm
from reach_pipeline import recommend as rec
from reach_pipeline.context import RunContext
from reach_pipeline.stages import validate

log = logging.getLogger(__name__)


def excluded(
    ctx: RunContext, work_stage: str, extra_tags: list[dict[str, str]] | None = None
) -> tuple[gpd.GeoSeries, dict[str, Any]]:
    """Polygons of `recommend.exclude_tags` (plus `extra_tags`) and of protected areas with a
    listed `protect_class` (`recommend.exclude_protect_classes`) from validate's clipped PBF
    (EPSG:25832), plus statistics of the protected areas that stay allowed. `work_stage` names
    the stage directory that holds the osmium intermediates."""
    r = ctx.config.recommend
    tags = [*r.exclude_tags, *(extra_tags or [])]
    exprs = osm.tag_expressions(tags, "wr")
    if r.exclude_protect_classes:
        exprs.append(f"wr/{rec.PROTECTED[0]}={rec.PROTECTED[1]}")
    if not exprs:
        return gpd.GeoSeries([], crs=validate.METRIC_CRS), {}
    work = ctx.stage_dir(work_stage) / "osm"
    work.mkdir(parents=True, exist_ok=True)
    pbf = ctx.stage_dir(validate.STAGE) / validate.ROUTING_PBF
    filtered = osm.tags_filter(pbf, work / "exclude.osm.pbf", exprs)
    exported = osm.export(filtered, work / "exclude.geojsonseq", ["polygon"])
    polygons, stats = rec.exclusions(osm.read_export(exported), tags, r.exclude_protect_classes)
    log.info("protected areas not excluded (by protect_class): %s", stats)
    return polygons, stats
