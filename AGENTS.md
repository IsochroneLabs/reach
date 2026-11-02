# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Copilot, Cursor, …) working in this repository.
They apply to every agent session, on behalf of any team member. Humans: see `README.md` and
`CONTRIBUTING.md`. Folder-specific rules are in `pipeline/AGENTS.md`, `api/AGENTS.md` and
`web/AGENTS.md`; the nearest `AGENTS.md` to the file you edit takes precedence.

**Project:** `reach` measures 15-minute accessibility (walking, cycling, wheelchair) for the urban
area of Tübingen, finds underserved areas and recommends sites for new facilities. Course project
DS500, University of Tübingen. Automation, validation, documentation and a hosted app are graded.

## Commands

Run from the repository root. If a command does not exist yet, say so; do not invent a substitute.

| Task | Command |
|---|---|
| Install / update Python env | `uv sync` |
| Lint + format check | `uv run ruff check . && uv run ruff format --check .` |
| Tests (all Python) | `uv run pytest` |
| Tests (one package) | `uv run pytest pipeline/tests` · `uv run pytest api/tests` |
| Start local stack | `make up` (Docker Compose: Caddy, API, PostGIS, Valhalla) |
| Run pipeline | `make pipeline` · single stage: `make pipeline STAGE=count` |
| Frontend | `cd web && npm ci && npm run dev` · checks: `npm run lint && npm run build` |
| Add Python dependency | `uv add --package pipeline <pkg>` / `--package api` / `--dev` |

## Stack

Python 3.12 via uv (one workspace: `pipeline`, `api`; one `uv.lock`) · FastAPI · PostgreSQL + PostGIS
· Valhalla (official Docker image, tag pinned in `compose.yaml`) · React + TypeScript + Vite +
MapLibre GL JS · Docker Compose · GitHub Actions. Exact versions live in `pyproject.toml`,
`uv.lock`, `web/package.json` and `compose.yaml`; do not change them without asking.

## Where things are

| Path | Content |
|---|---|
| `pipeline/` | Data pipeline: acquire → validate → tiles → count → score → recommend → publish |
| `api/` | FastAPI: read endpoints from `current` schema, live endpoints calling Valhalla |
| `web/` | Frontend (static build served by Caddy) |
| `config/config.yaml` | Study area, profiles, categories + OSM tags, thresholds — **all tunable values** |
| `config/valhalla.json` | Valhalla limits |
| `infra/` | Dockerfiles, Caddyfile, DB roles/migrations, systemd timer |
| `docs/architecture.md` | **Binding description of the system** (versioned, with change log) |
| `docs/data_contract.md` | Tables and files exchanged between pipeline and API |
| `docs/notes.md` | Open points and future work |
| `CHANGELOG.md` | Project change history (`Unreleased` section, then one section per release) |
| `data/` | Local data, **git-ignored**, never committed |

## How to work on a task

1. **Understand.** Read the task, the relevant sections of `docs/architecture.md`,
   `docs/data_contract.md` and `docs/notes.md`, and the existing code you will touch. Search the
   repo for functions that already do what you need before writing new ones.
2. **See the whole project.** Check what your change affects downstream: data contract, other
   pipeline stages, API, frontend, config, tests, docs, deployment. Name these effects in your plan.
3. **Plan and confirm.** For anything beyond a small local fix (several files, new module, schema,
   config, dependency, structure) state a short plan and wait for confirmation.
4. **Implement in small steps.** Run lint and tests after each step; keep the code working.
5. **Verify with evidence.** Run the checks and, for pipeline work, the stage on the small test
   clip. Report commands and results; never claim something works without running it.
6. **Update docs and history** (see below) in the same branch.
7. **Report.** End with: branch, commits, PR link (if opened), open points, any doc changes.

## Architecture rules (do not break)

