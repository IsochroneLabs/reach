"""cleanup: keep the last `cleanup.keep_published_runs` published runs (arch. §7).

Runs older than the oldest kept published run are deleted: their DB schema `run_<id>` with
their `meta.runs` / `meta.data_sources` rows, and `data/raw/<run_id>/` and `data/runs/<run_id>/`.
Newer runs that were not published (in progress, failed) and the run `current` points at are
never touched. With at most `keep_published_runs` published runs nothing is deleted.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from reach_pipeline import db
from reach_pipeline.context import RunContext, is_run_id
from reach_pipeline.manifest import (
    Manifest,
    config_input,
    is_up_to_date,
    read_manifest,
    require_ok,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import publish

STAGE = "cleanup"
# Config sections this stage uses; only they are part of its inputs (see
# manifest.config_input): retention and the database.
CONFIG_SECTIONS = ("cleanup", "database")
PREVIOUS = publish.STAGE

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Plan:
    keep: list[str]  # published runs kept, newest first
    drop_db: list[str]  # run ids whose schema / meta rows are dropped
    drop_files: list[str]  # run ids whose local directories are deleted


def plan(
    published: list[str],
    db_runs: set[str],
    local_runs: set[str],
    keep: int,
    protected: set[str],
) -> Plan:
    """What to delete. `published` newest first; `protected` = this run and the current run."""
    kept = sorted(published, reverse=True)[:keep]
    if len(published) <= keep:
        return Plan(keep=kept, drop_db=[], drop_files=[])
    oldest = kept[-1]

    def older(ids: set[str]) -> list[str]:
        return sorted(i for i in ids if i < oldest and i not in kept and i not in protected)

    return Plan(keep=kept, drop_db=older(db_runs), drop_files=older(local_runs))


def local_runs(data_dir: Path) -> set[str]:
    """Run ids with a directory under data/runs or data/raw."""
    ids: set[str] = set()
    for sub in ("runs", "raw"):
        base = data_dir / sub
        if base.is_dir():
            ids |= {p.name for p in base.iterdir() if p.is_dir() and is_run_id(p.name)}
    return ids


def delete_files(data_dir: Path, run_id: str) -> None:
    for sub in ("runs", "raw"):
        path = data_dir / sub / run_id
        if path.is_dir():
            shutil.rmtree(path)
            log.info("deleted %s", path)


def run(ctx: RunContext) -> Manifest:
    """Drop old run schemas and delete old run directories."""
    require_ok(ctx.stage_dir(PREVIOUS), PREVIOUS, ctx.config)
    cfg = ctx.config
    stage_dir = ctx.stage_dir(STAGE)
    inputs = [config_input(ctx.config, CONFIG_SECTIONS)]
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        log.info("already cleaned up after this run at %s", previous.finished_at.isoformat())
        return previous

    started_at = datetime.now(UTC)
    with measure() as m:
        with db.connect(db.env_url(publish.URL_ENV), cfg.database) as conn:
            current = db.current_schema(conn)
            meta_runs = {r[0] for r in conn.execute("SELECT run_id FROM meta.runs")}
            schemas = {db.run_id_of(s) for s in db.run_schemas(conn)}
            protected = {ctx.run_id, db.run_id_of(current) if current else None}
            p = plan(
                published=db.published_runs(conn),
                db_runs=meta_runs | {s for s in schemas if s},
                local_runs=local_runs(cfg.data_dir),
                keep=cfg.cleanup.keep_published_runs,
                protected={r for r in protected if r},
            )
            for run_id in p.drop_db:
                db.drop_run(conn, run_id)
                log.info("dropped schema %s and its meta rows", db.schema_name(run_id))
        for run_id in p.drop_files:
            delete_files(cfg.data_dir, run_id)

    manifest = Manifest(
        stage=STAGE,
        run_id=ctx.run_id,
        status="ok",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
        message=(
            f"kept published {p.keep}; dropped DB runs {p.drop_db}; "
            f"deleted local runs {p.drop_files}"
        ),
    )
    write_manifest(manifest, stage_dir)
    return manifest
