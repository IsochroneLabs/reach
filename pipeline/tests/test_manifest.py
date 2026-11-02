"""Manifests round-trip; the stage pattern writes, checks and skips as documented."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from reach_pipeline import cli
from reach_pipeline.config import config_files, load_config
from reach_pipeline.context import RunContext, new_run_id
from reach_pipeline.errors import StageValidationError
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

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Repo config with data_dir pointing into tmp_path."""
    data = yaml.safe_load((REPO / "config" / "config.yaml").read_text(encoding="utf-8"))
    data["data_dir"] = str(tmp_path / "data")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _manifest(tmp_path: Path, status: str = "ok") -> Manifest:
    src = tmp_path / "input.txt"
    src.write_text("hello", encoding="utf-8")
    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    return Manifest(
        stage="demo",
        run_id="20261102T120000Z",
        status=status,
        started_at=now,
        finished_at=now,
        runtime_s=0.5,
        peak_rss_mb=42.0,
        inputs=file_inputs([src]),
        outputs=[FileOutput(path="out.parquet", rows=3)],
    )


def test_round_trip(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    path = write_manifest(manifest, tmp_path / "demo")
    assert read_manifest(tmp_path / "demo") == manifest
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["inputs"][0]["sha256"] == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_require_ok(tmp_path: Path) -> None:
    with pytest.raises(StageValidationError, match="no manifest"):
        require_ok(tmp_path / "demo", "demo")

    write_manifest(_manifest(tmp_path, status="failed"), tmp_path / "demo")
    with pytest.raises(StageValidationError, match="did not finish ok"):
        require_ok(tmp_path / "demo", "demo")

    write_manifest(_manifest(tmp_path), tmp_path / "demo")
    assert require_ok(tmp_path / "demo", "demo").status == "ok"

    (tmp_path / "input.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(StageValidationError, match="inputs of stage 'demo' changed"):
        require_ok(tmp_path / "demo", "demo")


def test_is_up_to_date(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    assert is_up_to_date(manifest, file_inputs([tmp_path / "input.txt"]))
    (tmp_path / "input.txt").write_text("changed", encoding="utf-8")
    assert not is_up_to_date(manifest, file_inputs([tmp_path / "input.txt"]))
    assert not is_up_to_date(None, [])


def _demo_stage(ctx: RunContext) -> Manifest:
    """Minimal stage following the pattern: config checksum as input, no-op on re-run."""
    stage_dir = ctx.stage_dir("demo")
    inputs = file_inputs(config_files(ctx.config_path))
    previous = read_manifest(stage_dir)
    if is_up_to_date(previous, inputs):
        return previous
    now = datetime.now(UTC)
    with measure() as m:
        pass
    manifest = Manifest(
        stage="demo",
        run_id=ctx.run_id,
        status="ok",
        started_at=now,
        finished_at=datetime.now(UTC),
        runtime_s=m.runtime_s,
        peak_rss_mb=m.peak_rss_mb,
        inputs=inputs,
    )
    write_manifest(manifest, stage_dir)
    return manifest


@pytest.fixture
def demo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register the demo stage (not the first stage, so it reuses the latest run)."""
    monkeypatch.setitem(cli.STAGES, "demo", _demo_stage)


def test_stage_writes_manifest_and_skips_rerun(config_path: Path, demo: None) -> None:
    run_id = "20261102T120000Z"
    assert cli.main(["demo", "--run-id", run_id, "--config", str(config_path)]) == 0
    stage_dir = config_path.parent / "data" / "runs" / run_id / "demo"
    first = read_manifest(stage_dir)
    assert first is not None and first.status == "ok" and first.peak_rss_mb > 0
    assert first.inputs[0].path == str(config_path)

    # Unchanged inputs: the second run is a no-op and keeps the manifest.
    assert cli.main(["demo", "--config", str(config_path)]) == 0  # latest run id reused
    assert read_manifest(stage_dir) == first


def test_stage_reruns_when_parent_config_changes(config_path: Path, demo: None) -> None:
    child = config_path.parent / "child.yaml"
    child.write_text("extends: config.yaml\n", encoding="utf-8")
    run_id = "20261102T120000Z"
    assert cli.main(["demo", "--run-id", run_id, "--config", str(child)]) == 0
    stage_dir = config_path.parent / "data" / "runs" / run_id / "demo"
    first = read_manifest(stage_dir)
    assert first is not None and len(first.inputs) == 2

    # Only the parent changes; the merged config differs, so the stage must run again.
    config_path.write_text(config_path.read_text(encoding="utf-8") + "\n# edit\n", "utf-8")
    assert cli.main(["demo", "--run-id", run_id, "--config", str(child)]) == 0
    second = read_manifest(stage_dir)
    assert second is not None and second.inputs != first.inputs


def test_failed_stage_writes_failed_manifest(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(ctx: RunContext) -> Manifest:
        raise StageValidationError("broken input")

    monkeypatch.setitem(cli.STAGES, "demo", boom)
    run_id = "20261102T120000Z"
    assert cli.main(["demo", "--run-id", run_id, "--config", str(config_path)]) == 1
    manifest = read_manifest(config_path.parent / "data" / "runs" / run_id / "demo")
    assert manifest is not None and manifest.status == "failed"
    assert "broken input" in manifest.message


def test_config_error_exit_code(tmp_path: Path) -> None:
    assert cli.main(["validate", "--config", str(tmp_path / "missing.yaml")]) == 2


def test_invalid_run_id_exit_code(config_path: Path) -> None:
    assert cli.main(["validate", "--run-id", "latest", "--config", str(config_path)]) == 2


def test_stage_order() -> None:
    assert list(cli.STAGES)[:2] == ["acquire", "validate"]
    assert not set(cli.STAGES) & set(cli.PLANNED)


def test_planned_stage_fails_clearly(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["count", "--config", str(config_path)]) == 2
    assert "stage 'count' is not implemented yet (planned in P3)" in capsys.readouterr().err


def test_run_logs_planned_stages_as_skipped(
    config_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []
    stages = {
        name: (lambda ctx, name=name: seen.append(name) or _demo_stage(ctx)) for name in cli.STAGES
    }
    monkeypatch.setattr(cli, "STAGES", stages)
    assert cli.main(["run", "--config", str(config_path)]) == 0
    assert seen == ["acquire", "validate"]
    err = capsys.readouterr().err  # the CLI logs to stderr
    for name, phase in cli.PLANNED.items():
        assert f"stage {name} skipped: not implemented yet (planned in {phase})" in err


def test_first_stage_starts_a_new_run(config_path: Path) -> None:
    runs = config_path.parent / "data" / "runs"
    (runs / "20261102T120000Z").mkdir(parents=True)
    assert cli._resolve_run_id(None, "validate", runs) == "20261102T120000Z"
    assert cli._resolve_run_id(None, "acquire", runs) != "20261102T120000Z"
    assert cli._resolve_run_id(None, "run", runs) != "20261102T120000Z"


def test_run_id_and_schema(config_path: Path) -> None:
    run_id = new_run_id(datetime(2026, 11, 16, 3, 0, tzinfo=UTC))
    assert run_id == "20261116T030000Z"
    ctx = RunContext(config=load_config(config_path), config_path=config_path, run_id=run_id)
    assert ctx.db_schema == "run_20261116t030000z"