1. **Valhalla is the only routing engine.** No OSMnx/NetworkX/pandana/r5py routing.
2. **Count with the matrix (`sources_to_targets`), never with isochrone polygons.** Isochrones are
   display only. Follow `docs/architecture.md` §6.5 (one matrix for all categories, spatial blocks,
   exact straight-line prefilter, cached live calls).
3. **CRS:** convert to EPSG:25832 on ingest; keep Zensus cell IDs (EPSG:3035) as keys; transform
   to EPSG:4326 only at the API (`ST_Transform`). Never compute distances in degrees.
4. **No hard-coded values:** thresholds, speeds, tags, URLs and paths come from `config/` or `.env`.
5. **Store raw counts and times;** classes and deficits are derived at read time.
6. **Only the `publish` stage writes to PostGIS.** The API reads only from the `current` schema.
7. **Pipeline stages are idempotent** and write a manifest; each stage checks the previous manifest.
8. **No public data APIs at runtime** (Overpass, Nominatim). OSM data comes from the clipped Geofabrik extract.

## Architecture and docs stay in sync

`docs/architecture.md` describes what the code must do. Code and docs must never disagree.

- **If the implementation needs to differ from `architecture.md`** (it does not work as described,
  a better approach exists, a value or interface changes): **stop, explain the deviation and the
  proposed doc change, and ask for confirmation before continuing.** After confirmation,
  implement it **and** update `architecture.md` in the same branch. Never diverge silently.
- If you find existing code that already disagrees with `architecture.md`, report it; do not
  "fix" either side without asking.
- Every change to `architecture.md`: bump its version line (`draft v0.N` → `v0.N+1`), add one
  line to its **Change log** section (date, what changed, why), and move settled questions from
  "Open" to "Settled" in §13 with the date.
- Also update in the same branch, when affected: `docs/data_contract.md` (any table, column or
  file schema), `README.md` (commands, setup, structure, data sources), `config/config.yaml`
  comments, the folder's `AGENTS.md`, and `docs/notes.md` (add or close open points).
- New ideas or deferred work go to `docs/notes.md`, not into code comments or TODOs.

## Writing efficient code

The production server has 2 vCPU and 4 GB RAM shared by PostGIS, Valhalla, the API and the
pipeline. Write for that.

- **Vectorise.** Use pandas/GeoPandas operations, spatial joins and spatial indexes
  (`sjoin`, `sindex`, `STRtree`); no Python loops over cells or facilities.
- **Stream large inputs.** Read big files (GTFS `stop_times.txt`, PBF, Zensus CSV) with DuckDB,
  Polars or pyarrow and filter while reading; never load a whole large file into pandas.
- **Batch Valhalla calls** as in architecture §6.5; async client with bounded concurrency.
- **Compute once, reuse.** Cache intermediate results per run (GeoParquet); do not recompute what
  an earlier stage produced.
- **Measure pipeline stages:** log runtime and peak memory; mention them in the PR when a stage
  changes.
- **Keep it simple.** Small pure functions, I/O at the edges, no abstraction "for later", no new
  framework or service without asking. Delete dead code instead of commenting it out.

## Code style

- Python: ruff (line length 100), type hints on public functions, short docstrings for public
  modules and functions, `logging` instead of `print`, meaningful names.
- Errors: fail loudly with a clear message and non-zero exit code; retries only for network calls.

```python
# good: config-driven, metric CRS, explicit
radius_m = cfg.profiles[profile].speed_kmh * 1000 / 60 * cfg.time_budget_min
candidates = facilities[facilities.distance(cell.geometry) <= radius_m]

# bad: magic number, degrees, hidden assumption
candidates = facilities[facilities.distance(cell.geometry) <= 0.008]
```

## Tests and checks

Before every commit that touches code: lint and the tests of the touched package must pass. New
pipeline logic gets a unit test with a small fixture (no network, no real downloads). A schema
change gets a data-contract test. Report the commands and results in the PR.

## Committing

