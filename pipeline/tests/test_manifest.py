"""Manifests round-trip; the stage pattern writes, checks and skips as documented."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from reach_pipeline import cli
from reach_pipeline.config import load_config, pipeline_sections, section_digest
from reach_pipeline.context import RunContext, new_run_id
from reach_pipeline.errors import StageValidationError
from reach_pipeline.manifest import (
    FileOutput,
    Manifest,
    config_input,
    file_inputs,
    is_up_to_date,
    read_manifest,
    require_ok,
    write_manifest,
)
from reach_pipeline.metrics import measure
from reach_pipeline.stages import (
    acquire,
    cleanup,
    count,
    publish,
    recommend,
    score,
    tiles,
    validate,
    validate_results,
)

REPO = Path(__file__).resolve().parents[2]
STAGE_MODULES = (
    acquire,
    validate,
    tiles,
    count,
    score,
    recommend,
    validate_results,
    publish,
    cleanup,
)


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
    cfg = load_config(REPO / "config" / "config.yaml")
    with pytest.raises(StageValidationError, match="no manifest"):
        require_ok(tmp_path / "demo", "demo", cfg)

    write_manifest(_manifest(tmp_path, status="failed"), tmp_path / "demo")
    with pytest.raises(StageValidationError, match="did not finish ok"):
        require_ok(tmp_path / "demo", "demo", cfg)

    write_manifest(_manifest(tmp_path), tmp_path / "demo")
    assert require_ok(tmp_path / "demo", "demo", cfg).status == "ok"

    (tmp_path / "input.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(StageValidationError, match="inputs of stage 'demo' changed"):
        require_ok(tmp_path / "demo", "demo", cfg)


def test_require_ok_checks_config_sections(tmp_path: Path) -> None:
    cfg = load_config(REPO / "config" / "config.yaml")
    manifest = _manifest(tmp_path)
    manifest.inputs = [config_input(cfg, ("profiles",)), *manifest.inputs]
    write_manifest(manifest, tmp_path / "demo")
    assert manifest.inputs[0].path == "config:profiles"

    api_changed = cfg.model_copy(update={"api": {**cfg.api, "boundary_margin_m": 250}})
    assert require_ok(tmp_path / "demo", "demo", api_changed).status == "ok"

    profiles = {**cfg.profiles}
    profiles["walking_339"] = profiles["walking_339"].model_copy(update={"speed_kmh": 3.5})
    with pytest.raises(StageValidationError, match="config:profiles"):
        require_ok(tmp_path / "demo", "demo", cfg.model_copy(update={"profiles": profiles}))


def test_is_up_to_date(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    assert is_up_to_date(manifest, file_inputs([tmp_path / "input.txt"]))
    (tmp_path / "input.txt").write_text("changed", encoding="utf-8")
    assert not is_up_to_date(manifest, file_inputs([tmp_path / "input.txt"]))
    assert not is_up_to_date(None, [])


def _demo_stage(ctx: RunContext) -> Manifest:
    """Minimal stage following the pattern: digest of its config sections as input, no-op on
    re-run."""
    stage_dir = ctx.stage_dir("demo")
    inputs = [config_input(ctx.config, ("profiles", "time_budgets_min"))]
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
    assert first.inputs[0].path == "config:profiles,time_budgets_min"

    # Unchanged inputs: the second run is a no-op and keeps the manifest.
    assert cli.main(["demo", "--config", str(config_path)]) == 0  # latest run id reused
    assert read_manifest(stage_dir) == first


def _edit_yaml(path: Path, change) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_stage_reruns_only_when_its_sections_change(config_path: Path, demo: None) -> None:
    child = config_path.parent / "child.yaml"
    child.write_text("extends: config.yaml\n", encoding="utf-8")
    run_id = "20261102T120000Z"
    assert cli.main(["demo", "--run-id", run_id, "--config", str(child)]) == 0
    stage_dir = config_path.parent / "data" / "runs" / run_id / "demo"
    first = read_manifest(stage_dir)
    assert first is not None and len(first.inputs) == 1

    # The api section (read by reach_api only) and sections the stage does not use, in the
    # parent file: the stage stays a no-op and keeps its manifest.
    def unrelated(d: dict) -> None:
        d["api"]["boundary_margin_m"] = 250
        d["cleanup"]["keep_published_runs"] = 5

    _edit_yaml(config_path, unrelated)
    assert cli.main(["demo", "--run-id", run_id, "--config", str(child)]) == 0
    assert read_manifest(stage_dir) == first

    # A section it uses changes in the parent: the merged config differs, so it runs again.
    _edit_yaml(config_path, lambda d: d["time_budgets_min"].update(transit=12))
    assert cli.main(["demo", "--run-id", run_id, "--config", str(child)]) == 0
    second = read_manifest(stage_dir)
    assert second is not None and second.inputs != first.inputs


def test_config_sections_of_the_stages() -> None:
    assert {m.STAGE for m in STAGE_MODULES} == set(cli.STAGES)
    # Every pipeline section is used by at least one stage, `api` by none, and publish records
    # the digest of all pipeline sections (meta.runs.config_hash).
    used = {sec for module in STAGE_MODULES for sec in module.CONFIG_SECTIONS}
    assert "api" not in used
    assert used | {"data_dir"} == set(pipeline_sections())
    assert set(publish.CONFIG_SECTIONS) == set(pipeline_sections())


def test_api_section_leaves_every_stage_input_unchanged() -> None:
    cfg = load_config(REPO / "config" / "config.yaml")
    changed = cfg.model_copy(update={"api": {**cfg.api, "rate_limit": {"burst": 1}}})
    for module in STAGE_MODULES:
        assert config_input(cfg, module.CONFIG_SECTIONS) == config_input(
            changed, module.CONFIG_SECTIONS
        ), module.STAGE
    assert section_digest(cfg, pipeline_sections()) == section_digest(changed, pipeline_sections())


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


@pytest.fixture
def planned(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stage that is planned but not implemented (every real stage exists since P7)."""
    monkeypatch.setattr(cli, "PLANNED", {"later": "P9"})


