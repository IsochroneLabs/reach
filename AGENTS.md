# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Copilot, Cursor, …) working in this repository.
They apply to every agent session, on behalf of any team member. Humans: see `README.md` and
`CONTRIBUTING.md`. Folder-specific rules will live in `pipeline/AGENTS.md`, `api/AGENTS.md` and
`web/AGENTS.md`; the nearest `AGENTS.md` to the file you edit takes precedence.

**Project:** `reach` measures 15-minute accessibility (walking, cycling, wheelchair) for all residents
of the city of Tübingen, finds underserved areas and recommends sites for new facilities. Course project
DS500, University of Tübingen. Automation, validation, documentation and a hosted app are graded.

**Status:** P4 merged, P5 next — `docs/` (incl. a draft `docs/data_contract.md`), `config/config.yaml`,
`config/valhalla.json`, `Makefile` (incl. `refresh`, `migrate`), `compose.yaml` (db, valhalla,
valhalla-build, api placeholder, caddy placeholder), `.github/` (CI incl. the PostGIS
data-contract job), `infra/db/` (roles, migrations, run schema) and the pipeline stages
`acquire`, `validate`, `tiles`, `count`, `score`, `validate_results`, `publish` and `cleanup`
exist; `recommend`, the API endpoints, `web/`, `compose.prod.yaml` and the rest of `infra/` are
planned. If a file, folder or command referenced here does not exist yet, say so; do not invent a
substitute.

## Terms and roles

| Term | Meaning |
|---|---|
| **you** | The coding agent reading this file (any tool, any session). |
| **your human** | The team member who started your session and gives you the task. Confirmations come from them. |
| **we / the team** | **Rico** (GitHub `RicoS03`), **Socke** (`konstantinholl`), **Juju** (`nicholas-tuebi`). |
| **owner** | Team member responsible for a folder (`.github/CODEOWNERS`); reviews changes there. |
| **supervisors** | Course supervisors; read-only users of the app and the database, not contributors. |
| **ask first** | Stop, describe what you want to do and why, and wait for your human's explicit "yes". |

Project vocabulary (cell, origin, profile, reach, count, class, deficit, run, stage, manifest,
`current`, O/M/V/N numbers, …) is defined in [`docs/glossary.md`](docs/glossary.md). Use these
terms consistently in code, docs and messages.

## Sources of truth

| Document | Binding for |
|---|---|
| `docs/architecture.md` | System: components, data flow, Valhalla usage, deployment, decisions (O-numbers) |
| `docs/methodology.md` | What is measured: categories, thresholds, scoring, recommender, validation (V-numbers) |
| `docs/data_contract.md` (draft) | Table and file schemas between pipeline and API |
| `AGENTS.md`, `CONTRIBUTING.md` | How to work in this repo |

`docs/features.md` (features and roadmap), `docs/notes.md` (open points) and
`docs/project_management_decisions.md` (team organisation) are informative. If documents disagree,
`architecture.md` and `methodology.md` win — report the conflict instead of picking a side.

## Commands

Run from the repository root.

| Task | Command |
|---|---|
| Install / update Python env | `uv sync` |
| Lint + format check | `uv run ruff check . && uv run ruff format --check .` |
| Tests (all Python) | `uv run pytest` |
| Tests (one package) | `uv run pytest pipeline/tests` · `uv run pytest api/tests` |
| Start local stack | `make up` (Docker Compose: Caddy, API, PostGIS, Valhalla once tiles exist) |
| Run pipeline | `make pipeline` · single stage: `make pipeline STAGE=count` |
| Full refresh incl. tile build | `make refresh` (test clip: `make refresh REACH_CONFIG=config/test_clip.yaml`) |
| Integration tests (local Valhalla on the clip) | `uv run pytest -m integration` |
| DB contract tests (disposable PostGIS) | `REACH_TEST_DATABASE_URL=<superuser URL> uv run pytest -m db` |
| DB roles + migrations | `make migrate` (needs `DATABASE_URL_ADMIN` in `.env`) |
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
| `tests/integration/`, `tests/fixtures/` | End-to-end test on the test clip; small shared fixtures |
| `docs/` | Architecture, methodology, glossary, notes, features, team decisions |
| `CHANGELOG.md` | Project change history (`Unreleased`, then one section per release) |
| `data/` | Local data, **git-ignored**, never committed |

## How to work on a task

1. **Understand.** Read the task, the relevant sections of the sources of truth and
   `docs/notes.md`, and the code you will touch. Search the repo for functions that already do what
   you need before writing new ones.
2. **See the whole project.** Check what your change affects downstream: data contract, other
   pipeline stages, API, frontend, config, tests, docs, deployment. Name these effects in your plan.
3. **Plan and confirm.** For anything beyond a small local fix (several files, new module, schema,
   dependency, structure) state a short plan and wait for confirmation.
