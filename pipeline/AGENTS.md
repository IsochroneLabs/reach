# pipeline/AGENTS.md

Rules for agents working in `pipeline/` (package `reach_pipeline`). The root `AGENTS.md` applies;
this file adds the stage pattern (note N2) and wins where it is more specific.

## Stage pattern

- **CLI:** `python -m reach_pipeline <stage> [--run-id ID] [--config PATH]`, wrapped by
  `make pipeline STAGE=<stage>`; `run` executes all stages in `cli.STAGES` order.
  `--config` defaults to `$REACH_CONFIG`, else `config/config.yaml`; `--config` and `data_dir`
  are relative to the current directory, so run from the repository root. Run id: `--run-id`, else a new one for `run`, else the latest existing run.
- **Run id:** UTC `YYYYMMDDTHHMMSSZ` (`context.new_run_id`); DB schema `run_<id lowercased>`.
- **One module per stage** in `src/reach_pipeline/stages/`, with `STAGE = "<name>"` and one
  public `run(ctx: RunContext) -> Manifest`. Register it in `cli.STAGES` in execution order.
  Reusable logic lives in plain modules (`osm.py`, `count.py`, …) as small pure functions;
  stage modules only do I/O and orchestration.
- **`RunContext`** (`context.py`) holds the typed `Config`, `config_path` and `run_id`, and
  gives the paths: `data/raw/<run_id>/`, `data/runs/<run_id>/<stage>/`.
- **Start of a stage:** `manifest.require_ok(ctx.stage_dir(<previous>), <previous>)` checks the
  previous stage (status ok, input checksums unchanged). Then compute the own inputs with
  `file_inputs([...])`; if `is_up_to_date(read_manifest(stage_dir), inputs)`, return the old
  manifest (re-running with unchanged inputs is a no-op).
- **End of a stage:** wrap the work in `metrics.measure()`, then `write_manifest(...)` with
  inputs (checksums), outputs (path, rows), runtime and peak RSS. Peak RSS is the process
  high-water mark up to the end of the stage: under `run`, a stage reports at least the peak of
  earlier stages. Config inputs are `config_files(ctx.config_path)` (the whole `extends` chain). The CLI writes a `failed`
  manifest if the stage raises.
- **Errors and exit codes** (`errors.py`): `StageValidationError` → 1, `ConfigError` → 2,
  `ExternalError` → 3 (network, Valhalla, DB after retries). Raise them with a clear message;
  never `sys.exit` inside a stage.
- **Logging:** `log = logging.getLogger(__name__)`; the CLI sets the format
  `time level stage message`. No `print`.
- **Config:** every tunable value comes from `config/config.yaml` through `config.Config`.
  A new key needs a pydantic field, a comment in the YAML and, if it has rules, a validator plus
  a test in `tests/test_config.py`. `extends:` merges an override file (see `test_clip.yaml`).
- **Outputs:** GeoParquet/Parquet in EPSG:25832 under the stage directory; schemas follow
  `docs/data_contract.md`. Only `publish` writes to PostGIS.

## Tests

- `pipeline/tests/test_<module>.py`, small fixtures in `pipeline/tests/fixtures/` (< 1 MB each).
- No network: Valhalla responses are recorded once into `tests/fixtures/valhalla/*.json` and
  replayed with `respx`; downloads are mocked.
- Tests that write files use `tmp_path` and a config copy with `data_dir` inside it
  (see `tests/test_manifest.py`).
- Integration tests against a local Valhalla on the test clip go to `tests/integration/` and
  carry the `integration` marker.