**What goes into one commit:** one logical change that leaves the code working — the code, its
tests, and the docs/config/lockfile changes it requires. `pyproject.toml` and `uv.lock` always
together. Formatting-only or refactoring changes in separate commits from behaviour changes.

**Never commit:** anything in `data/` or other datasets, files > 10 MB, `.env`, keys, tokens,
passwords, `.venv/`, caches, notebook outputs, generated build output (`web/dist/`). Missing
`.gitignore` entry → add it in the same branch. Secret committed by accident → tell the human
immediately; the key must be rotated (deleting it later does not remove it from history).

**Before committing:** `git status` and `git diff --staged`; stage files explicitly (no blind
`git add .`).

**Message:** Conventional Commits in English:

```
<type>(<scope>): <imperative summary, max ~72 chars>

<body: what and why, not how>

Closes #12
Co-authored-by: Claude <noreply@anthropic.com>
```

Types: `feat fix docs refactor test data chore style ci`. Scope: `pipeline`, `api`, `web`,
`infra`, `config`, `docs`, `repo`. Not okay: `update`, `wip`, `fix stuff`, `changes`.
Every commit made by an agent ends with a co-author trailer for the assistant used.

## Branches, pull requests, versions

- Base branch: **`dev`**. `main` only receives milestone releases via PR from `dev`.
- Branch per topic from fresh `dev` (`git fetch --all --prune` first):
  `feature/…`, `fix/…`, `docs/…`, `refactor/…`, `data/…`, `exp/…`; issue number prefix if there is
  one (`feature/12-matrix-batching`). One branch = one topic, short-lived.
- Behind `dev`: `git rebase origin/dev` on your **own** branch, re-run checks, then
  `git push --force-with-lease`.
- Pull requests target `dev`; title in Conventional Commit format; body uses the template in
  `CONTRIBUTING.md` (What / Why / How tested / Open points / Related) and states on whose behalf
  the agent worked. Keep PRs reviewable in ~15 minutes. Merged with "Squash and merge".
- **Version history:** add a line under `## [Unreleased]` in `CHANGELOG.md` for every user-visible
  or architectural change (Added / Changed / Fixed / Removed). Releases use Semantic Versioning
  tags on `main` (`v0.1.0` interim, `v1.0.0` submission) with a GitHub Release; tagging and
  releasing only on explicit request.
- Merge conflicts: never accept one side blindly; explain both versions and propose a resolution;
  ask before resolving conflicts in another person's code.

## Boundaries

**Always**
- Work on a topic branch; keep the change to the task you were given.
- Keep `architecture.md`, `data_contract.md`, `README.md` and `CHANGELOG.md` in sync with the code.
- Ask when a requirement is unclear or the task touches another person's folder (see `.github/CODEOWNERS`).

**Ask first (wait for explicit confirmation)**
- Any change to `docs/architecture.md`, or implementing something that deviates from it.
- Adding, removing or upgrading dependencies.
- Changing `config/`, `compose*.yaml`, `infra/`, CI workflows, the data contract or the repo structure.
- Changes in more than one top-level folder, or anything outside the task.
- Pushing, opening or updating a PR or issue, deleting branches or files, tagging, releasing.

**Never**
- Commit or push directly to `main` or `dev`; `git push --force` on `main`/`dev`; `git reset --hard`
  on shared branches; rewrite or delete someone else's branch; merge PRs unless explicitly told to.
- Commit data, secrets or large files (see Committing).
- Use `pip install` or hand-made virtual environments (use uv).
- Disable tests, lint rules or validation checks to make something pass.
- Expose Valhalla or PostGIS ports publicly in production configs.

## Working in parallel

Each person (and each agent session) works on its own branch; parallel sessions use separate git
worktrees. Before opening a PR, review the diff in a fresh session or by a teammate; the author
does not approve their own PR.

## Keeping this file useful

Keep it short. When an agent repeats the same mistake, add one precise rule here (ask first); remove
rules that no longer apply. Detailed explanations belong in `docs/` or `CONTRIBUTING.md`.
