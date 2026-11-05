# pipeline/AGENTS.md

Rules for agents working in `pipeline/` (package `reach_pipeline`). The root `AGENTS.md` applies;
this file adds the stage pattern (note N2) and wins where it is more specific.

## Stage pattern

- **CLI:** `python -m reach_pipeline <stage> [--run-id ID] [--config PATH]`, wrapped by
  `make pipeline STAGE=<stage>`; `run` executes all stages in `cli.STAGES` order.
  `--config` defaults to `$REACH_CONFIG`, else `config/config.yaml`; `--config` and `data_dir`
  are relative to the current directory, so run from the repository root. Run id: `--run-id`, else a new one for `run` and the first stage (`acquire`), else the latest
  existing run. Stages that are not implemented yet are listed in `cli.PLANNED`: a single one
  exits with code 2 and a clear message, `run` logs each as skipped.
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
  `docs/data_contract.md`. Only `publish` writes to PostGIS; `cleanup` only drops old run
  schemas (AGENTS.md rule 6).
- **OSM:** only through `osm.py` (osmium CLI: `tags-filter` → `extract` → `export` as GeoJSON
  lines → GeoPandas); never read the full PBF in Python. osmium's memory grows with the highest
  node ID (about 1.7 GB per ID bitmap), not with the file size; keep the number of
  `extract`/`tags-filter` passes over the regional PBF small.
- **Raw inputs:** `acquire.raw_path(raw_dir, source, file)`; later stages never download.
- **Valhalla:** only through `valhalla/client.py` (`ValhallaClient`: async httpx, at most
  `valhalla.concurrency` requests in flight, retries on timeouts/5xx, `matrix()` with compact
  output, NaN = unreachable, target sets split above `valhalla.max_matrix_pairs`). The URL comes
  from `$VALHALLA_URL`, else `valhalla.url`. Counting follows arch. §6.5: blocks
  (`count.make_blocks`), exact prefilter (`count.prefilter`), one matrix per block for all
  categories and stops, split afterwards (`count.count_block`, `count.transit_block`).
- **Tiles:** `tiles check` (flag file, no manifest) and `tiles verify` (manifest; also the step of
  `run`). Stages never call Docker; the build, swap and restart are `make refresh` (O19).
- **Stages after count:** `score` (only `thresholds.parquet`; classes and deficits are SQL views),
  `validate_results` (report part 2; a `fail` stops the run), `publish`, `cleanup`. `recommend`
  (P7) goes between `score` and `validate_results`.
- **Database:** only through `db.py` (psycopg, autocommit connections, every write inside
  `conn.transaction()`). Only `publish` loads data and `cleanup` drops old run schemas (arch. §7);
  both connect as `pipeline_write` via `$DATABASE_URL_PIPELINE`. SQL lives in `infra/db/`
  (`database.sql_dir`): `roles.sql` (re-applied every time), numbered `migrations/NNNN_name.sql`
  (applied once, recorded in `meta.schema_migrations`; never edit an applied one, add a new file)
  and `run_schema.sql` (template of `run_<id>`, run with `search_path = run_<id>, public`).
  `python -m reach_pipeline migrate` (`make migrate`) applies roles and migrations as the
  superuser (`$DATABASE_URL_ADMIN`); `publish` does it first when that variable is set. A change
  to tables or views is a data-contract change: update `docs/data_contract.md` and
  `tests/test_db_contract.py` in the same branch.
- **Environment:** `make` passes `.env` to the pipeline (`uv run --env-file .env`); a failed
  stage posts to `$FAILURE_WEBHOOK_URL` if set (`notify.py`, never raises).

## Tests

- `pipeline/tests/test_<module>.py`, small fixtures in `pipeline/tests/fixtures/` (< 1 MB each).
- No network: Valhalla responses are recorded once into `tests/fixtures/valhalla/*.json` and
  replayed with `respx`; downloads are mocked with `respx` (see `tests/test_acquire.py`).
- osmium tests run the real binary on the hand-made `tests/fixtures/tiny.osm` (osmium-tool is a
  requirement locally and in CI).
- Tests that write files use `tmp_path` and a config copy with `data_dir` inside it
  (see `tests/test_manifest.py`).
- Database contract tests carry the `db` marker (deselected by default) and need a disposable
  PostGIS: `REACH_TEST_DATABASE_URL=postgresql://postgres:<pw>@localhost:5432/postgres uv run
  pytest -m db`. They create and drop their own database; CI runs them in the job `db-contract`
  with a PostGIS service container.
- Integration tests against a local Valhalla on the test clip go to `tests/integration/` and
  carry the `integration` marker; they are deselected by default. Run them with the clip tiles
  served: `make refresh REACH_CONFIG=config/test_clip.yaml`, then `uv run pytest -m integration`.
