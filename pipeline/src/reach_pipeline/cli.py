"""Command line: `python -m reach_pipeline <stage> [--run-id ID] [--config PATH]`."""

from __future__ import annotations

import argparse
import contextvars
import logging
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from reach_pipeline.config import load_config
from reach_pipeline.context import RunContext, is_run_id, latest_run_id, new_run_id
from reach_pipeline.errors import ConfigError, PipelineError
from reach_pipeline.manifest import Manifest, write_manifest
from reach_pipeline.metrics import Measurement, measure
from reach_pipeline.stages import acquire, count, tiles, validate

DEFAULT_CONFIG = "config/config.yaml"
TILES_ACTIONS = ("check", "verify")

# Implemented stages in execution order; `run` executes all of them. The first one starts a run.
STAGES: dict[str, Callable[[RunContext], Manifest]] = {
    acquire.STAGE: acquire.run,
    validate.STAGE: validate.run,
    tiles.STAGE: tiles.run,  # `tiles verify`; `tiles check` is called on its own (make refresh)
    count.STAGE: count.run,
}
# Stages that follow (C11), with the phase that implements them: a single one fails with a
# clear message, `run` logs each as skipped. Move a stage to STAGES when it is implemented.
PLANNED: dict[str, str] = {
    "score": "P4",
    "recommend": "P7",
    "validate_results": "P4",
    "publish": "P4",
    "cleanup": "P4",
}

log = logging.getLogger("reach_pipeline")
_current_stage: contextvars.ContextVar[str] = contextvars.ContextVar("stage", default="-")


class _StageFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.stage = _current_stage.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """One format for every stage: `time level stage message`."""
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_StageFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(stage)s %(message)s"))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # One line per HTTP request is noise; acquire logs what it does with each source.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m reach_pipeline", description=__doc__)
    parser.add_argument(
        "stage", choices=[*STAGES, *PLANNED, "run"], help="stage to run, or 'run' for all"
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=TILES_ACTIONS,
        help="tiles only: 'check' (write the rebuild flag) or 'verify' (default)",
    )
    parser.add_argument(
        "--run-id",
        help=(
            f"run id (YYYYMMDDTHHMMSSZ); default: new id for 'run' and '{next(iter(STAGES))}', "
            "latest run for any other stage"
        ),
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("REACH_CONFIG", DEFAULT_CONFIG),
        help=f"config file (default: $REACH_CONFIG or {DEFAULT_CONFIG})",
    )
    return parser.parse_args(argv)


def _resolve_run_id(requested: str | None, stage: str, runs_dir: Path) -> str:
    if requested is not None:
        if not is_run_id(requested):
            raise ConfigError(f"invalid run id {requested!r}, expected YYYYMMDDTHHMMSSZ")
        return requested
    starts_run = stage in ("run", next(iter(STAGES)))
    if not starts_run and (latest := latest_run_id(runs_dir)):
        return latest
    return new_run_id()


def _run_stage(name: str, ctx: RunContext) -> Manifest:
    token = _current_stage.set(name)
    started_at = datetime.now(UTC)
    m = Measurement()
    try:
        with measure() as m:
            manifest = STAGES[name](ctx)
    except Exception as exc:
        # measure() has filled m on the way out; record the failure for the next stage.
        failed = Manifest(
            stage=name,
            run_id=ctx.run_id,
            status="failed",
            started_at=started_at,
            finished_at=datetime.now(UTC),
            runtime_s=m.runtime_s,
            peak_rss_mb=m.peak_rss_mb,
            message=f"{type(exc).__name__}: {exc}",
        )
        write_manifest(failed, ctx.stage_dir(name))
        raise
    else:
        if manifest.finished_at < started_at:
            log.info("skipped, up to date (manifest of %s)", manifest.finished_at.isoformat())
        else:
            log.info("done in %.2f s, peak RSS %.1f MB", m.runtime_s, m.peak_rss_mb)
        return manifest
    finally:
        _current_stage.reset(token)


def _tiles_check(ctx: RunContext) -> None:
    """`tiles check`: writes the rebuild flag file only, no manifest (O19)."""
    token = _current_stage.set(tiles.STAGE)
    try:
        tiles.check(ctx)
    finally:
        _current_stage.reset(token)


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code (0 ok, 1 validation, 2 config, 3 external)."""
    setup_logging()
    args = _parse_args(argv)
    try:
        if args.stage in PLANNED:
            raise ConfigError(
                f"stage {args.stage!r} is not implemented yet (planned in {PLANNED[args.stage]})"
            )
        if args.action and args.stage != tiles.STAGE:
            raise ConfigError(f"{args.action!r} is only valid for the tiles stage")
        config_path = Path(args.config)
        config = load_config(config_path)
        run_id = _resolve_run_id(args.run_id, args.stage, config.data_dir / "runs")
        ctx = RunContext(config=config, config_path=config_path, run_id=run_id)
        log.info("run %s, config %s", run_id, config_path)
        if args.action == "check":
            _tiles_check(ctx)
            return 0
        names = list(STAGES) if args.stage == "run" else [args.stage]
        for name in names:
            _run_stage(name, ctx)
        if args.stage == "run":
            for name, phase in PLANNED.items():
                log.warning("stage %s skipped: not implemented yet (planned in %s)", name, phase)
    except PipelineError as exc:
        log.error("%s", exc)
        return exc.exit_code
    except Exception:
        log.exception("unexpected error")
        return 1
    return 0
