"""Stage manifests: what a stage read and wrote, how long it took, and whether it succeeded."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from reach_pipeline.errors import StageValidationError

MANIFEST_NAME = "manifest.json"
_CHUNK = 1 << 20


class FileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str


class FileOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    rows: int | None = None


class Manifest(BaseModel):
    """Contents of `data/runs/<run_id>/<stage>/manifest.json` (docs/data_contract.md)."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    run_id: str
    status: Literal["ok", "failed"]
    started_at: datetime
    finished_at: datetime
    runtime_s: float
    peak_rss_mb: float
    inputs: list[FileInput] = Field(default_factory=list)
    outputs: list[FileOutput] = Field(default_factory=list)
    message: str = ""


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def file_inputs(paths: list[Path]) -> list[FileInput]:
    """Inputs with checksums, in the given order."""
    return [FileInput(path=str(p), sha256=sha256_file(p)) for p in paths]


def write_manifest(manifest: Manifest, stage_dir: Path) -> Path:
    stage_dir.mkdir(parents=True, exist_ok=True)
    path = stage_dir / MANIFEST_NAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)  # atomic: a reader never sees a half-written manifest
    return path


def read_manifest(stage_dir: Path) -> Manifest | None:
    path = stage_dir / MANIFEST_NAME
    if not path.exists():
        return None
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def require_ok(stage_dir: Path, stage: str) -> Manifest:
    """Manifest of a previous stage; fails if it is missing, failed or its inputs changed."""
    manifest = read_manifest(stage_dir)
    if manifest is None:
        raise StageValidationError(f"stage {stage!r} has no manifest in {stage_dir}; run it first")
    if manifest.status != "ok":
        raise StageValidationError(f"stage {stage!r} did not finish ok: {manifest.message}")
    changed = [i.path for i in manifest.inputs if not _unchanged(i)]
    if changed:
        raise StageValidationError(f"inputs of stage {stage!r} changed since it ran: {changed}")
    return manifest


def is_up_to_date(manifest: Manifest | None, inputs: list[FileInput]) -> bool:
    """True if a previous ok run of this stage used exactly these inputs (re-run is a no-op)."""
    return manifest is not None and manifest.status == "ok" and manifest.inputs == inputs


def _unchanged(item: FileInput) -> bool:
    path = Path(item.path)
    return path.exists() and sha256_file(path) == item.sha256
