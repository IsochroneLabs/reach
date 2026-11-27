"""transit: inputs of the OpenTripPlanner graph, and verification of the running service (O17).

Two subcommands, like `tiles`; neither touches Docker. The graph build (official OTP image,
`--build --save`), the swap into `<data_dir>/otp` and the OTP restart run on the host
(`make refresh`, `otp-build` in `compose.yaml`).

- `transit prepare` writes `data/runs/<run_id>/transit/`: the GTFS feed clipped to the stops of
  the routing area, the routing-area PBF (hard link) and `build-config.json` /
  `router-config.json`. No manifest: only `verify` lets `travel_times` start.
- `transit verify` (also the step of `run`) asks the running OTP for the transit trip of
  `otp.verify` in the morning window; it must find an itinerary with a vehicle leg. Writes
  `verify.json` and the manifest.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

import geopandas as gpd

from reach_pipeline import otp
from reach_pipeline.context import RunContext
from reach_pipeline.errors import ConfigError, StageValidationError
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    config_input,
    file_inputs,
    require_ok,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import tiles, validate
from reach_pipeline.timing import window_datetime

STAGE = "transit"
CONFIG_SECTIONS = ("otp", "routing_profiles", "sources", "timezone", "trip_windows")
PREVIOUS = tiles.STAGE
GRAPH = "graph.obj"
VERIFY_JSON = "verify.json"
INPUT_FILES = ("build-config.json", "router-config.json")

log = logging.getLogger(__name__)


def otp_dir(ctx: RunContext) -> Path:
    """Directory the OTP service serves (`OTP_DIR` in compose, `<data_dir>/otp`)."""
    return ctx.config.data_dir / "otp"


def reference_dates(ctx: RunContext) -> dict[str, date]:
    """Reference date per trip window from report part 1 of `validate`."""
    report = ctx.stage_dir(validate.STAGE) / validate.REPORT_JSON
    refs = json.loads(report.read_text(encoding="utf-8"))["summary"]["reference_dates"]
    missing = sorted(k for k, v in refs.items() if v is None)
    if missing:
        raise StageValidationError(f"no reference date for {missing} (see {report})")
    return {k: date.fromisoformat(v) for k, v in refs.items()}


def prepare(ctx: RunContext) -> Path:
    """Write the graph inputs into the run's `transit/` directory and return it."""
    if ctx.config.otp is None:
        raise ConfigError("config has no otp section (O17)")
    require_ok(ctx.stage_dir(validate.STAGE), validate.STAGE, ctx.config)
    out = ctx.stage_dir(STAGE)
    out.mkdir(parents=True, exist_ok=True)
    stops = gpd.read_parquet(ctx.stage_dir(validate.STAGE) / "stops.parquet")
    with measure() as m:
        counts = otp.clip_gtfs(ctx.raw_dir / "gtfs", out / "gtfs", stops["stop_id"].tolist())
    log.info("GTFS clipped in %.1f s: %s", m.runtime_s, counts)
    pbf, link = ctx.stage_dir(validate.STAGE) / validate.ROUTING_PBF, out / "osm.pbf"
    link.unlink(missing_ok=True)
    try:
        os.link(pbf, link)
    except OSError:
        link.write_bytes(pbf.read_bytes())
    otp.write_json(out / "build-config.json", otp.build_config(list(reference_dates(ctx).values())))
    otp.write_json(out / "router-config.json", otp.router_config(ctx.config))
    log.info("OTP inputs in %s; build with `make transit-build`", out)
    return out


async def _verify(ctx: RunContext) -> dict:
    cfg = ctx.config
    v = cfg.otp.verify
    window = cfg.trip_windows[v.trip_window]
    when = window_datetime(reference_dates(ctx)[v.trip_window], window.time, cfg.timezone)
    async with otp.OtpClient(cfg.otp) as client:
        trip = await client.plan(
            tuple(v.route[0]), tuple(v.route[1]), when, window.mode == "arrive_by", "WALK"
        )
    result = {"route": v.route, "trip_window": v.trip_window, "when": when.isoformat()}
    result |= asdict(trip)
    if trip.time_s is None or trip.walk_only:
        raise StageValidationError(f"OTP found no transit trip for otp.verify: {result}")
    if trip.time_s > v.max_minutes * 60:
        raise StageValidationError(f"OTP verify trip takes {trip.time_s} s > {v.max_minutes} min")
    return result


def run(ctx: RunContext) -> Manifest:
    """`transit verify`: the served graph answers the verify trip; writes the manifest."""
    if ctx.config.otp is None:
        raise ConfigError("config has no otp section (O17)")
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    stage_dir = ctx.stage_dir(STAGE)
    graph = otp_dir(ctx) / GRAPH
    if not graph.exists():
        raise StageValidationError(f"{graph} missing: run `make refresh` (transit build)")
    started_at = datetime.now(UTC)
    with measure() as m:
        result = asyncio.run(_verify(ctx))
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / VERIFY_JSON).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    log.info(
        "verify trip: %s min, first stop %s, route %s",
        round(result["time_s"] / 60),
        result["first_stop"],
        result["first_route"],
    )
    inputs = [config_input(ctx.config, CONFIG_SECTIONS), *file_inputs([graph])]
    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        outputs=[FileOutput(path=str(stage_dir / VERIFY_JSON))],
        message=f"OTP verify trip {round(result['time_s'] / 60)} min ({graph})",
    )
    write_manifest(manifest, stage_dir)
    return manifest
