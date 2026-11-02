"""No-op stage that proves the stage pattern end to end (config, run id, manifest, metrics)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from reach_pipeline.context import RunContext
from reach_pipeline.manifest import (
    Manifest,
    file_inputs,
    is_up_to_date,
    read_manifest,
    write_manifest,
)
from reach_pipeline.metrics import measure

STAGE = "hello"
log = logging.getLogger(__name__)


def run(ctx: RunContext) -> Manifest:
    """Record the config checksum; a re-run with the same config is a no-op."""
    stage_dir = ctx.stage_dir(STAGE)
    inputs = file_inputs([ctx.config_path])
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        log.info("inputs unchanged since %s, nothing to do", previous.finished_at.isoformat())
        return previous

    started_at = datetime.now(UTC)
    with measure() as m:
        cfg = ctx.config
        message = (
            f"{cfg.study_area.city_name}: {len(cfg.profiles)} profiles, "
            f"{len(cfg.categories)} categories"
        )
        log.info(message)
    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        message=message,
    )
    path = write_manifest(manifest, stage_dir)
    log.info("manifest written to %s", path)
    return manifest