@pytest.mark.usefixtures("planned")
def test_planned_stage_fails_clearly(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["later", "--config", str(config_path)]) == 2
    assert "stage 'later' is not implemented yet (planned in P9)" in capsys.readouterr().err


@pytest.mark.usefixtures("planned")
def test_failure_posts_to_webhook(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(cli.notify, "failure", lambda text: sent.append(text) or True)
    assert cli.main(["later", "--config", str(config_path)]) == 2
    assert len(sent) == 1 and "stage later" in sent[0] and "planned in P9" in sent[0]


def test_migrate_needs_admin_url(
    config_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL_ADMIN", raising=False)
    assert cli.main(["migrate", "--config", str(config_path)]) == 2
    assert "DATABASE_URL_ADMIN is not set" in capsys.readouterr().err


def test_action_only_for_tiles(config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["count", "check", "--config", str(config_path)]) == 2
    assert "'check' is only valid for the tiles stage" in capsys.readouterr().err


def test_tiles_check_runs_without_manifest(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []
    monkeypatch.setattr(cli.tiles, "check", lambda ctx: called.append(ctx.run_id) or True)
    assert (
        cli.main(["tiles", "check", "--config", str(config_path), "--run-id", "20261102T120000Z"])
        == 0
    )
    assert called == ["20261102T120000Z"]


@pytest.mark.usefixtures("planned")
def test_run_logs_planned_stages_as_skipped(
    config_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[str] = []
    stages = {
        name: (lambda ctx, name=name: seen.append(name) or _demo_stage(ctx)) for name in cli.STAGES
    }
    monkeypatch.setattr(cli, "STAGES", stages)
    assert cli.main(["run", "--config", str(config_path)]) == 0
    assert seen == [
        "acquire",
        "validate",
        "tiles",
        "count",
        "score",
        "recommend",
        "validate_results",
        "publish",
        "cleanup",
    ]
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
