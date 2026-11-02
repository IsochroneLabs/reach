"""Run context shared by all stages: typed config, run id and paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from reach_pipeline.config import Config

RUN_ID_FORMAT = "%Y%m%dT%H%M%SZ"
_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z$")


def new_run_id(now: datetime | None = None) -> str:
    """UTC timestamp with seconds, e.g. `20261116T030000Z`."""
    return (now or datetime.now(UTC)).strftime(RUN_ID_FORMAT)


def is_run_id(value: str) -> bool:
    return bool(_RUN_ID_RE.match(value))


def latest_run_id(runs_dir: Path) -> str | None:
    """Newest existing run id under `runs_dir`, or None."""
    if not runs_dir.is_dir():
        return None
    ids = sorted(p.name for p in runs_dir.iterdir() if p.is_dir() and is_run_id(p.name))
    return ids[-1] if ids else None


@dataclass(frozen=True)
class RunContext:
    config: Config
    config_path: Path
    run_id: str

    @property
    def runs_dir(self) -> Path:
        return self.config.data_dir / "runs"

    @property
    def run_dir(self) -> Path:
        return self.runs_dir / self.run_id

    @property
    def raw_dir(self) -> Path:
        return self.config.data_dir / "raw" / self.run_id

    def stage_dir(self, stage: str) -> Path:
        return self.run_dir / stage

    @property
    def db_schema(self) -> str:
        """PostGIS schema of this run, e.g. `run_20261116t030000z`."""
        return f"run_{self.run_id.lower()}"
