"""score: thresholds of this run from the config → `thresholds.parquet` (arch. §7).

Classes and deficits are not stored: the database derives them at read time from the raw counts
and this table (`scores`, `transit_scores`, `district_scores` in `infra/db/run_schema.sql`;
AGENTS.md rule 5). Changing a threshold therefore never needs re-routing.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from reach_pipeline import scoring
from reach_pipeline.config import config_files
from reach_pipeline.context import RunContext
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    file_inputs,
    is_up_to_date,
    read_manifest,
    require_ok,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import count

STAGE = "score"
PREVIOUS = count.STAGE
THRESHOLDS = "thresholds.parquet"

log = logging.getLogger(__name__)


def run(ctx: RunContext) -> Manifest:
    """Write the thresholds table (categories: k; transit: class bounds)."""
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS)
    stage_dir = ctx.stage_dir(STAGE)
    inputs = file_inputs(config_files(ctx.config_path))
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        log.info("inputs unchanged since %s, nothing to do", previous.finished_at.isoformat())
        return previous

    started_at = datetime.now(UTC)
    with measure() as m:
        thr = scoring.thresholds(ctx.config)
        stage_dir.mkdir(parents=True, exist_ok=True)
        thr.to_parquet(stage_dir / THRESHOLDS, index=False)
    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        outputs=[FileOutput(path=str(stage_dir / THRESHOLDS), rows=len(thr))],
        message=(
            f"{int(thr['class'].isna().sum())} category thresholds, "
            f"{int(thr['class'].notna().sum())} transit classes"
        ),
    )
    write_manifest(manifest, stage_dir)
    return manifest
