"""Command line of the validation experiments.

    python -m reach_pipeline.experiments [v01 v05 …] [--run-id ID] [--config PATH]
        [--settings PATH]
    python -m reach_pipeline.experiments summary [--run-id ID]
    python -m reach_pipeline.experiments figures [--run-id ID]

Without names, all automated experiments run in order. Each one writes `result.json` (status,
results, runtime, peak RSS) into its folder; `make experiments` starts one process per
experiment, so the peak RSS is that experiment's own. Exit codes as the pipeline (errors.py).
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reach_pipeline.cli import DEFAULT_CONFIG, setup_logging
from reach_pipeline.config import load_config
from reach_pipeline.context import RunContext, latest_run_id
from reach_pipeline.errors import ConfigError, PipelineError
from reach_pipeline.experiments.common import Experiment
from reach_pipeline.experiments.settings import DEFAULT_PATH, Settings, load_settings
from reach_pipeline.metrics import measure

# Automated experiments in execution order: name → module.
AUTOMATED: dict[str, str] = {
    "v01": "v01_isochrones",
    "v02": "v02_completeness",
    "v03": "v03_backtest",
    "v04": "v04_exact",
    "v05": "v05_sensitivity",
    "v06": "v06_origin",
    "v08": "v08_spatial",
    "v10": "v10_route",
    "v11": "v11_slopes",
}
# Experiments that need people; their protocol is in docs/validation_report.md.
MANUAL: dict[str, tuple[str, str]] = {
    "v07": (
        "Plausibility with local knowledge",
        "needs two or three people who know Tübingen (protocol in docs/validation_report.md)",
    ),
    "v09": (
        "Reproducibility from the README",
        "needs a team member who did not write the pipeline (protocol in "
        "docs/validation_report.md)",
    ),
}
RESULT = "result.json"
SUMMARY = "summary.md"

log = logging.getLogger("reach_pipeline")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m reach_pipeline.experiments", description=__doc__)
    p.add_argument(
        "names", nargs="*", help=f"experiments ({', '.join(AUTOMATED)}), 'summary' or 'figures'"
    )
    p.add_argument("--run-id", help="run to validate (default: the latest run)")
    p.add_argument(
        "--config", default=os.environ.get("REACH_CONFIG", DEFAULT_CONFIG), help="pipeline config"
    )
    p.add_argument("--settings", default=DEFAULT_PATH, help="experiments config")
    return p.parse_args(argv)


def _context(args: argparse.Namespace) -> tuple[RunContext, Settings]:
    cfg = load_config(args.config)
    run_id = args.run_id or latest_run_id(cfg.data_dir / "runs")
    if not run_id or not (cfg.data_dir / "runs" / run_id).is_dir():
        raise ConfigError(f"run {run_id!r} not found under {cfg.data_dir / 'runs'}")
    settings = load_settings(args.settings)
    unknown = sorted(settings.profiles_used() - cfg.profiles.keys())
    if unknown:
        raise ConfigError(f"{args.settings}: unknown profiles {unknown}")
    return RunContext(config=cfg, config_path=Path(args.config), run_id=run_id), settings


def run_one(ctx: RunContext, settings: Settings, name: str) -> dict[str, Any]:
    """Run one experiment and write its `result.json`."""
    e = Experiment(ctx=ctx, settings=settings, name=name)
    started = datetime.now(UTC)
    if name in MANUAL:
        title, reason = MANUAL[name]
        result: dict[str, Any] = {"status": "manual", "reason": reason}
        m = None
    else:
        module = importlib.import_module(f"reach_pipeline.experiments.{AUTOMATED[name]}")
        title = module.TITLE
        log.info("%s: %s", name, title)
        with measure() as m:
            result = module.run(e)
    out = {
        "experiment": name.upper(),
        "title": title,
        "run_id": ctx.run_id,
        "started_at": started.isoformat(timespec="seconds"),
        "runtime_s": m.runtime_s if m else None,
        "peak_rss_mb": m.peak_rss_mb if m else None,
        **result,
        "notes": e.notes,
    }
    e.write_json(RESULT, out)
    log.info(
        "%s %s in %s s (peak %s MB)", name, out["status"], out["runtime_s"], out["peak_rss_mb"]
    )
    return out


def summary(ctx: RunContext, settings: Settings) -> Path:
    """`summary.md`: one row per experiment from the `result.json` files."""
    root = ctx.config.data_dir / settings.results_dir / ctx.run_id
    lines = [
        f"# Validation experiments — run {ctx.run_id}",
        "",
        f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} by "
        "`python -m reach_pipeline.experiments summary`; interpretation in "
        "`docs/validation_report.md`.",
        "",
        "| # | Experiment | Status | Runtime (s) | Peak RSS (MB) | Result file |",
        "|---|---|---|---|---|---|",
    ]
    for name in sorted([*AUTOMATED, *MANUAL]):
        path = root / name / RESULT
        if not path.exists():
            lines.append(f"| {name.upper()} | – | not run | – | – | – |")
            continue
        r = json.loads(path.read_text(encoding="utf-8"))
        lines.append(
            f"| {r['experiment']} | {r['title']} | {r['status']} | {r['runtime_s'] or '–'} | "
            f"{r['peak_rss_mb'] or '–'} | `{name}/{RESULT}` |"
        )
    out = root / SUMMARY
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("summary written to %s", out)
    return out


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = _parse(argv)
    try:
        ctx, settings = _context(args)
        names = [n.lower() for n in args.names] or list(AUTOMATED)
        for name in names:
            if name == "summary":
                summary(ctx, settings)
            elif name == "figures":
                importlib.import_module("reach_pipeline.experiments.figures").draw(ctx, settings)
            elif name in AUTOMATED or name in MANUAL:
                run_one(ctx, settings, name)
            else:
                raise ConfigError(f"unknown experiment {name!r}")
    except PipelineError as exc:
        log.error("%s", exc)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    sys.exit(main())
