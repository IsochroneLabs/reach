"""tiles: decide whether the Valhalla graph must be rebuilt, and verify the running service.

Two subcommands (O19); neither touches Docker. The build, the tile swap and the Valhalla restart
run on the host (`make refresh`, `valhalla-build` in `compose.yaml`).

- `tiles check` compares the fingerprint of the build inputs (clipped PBF, `config/valhalla.json`,
  elevation on/off) with the one recorded after the last build (`<data_dir>/valhalla/
  tiles_source.sha256`, written by `make refresh`) and writes the flag file
  `data/runs/<run_id>/tiles/rebuild_needed` (shell variables for the build) if they differ.
  No manifest: only `verify` may let `count` start.
- `tiles verify` (also the step of `run`) checks `/status` (the service must serve
  `<data_dir>/valhalla/valhalla_tiles.tar`: same modification time), routes the golden pair from
  `tiles.verify` and, with elevation, that the route's edges carry grades (VF1); writes
  `verify.json` and the manifest.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from pyproj import Transformer

from reach_pipeline.context import RunContext
from reach_pipeline.errors import ExternalError, StageValidationError
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    config_input,
    file_inputs,
    require_ok,
    sha256_file,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import validate
from reach_pipeline.valhalla.client import ValhallaClient

STAGE = "tiles"
# Config sections this stage uses; only they are part of its inputs (see
# manifest.config_input): tile build flags and the golden route.
CONFIG_SECTIONS = ("tiles", "valhalla")
PREVIOUS = validate.STAGE
FLAG = "rebuild_needed"
SOURCE_FILE = "tiles_source.sha256"
TILES_TAR = "valhalla_tiles.tar"
VERIFY_JSON = "verify.json"
GRADE_ATTRIBUTES = ["edge.weighted_grade", "edge.max_upward_grade", "edge.max_downward_grade"]

log = logging.getLogger(__name__)
_to_metric = Transformer.from_crs("EPSG:4326", validate.METRIC_CRS, always_xy=True)


def valhalla_dir(ctx: RunContext) -> Path:
    """Host directory with the live tiles, the build directory and the elevation cache."""
    return ctx.config.data_dir / "valhalla"


def valhalla_config(ctx: RunContext) -> Path:
    """`config/valhalla.json`, next to the pipeline config (mounted by compose.yaml)."""
    return ctx.config_path.parent / "valhalla.json"


def _routing_pbf(ctx: RunContext) -> Path:
    return ctx.stage_dir(PREVIOUS) / validate.ROUTING_PBF


def fingerprint(pbf: Path, valhalla_json: Path, elevation: bool) -> str:
    """SHA-256 over everything the tile build depends on."""
    text = f"pbf:{sha256_file(pbf)}\nvalhalla.json:{sha256_file(valhalla_json)}\n"
    text += f"elevation:{elevation}\n"
    return hashlib.sha256(text.encode()).hexdigest()


def built_fingerprint(ctx: RunContext) -> str | None:
    path = valhalla_dir(ctx) / SOURCE_FILE
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def _bbox_lonlat(ctx: RunContext) -> str:
    """Routing area bounds in EPSG:4326, rounded outwards (elevation download)."""
    area = gpd.read_parquet(ctx.stage_dir(PREVIOUS) / "routing_area.parquet").to_crs("EPSG:4326")
    x0, y0, x1, y1 = area.total_bounds
    lo = np.floor(np.array([x0, y0]) * 1e4) / 1e4
    hi = np.ceil(np.array([x1, y1]) * 1e4) / 1e4
    return f"{lo[0]:.4f},{lo[1]:.4f},{hi[0]:.4f},{hi[1]:.4f}"


def check(ctx: RunContext) -> bool:
    """Write the flag file if the tiles must be (re)built; return whether they must."""
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    pbf, vjson = _routing_pbf(ctx), valhalla_config(ctx)
    current = fingerprint(pbf, vjson, ctx.config.tiles.elevation)
    flag = ctx.stage_dir(STAGE) / FLAG
    tar = valhalla_dir(ctx) / TILES_TAR
    if built_fingerprint(ctx) == current and tar.exists():
        flag.unlink(missing_ok=True)
        log.info("tiles up to date (%s built from the same inputs)", tar)
        return False
    reason = "no tiles yet" if not tar.exists() else "build inputs changed"
    flag.parent.mkdir(parents=True, exist_ok=True)
    lines = {
        "PBF": str(pbf),
        "SHA256": current,
        "ELEVATION": str(ctx.config.tiles.elevation).lower(),
        "BBOX": _bbox_lonlat(ctx),
    }
    flag.write_text("".join(f"{k}={v}\n" for k, v in lines.items()), encoding="utf-8")
    log.info("rebuild needed (%s): wrote %s", reason, flag)
    return True


def _metric_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    (ax, bx), (ay, by) = _to_metric.transform([a[0], b[0]], [a[1], b[1]])
    return float(np.hypot(bx - ax, by - ay))


async def _verify(ctx: RunContext) -> dict[str, Any]:
    vcfg = ctx.config.tiles.verify
    a, b = vcfg.route
    async with ValhallaClient(ctx.config.valhalla) as client:
        try:
            status = await client.get("status")
        except ExternalError as exc:
            raise ExternalError(
                f"Valhalla is not reachable ({exc}); start it with `make up`"
            ) from exc
        route = await client.post(
            "route",
            {
                "locations": [{"lon": a[0], "lat": a[1]}, {"lon": b[0], "lat": b[1]}],
                "costing": vcfg.costing,
                "units": "kilometers",
            },
        )
        trip = route["trip"]
        grades: list[dict[str, Any]] = []
        if ctx.config.tiles.elevation:
            attrs = await client.post(
                "trace_attributes",
                {
                    "encoded_polyline": trip["legs"][0]["shape"],
                    "costing": vcfg.costing,
                    "shape_match": "edge_walk",
                    "filters": {"attributes": GRADE_ATTRIBUTES, "action": "include"},
                },
            )
            grades = attrs.get("edges", [])
    straight = _metric_distance(a, b)
    length_m = trip["summary"]["length"] * 1000
    return {
        "valhalla_version": status.get("version"),
        "tileset_last_modified": status.get("tileset_last_modified"),
        "route_length_m": round(length_m, 1),
        "route_time_s": round(trip["summary"]["time"], 1),
        "straight_line_m": round(straight, 1),
        "detour_factor": round(length_m / straight, 3),
        "grade_edges": len(grades),
        "max_abs_weighted_grade": max((abs(e["weighted_grade"]) for e in grades), default=None),
        "max_upward_grade": max((e["max_upward_grade"] for e in grades), default=None),
    }


def run(ctx: RunContext) -> Manifest:
    """`tiles verify`: the running Valhalla answers and serves a plausible graph."""
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    stage_dir = ctx.stage_dir(STAGE)
    pbf, vjson = _routing_pbf(ctx), valhalla_config(ctx)
    inputs = [config_input(ctx.config, CONFIG_SECTIONS), *file_inputs([vjson, pbf])]
    started_at = datetime.now(UTC)
    with measure() as m:
        result = asyncio.run(_verify(ctx))
    current = fingerprint(pbf, vjson, ctx.config.tiles.elevation)
    result["tiles_match_run"] = built_fingerprint(ctx) == current
    tar = valhalla_dir(ctx) / TILES_TAR
    result["serves_tiles_of_this_config"] = (
        tar.exists() and int(tar.stat().st_mtime) == result["tileset_last_modified"]
    )
    if not result["tiles_match_run"]:
        log.warning(
            "the tiles were not built from this run's PBF/config (run `make refresh` to rebuild); "
            "counting uses the graph Valhalla serves"
        )
    errors = []
    if not result["serves_tiles_of_this_config"]:
        errors.append(
            f"Valhalla serves another tile set than {tar} (status tileset_last_modified "
            f"{result['tileset_last_modified']}); restart it on this config's tiles: "
            f"`make up REACH_CONFIG={ctx.config_path}` or `make refresh`"
        )
    factor = ctx.config.tiles.verify.max_detour_factor
    if not 1.0 <= result["detour_factor"] <= factor:
        errors.append(
            f"golden route length {result['route_length_m']} m vs. straight line "
            f"{result['straight_line_m']} m (allowed factor 1..{factor})"
        )
    if ctx.config.tiles.elevation and not result["max_abs_weighted_grade"]:
        errors.append("tiles.elevation is true but the golden route carries no grades (VF1)")
    stage_dir.mkdir(parents=True, exist_ok=True)
    report = stage_dir / VERIFY_JSON
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    log.info("verify: %s", result)
    if errors:
        raise StageValidationError("; ".join(errors))
    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        outputs=[FileOutput(path=str(report))],
        message=(
            f"Valhalla {result['valhalla_version']}: golden route {result['route_length_m']} m, "
            f"max grade {result['max_abs_weighted_grade']}, "
            f"tiles match run: {result['tiles_match_run']}"
        ),
    )
    write_manifest(manifest, stage_dir)
    return manifest
