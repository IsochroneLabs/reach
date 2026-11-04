"""cleanup plan: keep the last N published runs, never touch newer or protected runs."""

from __future__ import annotations

from pathlib import Path

from reach_pipeline.stages import cleanup

R = [f"202611{d:02d}T030000Z" for d in range(1, 8)]  # R[0] oldest … R[6] newest


def test_nothing_deleted_with_few_published_runs() -> None:
    p = cleanup.plan([R[3], R[1]], set(R), set(R), keep=3, protected={R[6]})
    assert p.keep == [R[3], R[1]] and p.drop_db == [] and p.drop_files == []


def test_older_runs_deleted_newer_unpublished_kept() -> None:
    published = [R[1], R[2], R[4], R[5]]  # R[0], R[3], R[6] were never published
    p = cleanup.plan(published, set(R), set(R), keep=3, protected={R[6]})
    assert p.keep == [R[5], R[4], R[2]]
    # R[3] lies between kept runs and R[6] is newer: both stay; R[0] and R[1] go
    assert p.drop_db == [R[0], R[1]]
    assert p.drop_files == [R[0], R[1]]


def test_protected_run_is_never_deleted() -> None:
    p = cleanup.plan(R[1:5], set(R), set(R), keep=3, protected={R[0]})
    assert p.drop_db == [R[1]]


def test_local_runs_and_delete(tmp_path: Path) -> None:
    for sub in ("runs", "raw"):
        for run_id in (R[0], R[1]):
            (tmp_path / sub / run_id / "x").mkdir(parents=True)
    (tmp_path / "runs" / "not-a-run").mkdir()
    assert cleanup.local_runs(tmp_path) == {R[0], R[1]}
    cleanup.delete_files(tmp_path, R[0])
    assert cleanup.local_runs(tmp_path) == {R[1]}
    assert (tmp_path / "runs" / "not-a-run").is_dir()