4. **Implement in small steps.** Run lint and tests after each step; keep the code working.
5. **Verify with evidence.** Run the checks and, for pipeline work, the stage on the test clip.
   Report commands and results; never claim something works without running it.
6. **Update docs and history** (see below) in the same branch.
7. **Report.** End with: branch, commits, PR link (if opened), open points, doc changes.

## Prompting

**How the team writes tasks for you** (template; short prompts are fine for small fixes):

```text
Goal:        what should work afterwards (one or two sentences)
Context:     relevant files, docs sections, issue number
Scope:       folders/files you may change; what is out of scope
Constraints: decisions, performance limits, things not to touch
Done when:   checks that must pass, expected output, docs to update
Output:      commit/PR wanted? summary format?
```

**How you handle a prompt**

- **Restate before acting** when the task is ambiguous or larger than a small fix: what you
  understood, the files you will touch and your plan; then wait.
- **Ask few, precise questions.** Bundle them (at most 3–4), offer a recommended option for each,
  and only ask what you cannot find in the repo or docs.
- **Do exactly the task.** No unrequested features, refactors or renames. Note improvements as
  suggestions at the end (or as an N-entry in `docs/notes.md` after asking).
- **Check the prompt against the docs.** If the request conflicts with a source of truth or this
  file, say so and ask instead of choosing silently.
- **Prefer the repo over memory.** Read config, code and docs instead of assuming APIs, column
  names or versions; look up external facts (library APIs, data sources) when unsure.
- **Language:** reply in the language of the prompt; code, comments, commit messages, PRs and docs
  are always English.
- **Report concisely:** what changed, how it was verified, what is open.
- "Just do it" does not override **Never** rules or the **Ask first** list.

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

## Docs stay in sync with the code

Code and the sources of truth must never disagree.

- **If the implementation needs to differ from `architecture.md` or `methodology.md`** (it does
  not work as described, a better approach exists, a value or interface changes): **stop, explain
  the deviation and the proposed doc change, and ask first.** After confirmation, implement it
  **and** update the document in the same branch. Never diverge silently.
- Found code that already disagrees with the docs? Report it; do not "fix" either side without asking.
- Every change to `architecture.md` or `methodology.md`: bump its version line, add one line to its
  **Change log** (date, what, why), and move settled questions to "Settled" with the date.
- Update without asking, in the same branch, when affected: `docs/data_contract.md` (schemas —
  the change itself still needs confirmation), `docs/glossary.md` (new terms), `docs/notes.md`
  (add or close points), `.env.example` (every new environment variable with a comment),
  `config/config.yaml` comments, the folder's `AGENTS.md`, `CHANGELOG.md`.
- New ideas or deferred work go to `docs/notes.md`, not into code comments or TODOs.

### README (update automatically)

`README.md` is the entry point for supervisors and new readers. **Update it yourself, without
asking, in the same branch** whenever your change affects anything it describes: status,
features, commands, setup requirements, repository layout (incl. the Status column), data sources,
documentation links, team or milestones. Before every commit, check whether the README is still true.

- Fixed section order: title + summary · status · what it does · architecture in one picture ·
  repository layout · getting started · data sources · documentation · team · milestones.
- Short and factual; link to `docs/` instead of copying details. Mark commands that do not work
  yet as *planned*; never document a command you have not run.
- Every link and path in it must exist; remove sections that no longer apply.

## Writing efficient code

The production server has 2 vCPU and 4 GB RAM shared by PostGIS, Valhalla, the API and the
pipeline. Write for that.

- **Vectorise.** pandas/GeoPandas operations, spatial joins and spatial indexes (`sjoin`,
  `sindex`, `STRtree`); no Python loops over cells or facilities.
- **Stream large inputs.** Read big files (GTFS `stop_times.txt`, PBF, Zensus CSV) with DuckDB,
  Polars or pyarrow and filter while reading; never load a whole large file into pandas.
- **Batch Valhalla calls** as in architecture §6.5; async client with bounded concurrency.
- **Compute once, reuse.** Cache intermediate results per run (GeoParquet); do not recompute what
  an earlier stage produced.
- **Measure pipeline stages:** log runtime and peak memory; mention them in the PR when a stage changes.
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

## Tests

- Before every commit that touches code: lint and the tests of the touched package pass.
- **Unit tests** use small fixtures and no network: mock HTTP calls to Valhalla (record a real
  response once and replay it), never download data.
- **Fixtures** live next to the tests (`<package>/tests/fixtures/`, shared ones in
  `tests/fixtures/`), each under 1 MB; real data never goes into the repo.
- **Integration tests** (`tests/integration/`) run the pipeline against a local Valhalla container
  on the test clip; they are not required for every commit.
- A schema change gets a data-contract test. Report the commands and results in the PR.

