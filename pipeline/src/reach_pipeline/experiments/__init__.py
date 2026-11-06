"""Validation experiments V1–V11 (methodology §6) on a finished run.

`python -m reach_pipeline.experiments [V01 …] [--run-id ID]` (`make experiments`) runs them;
results go to `<data_dir>/experiments/<run_id>/vNN/` with a `result.json` each, and `summary`
collects them into `summary.md`. `docs/validation_report.md` interprets the numbers.
Settings: `config/experiments.yaml`.
"""
