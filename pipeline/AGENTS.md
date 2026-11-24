# pipeline/AGENTS.md

Rules for agents working in `pipeline/` (package `reach_pipeline`). The root `AGENTS.md` applies;
this file adds the stage pattern and wins where it is more specific.

## Stage pattern

- **CLI:** `python -m reach_pipeline <stage> [--run-id ID] [--config PATH]`, wrapped by
  `make pipeline STAGE=<stage>`; `run` executes all stages in `cli.STAGES` order. `--config`
  defaults to `$REACH_CONFIG`, else `config/config.yaml`; `--config` and `data_dir` are relative
  to the current directory, so run from the repository root. Run id: `--run-id`, else a new one
  for `run` and the first stage (`acquire`), else the latest existing run.
- **Stages:** `acquire → validate → tiles → publish → cleanup` exist; `travel_times` (S1.8) and
  `validate_results` (S1.9) are listed in `cli.PLANNED`: a single one exits with code 2 and a
  clear message, `run` logs each as skipped. Move a stage from `PLANNED` to `STAGES` when it is
  implemented (`test_stage_order` checks the order).
- **Run id:** UTC `YYYYMMDDTHHMMSSZ` (`context.new_run_id`); DB schema `run_<id lowercased>`.
- **One module per stage** in `src/reach_pipeline/stages/`, with `STAGE = "<name>"`,
  `CONFIG_SECTIONS` and one public `run(ctx: RunContext) -> Manifest`. Reusable logic lives in
  plain modules (`osm.py`, `zensus.py`, `boundary.py`, `gtfs.py`, …) as small pure functions;
  stage modules only do I/O and orchestration.
- **`RunContext`** (`context.py`) holds the typed `Config`, `config_path` and `run_id`, and gives
  the paths `data/raw/<run_id>/` and `data/runs/<run_id>/<stage>/`.
- **Start of a stage:** `manifest.require_ok(ctx.stage_dir(<previous>), <previous>, ctx.config)`
  checks the previous stage (status ok, input checksums and config digest unchanged). Then
  compute the own inputs with `[config_input(ctx.config, CONFIG_SECTIONS), *file_inputs([...])]`;
  if `is_up_to_date(read_manifest(stage_dir), inputs)`, return the old manifest (re-running with
  unchanged inputs is a no-op, AGENTS.md rule 7).
- **End of a stage:** wrap the work in `metrics.measure()`, then `write_manifest(...)` with inputs
  (checksums), outputs (path, rows), runtime and peak RSS. The CLI writes a `failed` manifest if
  the stage raises and posts to `$FAILURE_WEBHOOK_URL` if set (`notify.py`, never raises).
- **Config sections:** `CONFIG_SECTIONS` lists the top-level config sections a stage (and its
  helpers) reads; its config input is `config:<sections>` with the digest of exactly those
  sections (`config.section_digest`), so a change elsewhere, e.g. in `api`, never re-runs it.
  `publish` uses all pipeline sections (`meta.runs.config_hash`).
- **Errors and exit codes** (`errors.py`): `StageValidationError` → 1, `ConfigError` → 2,
  `ExternalError` → 3 (network, Valhalla, DB after retries). Raise them with a clear message;
  never `sys.exit` inside a stage.
- **Logging:** `log = logging.getLogger(__name__)`; the CLI sets `time level stage message`.
- **Config:** every tunable value comes from `config/config.yaml` through `config.Config`
  (unknown keys are errors). A new key needs a pydantic field, a comment in the YAML and, if it
  has rules, a validator plus a test in `tests/test_config.py`. `extends:` merges an override
  file (`config/test_clip.yaml`).
- **Outputs:** GeoParquet/Parquet in EPSG:25832 under the stage directory; schemas follow
  `docs/data_contract.md`. Only `publish` writes to PostGIS; `cleanup` only drops old run schemas
  (AGENTS.md rule 6).
- **OSM:** only through `osm.py` (osmium CLI: `tags-filter` → `extract` → `export` as GeoJSON
  lines → GeoPandas); never read the full PBF in Python. osmium's memory grows with the highest
  node id, not with the file size; keep the passes over the regional PBF few.
- **Raw inputs:** `acquire.raw_path(raw_dir, source, file)`; later stages never download.
- **Trip windows:** `gtfs.reference_date` picks one date per trip window (weekday, holidays in
  `calendar`, active services). Service days beyond 24:00 for night windows follow in S1.6.
- **Valhalla:** only through `valhalla/client.py` (`ValhallaClient`: async httpx, at most
  `valhalla.concurrency` requests in flight, retries on timeouts/5xx, `matrix()` with compact
  output, NaN = unreachable, targets split above `valhalla.max_matrix_pairs`). URL from
  `$VALHALLA_URL`, else `valhalla.url`; never a guessed port (notes N5). `costmatrix` for every
  matrix (notes N4). Times come from network routing, never from isochrones (AGENTS.md rule 2).
- **Tiles:** `tiles check` (flag file, no manifest) and `tiles verify` (manifest; also the step
  of `run`). Stages never call Docker; build, swap and restart are `make refresh` (O5).
- **Database:** only through `db.py` (psycopg, autocommit connections, every write inside
  `conn.transaction()`); `publish` and `cleanup` connect as `pipeline_write` via
  `$DATABASE_URL_PIPELINE`. SQL lives in `infra/db/` (`database.sql_dir`): `roles.sql` (re-applied
  every time), numbered `migrations/NNNN_name.sql` (applied once, recorded in
  `meta.schema_migrations`; never edit an applied one, add a new file) and `run_schema.sql`
  (template of `run_<id>`). `make migrate` applies roles and migrations as the superuser
  (`$DATABASE_URL_ADMIN`); `publish` does it first when that variable is set. A change to tables
  or views is a data-contract change: update `docs/data_contract.md` and
  `tests/test_db_contract.py` in the same branch (and ask first, AGENTS.md).

## Tests

- `pipeline/tests/test_<module>.py`, small fixtures in `pipeline/tests/fixtures/` (< 1 MB each).
- No network: Valhalla responses are recorded once into `tests/fixtures/valhalla/*.json` and
  replayed with `respx`; downloads are mocked with `respx` (`tests/test_acquire.py`).
- osmium tests run the real binary on `tests/fixtures/tiny.osm` (osmium-tool is required locally
  and in CI).
- Tests that write files use `tmp_path` and a config copy with `data_dir` inside it
  (`tests/test_manifest.py`).
- Database contract tests carry the `db` marker (deselected by default) and need a disposable
  PostGIS: `REACH_TEST_DATABASE_URL=postgresql://postgres:<pw>@localhost:5432/postgres uv run
  pytest -m db`. They create and drop their own database.
- Integration tests against a local Valhalla on the test clip go to `tests/integration/` with the
  `integration` marker (*planned*): serve the clip tiles with
  `make refresh REACH_CONFIG=config/test_clip.yaml`, then `uv run pytest -m integration`.