## Notebooks and experiments

Exploration (notebooks, quick scripts, prototypes) happens on `exp/…` branches and is not merged
into `dev`. Results that matter become pipeline code with tests, or a finding in `docs/notes.md`.
Never import notebook code into the pipeline.

## Committing

- **One logical change per commit** that leaves the code working: the code, its tests, and the
  docs/config/lockfile changes it requires. `pyproject.toml` and `uv.lock` always together.
  Formatting-only or refactoring changes in separate commits from behaviour changes.
- **Never commit:** anything in `data/` or other datasets, files > 10 MB, `.env`, keys, tokens,
  passwords, `.venv/`, caches, notebook outputs, build output (`web/dist/`). Missing
  `.gitignore` entry → add it in the same branch. Secret committed by accident → tell your human
  immediately; the key must be rotated.
- **Before committing:** `git status` and `git diff --staged`; stage files explicitly (no blind
  `git add .`).
- **Message:** Conventional Commits in English, `<type>(<scope>): <imperative summary>`, body with
  what and why, `Closes #N` if applicable, and a co-author trailer for the assistant used, e.g.
  `Co-authored-by: Claude <noreply@anthropic.com>`. Types and scopes: see `CONTRIBUTING.md` §3.
  Not okay: `update`, `wip`, `fix stuff`, `changes`.

## Branches, pull requests, versions

- Base branch **`dev`**; `main` only receives milestone releases via PR from `dev`.
- Branch per topic from fresh `dev` (`git fetch --all --prune` first), named
  `<type>/<name>-<topic>`: type `feature`, `fix`, `docs`, `refactor`, `data` or `exp`; `<name>` =
  your human's lowercase team name (`rico`, `socke`, `juju`); issue number after the name if there
  is one (`feature/rico-12-matrix-batching`). One branch = one topic, short-lived.
- **Never commit to, push to or open a PR from a branch that carries another person's name**, even
  if it already contains the work you need; create your own branch from `dev` instead.
- Behind `dev`: `git rebase origin/dev` on your **own** branch, re-run checks,
  `git push --force-with-lease`.
- **You may push your own topic branch and open a draft PR into `dev` without asking.** Title in
  Conventional Commit format; body uses the template in `CONTRIBUTING.md` §4 and states on whose
  behalf you worked. Keep PRs reviewable in ~15 minutes.
- **Version history:** add a line under `## [Unreleased]` in `CHANGELOG.md` for every user-visible
  or architectural change. Releases and tags: `CONTRIBUTING.md` §7, only on explicit request.
- Merge conflicts: never accept one side blindly; explain both versions and propose a resolution;
  ask before resolving conflicts in another person's code.

## Boundaries

**Always**
- Work on a topic branch; keep the change to the task you were given.
- Keep docs in sync (see above); update `README.md` and `CHANGELOG.md` automatically.
- Ask when a requirement is unclear or the task touches another person's folder (`.github/CODEOWNERS`).

**Ask first (wait for explicit confirmation)**
- Any change to `docs/architecture.md` or `docs/methodology.md`, or implementing something that
  deviates from them.
- Adding, removing or upgrading dependencies.
- Changing or removing **existing** values in `config/`; changes to `compose*.yaml`, `infra/`, CI
  workflows, the data contract or the repository structure. (Adding a new config key with a
  comment is fine.)
- Changes in more than one **code** folder (`pipeline`, `api`, `web`, `infra`, `config`), or
  anything outside the task. Docs, `README.md` and `CHANGELOG.md` do not count.
- A phase plan in `docs/implementation_plan.md` that your human has confirmed counts as this
  confirmation for the folders, files, `compose*.yaml`, `infra/`, CI workflows, data-contract
  tables and structure it **names explicitly**. Dependencies, existing config values, deviations
  from the plan and any change to `architecture.md`/`methodology.md` still need their own "yes".
- Marking a PR ready for review, commenting on issues/PRs of others, deleting branches or files,
  tagging, releasing.

**Never**
- Commit or push directly to `main` or `dev`; `git push --force` on `main`/`dev`; `git reset --hard`
  on shared branches; rewrite or delete someone else's branch; merge PRs unless explicitly told to.
- Commit data, secrets or large files.
- Use `pip install` or hand-made virtual environments (use uv).
- Disable tests, lint rules or validation checks to make something pass.
- Expose Valhalla or PostGIS ports publicly in production configs.

## Working in parallel

Each person (and each agent session) works on its own branch; parallel sessions use separate git
worktrees. Before a PR leaves draft, review the diff in a fresh session or by a teammate; the
author does not approve their own PR.

## Keeping this file useful

Keep it short. When an agent repeats the same mistake, add one precise rule here (ask first);
remove rules that no longer apply. Details belong in `docs/` or `CONTRIBUTING.md`.
