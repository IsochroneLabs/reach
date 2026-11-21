"""Wrappers around the osmium CLI: filter, clip and export OSM data by streaming.

The full PBF never enters Python: `tags-filter` and `extract` reduce it on disk, `export` writes
the small result as GeoJSON lines, which GeoPandas reads and converts to EPSG:25832.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path

import geopandas as gpd

from reach_pipeline.errors import ExternalError
from reach_pipeline.metrics import peak_rss_mb

OSMIUM = "osmium"
METRIC_CRS = "EPSG:25832"
# `smart` completes multipolygon relations that cross the clip polygon (parks, school sites).
EXTRACT_STRATEGY = "smart"
_PREFIX = {"node": "n", "way": "w", "relation": "r"}

log = logging.getLogger(__name__)


def _run(args: list[str]) -> str:
    if shutil.which(OSMIUM) is None:
        raise ExternalError("osmium not found on PATH; install osmium-tool (see README)")
    start = time.perf_counter()
    try:
        result = subprocess.run([OSMIUM, *args], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise ExternalError(f"osmium {args[0]} failed: {exc.stderr.strip()}") from exc
    log.info(
        "osmium %s: %.1f s, peak RSS so far %.0f MB",
        args[0],
        time.perf_counter() - start,
        peak_rss_mb(),
    )
    return result.stdout


def tags_filter(src: Path, dst: Path, expressions: list[str]) -> Path:
    """Keep objects matching any expression (e.g. `nwr/amenity=school`) plus referenced objects."""
    _run(["tags-filter", str(src), *expressions, "-o", str(dst), "--overwrite"])
    return dst


def extract_polygon(src: Path, dst: Path, polygon: Path) -> Path:
    """Clip `src` to the (Multi)Polygon in the GeoJSON file `polygon` (EPSG:4326)."""
    args = ["extract", "-p", str(polygon), "-s", EXTRACT_STRATEGY, str(src)]
    _run([*args, "-o", str(dst), "--overwrite"])
    return dst


def export(src: Path, dst: Path, geometry_types: list[str]) -> Path:
    """Tagged objects as GeoJSON lines with `@type` and `@id` (geometry types: point, linestring,
    polygon; closed ways appear as linestring and as polygon)."""
    _run(
        [
            "export",
            str(src),
            "-f",
            "geojsonseq",
            "-a",
            "type,id",
            f"--geometry-types={','.join(geometry_types)}",
            "-o",
            str(dst),
            "--overwrite",
        ]
    )
    return dst


def replication_timestamp(pbf: Path) -> str | None:
    """OSM snapshot time from the PBF header (Geofabrik sets it), or None."""
    out = _run(["fileinfo", "-g", "header.option.osmosis_replication_timestamp", str(pbf)])
    return out.strip() or None


def read_export(
    path: Path, bbox: tuple[float, float, float, float] | None = None, where: str | None = None
) -> gpd.GeoDataFrame:
    """Read an `export` file; adds `osm_id` (`n123`/`w456`/`r789`) and converts to EPSG:25832.

    `bbox` (EPSG:4326) and `where` (OGR SQL on tag columns) are applied while reading.
    """
    with path.open("rb") as fh:
        if not fh.read(64).strip():  # no features: osmium writes a single newline
            return gpd.GeoDataFrame({"osm_id": []}, geometry=[], crs=METRIC_CRS)
    gdf = gpd.read_file(path, bbox=bbox, where=where)
    if gdf.empty:
        return gpd.GeoDataFrame({"osm_id": []}, geometry=[], crs=METRIC_CRS)
    gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    gdf.insert(0, "osm_id", gdf["@type"].map(_PREFIX) + gdf["@id"].astype("int64").astype(str))
    return gdf.drop(columns=["@type", "@id"]).to_crs(METRIC_CRS)


def tag_expressions(tags: list[dict[str, str]], types: str = "nwr") -> list[str]:
    """`tags-filter` expressions for key/value pairs, e.g. `nwr/shop=supermarket`."""
    return [f"{types}/{k}={v}" for tag in tags for k, v in tag.items()]
