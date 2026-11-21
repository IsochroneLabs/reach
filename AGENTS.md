# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Copilot, Cursor, …) working in this repository.
They apply to every agent session, on behalf of any team member. Humans: see `README.md` and
`CONTRIBUTING.md` (*planned, S0.4*). Folder rules follow in `pipeline/AGENTS.md`, `api/AGENTS.md`
and `web/AGENTS.md`; the nearest `AGENTS.md` to the file you edit takes precedence.

**Project:** reach helps students who are new to Tübingen decide where to live, by showing how
long their own everyday trips take from each part of the city on foot, by bike (with hills) and
by bus, and explaining the differences in plain language. Course project DS500, University of
Tübingen; complexity, UX, automation and error handling, consistency, validation, documentation
and a hosted app are graded. Submission: 22 Jan 2027.

**Status:** rebuild on an empty `dev` (21 Nov 2026). The previous project (a planner tool) is frozen
in `archive/2026-11-21-planner`. Progress, the next step and open decisions live in
[`docs/implementation_plan.md`](docs/implementation_plan.md). If a file, folder or command named
here does not exist yet, say so; do not invent a substitute.

A new session continues with: *"Continue with the next open step in docs/implementation_plan.md."*

## Terms and roles

| Term | Meaning |
|---|---|
| **you** | The coding agent reading this file (any tool, any session). |
| **your human** | The team member who started your session and gives you the task. Confirmations come from them. |
| **we / the team** | **Rico** (GitHub `RicoS03`), **Socke** (`konstantinholl`), **Juju** (`nicholas-tuebi`). |
| **ask first** | Stop, describe what you want to do and why, and wait for your human's explicit "yes". |

Project vocabulary (student profile, persona, destination type, mode, trip window, fit, cell,
run, stage, manifest, `current`, …) is defined in [`docs/glossary.md`](docs/glossary.md). Use
these terms in code, docs and messages; do not use the old project's terms (15-minute city,
class, deficit, recommender, …).

## Sources of truth

| Document | Binding for |
|---|---|
| `docs/product.md` | User, their questions, use cases U1–U3, non-goals, cut order |
| `docs/architecture.md` | System: components, data flow, routing, deployment, decisions (O-numbers, T1, D1–D5) |
| `docs/methodology.md` | What is computed: destinations, modes, trip windows, travel times, fit, validation (V-numbers) |
| `docs/data_contract.md` | Table, file and API schemas between pipeline and API |
| `docs/deployment.md` | Environments, workflows, secrets, runbook |
| `docs/implementation_plan.md` | Steps, status, dates, assumptions |
| `AGENTS.md`, `CONTRIBUTING.md` | How to work in this repo |

`docs/notes.md` (findings and open points) and `docs/osm_tagging.md` are informative. If documents
disagree, `architecture.md` and `methodology.md` win; report the conflict instead of picking a side.

## Commands

Run from the repository root. Commands marked *planned* do not work yet; the step that adds them
is named.

| Task | Command |
|---|---|
| Install / update Python env | `uv sync` (*planned, S0.4*) |
| Lint + format check | `uv run ruff check . && uv run ruff format --check .` (*planned, S0.4*) |
| Tests | `uv run pytest` · DB contract: `REACH_TEST_DATABASE_URL=<superuser URL> uv run pytest -m db` (*planned, S0.4*) |
| Local stack | `make up` (PostGIS, API, Valhalla once tiles exist) (*planned, S0.4*) |
| Full refresh | `make refresh` · test clip: `make refresh REACH_CONFIG=config/test_clip.yaml` (*planned, S0.4; transit from S1.7*) |
| One pipeline stage | `make pipeline STAGE=<stage>` (*planned, S0.4*) |
| DB roles + migrations | `make migrate` (*planned, S0.4*) |
| Frontend | `cd web && npm ci && npm run dev` · checks: `npm run lint && npm run build` (*planned, S0.5*) |
| Add Python dependency | `uv add --package pipeline <pkg>` / `--package api` / `--dev` (ask first) |

## Stack

Python 3.12 via uv (one workspace: `pipeline`, `api`; one `uv.lock`) · FastAPI · PostgreSQL +
PostGIS · Valhalla (official image, tag pinned) for walk and bike · transit engine **pending (T1)** ·
React + TypeScript + Vite + MapLibre GL JS · Docker Compose · GitHub Actions · GHCR · Cloudflare
for the frontend. Exact versions live in `pyproject.toml`, `uv.lock`, `web/package.json` and
`compose*.yaml`; do not change them without asking.

## Where things are

| Path | Content |
|---|---|
| `pipeline/` | Data pipeline: acquire → validate → tiles → travel times → validate results → publish → cleanup (*planned, S0.4/S1*) |
| `api/` | FastAPI: health, reference data, address search, fit, cell detail, live route (*planned, S0.4/S1.10*) |
| `web/` | Student web app, static build deployed to Cloudflare (*planned, S0.5/Phase 2*) |
| `config/config.yaml` | Study area, routing profiles, trip windows, destination types + OSM tags, validation limits: **all tunable values** |
| `config/campus.yaml` | Programmes → campus sites |
| `config/personas.yaml` | Personas for demos and tests |
| `infra/` | Dockerfiles, DB roles/migrations, server files (*planned, S0.4/S1.5*) |
| `.github/workflows/` | `ci.yml`, `deploy.yml` (*planned, S0.5*) |
| `docs/` | Product, architecture, methodology, data contract, deployment, glossary, notes, plan |
| `CHANGELOG.md` | Change history (`Unreleased`, then one section per release) |
| `data/` | Local data, **git-ignored**, never committed |

## How to work on a task

1. **Understand.** Read the task, the relevant sources of truth, `docs/notes.md` and the code you
   will touch. Search for functions that already do what you need.
2. **See the whole project.** Name downstream effects: data contract, pipeline stages, API,
   frontend, config, tests, docs, deployment.
3. **Plan and confirm.** For anything beyond a small local fix, state a short plan and wait.
4. **Implement in small steps.** Run lint and tests after each step; keep the code working.
5. **Verify with evidence.** Run the checks (pipeline work: on the test clip). Report commands and
   results; never claim something works without running it.
6. **Update docs and history** in the same branch (see below), including the status block of
   `docs/implementation_plan.md` at the end of every step.
7. **Report.** Branch, commits, PR link, checks, open points, doc changes.

Bundle questions (at most 3–4), each with a recommended option. Do exactly the task; note
improvements as suggestions or as an N-entry in `docs/notes.md`. Reply in the language of the
prompt; code, comments, commit messages, PRs and docs are English. "Just do it" does not override
the Never list or the Ask-first list.

## Architecture rules (do not break)

1. **Routing engines:** Valhalla for walk and bike (with elevation, `costmatrix` for every matrix).
   **Transit engine: decision pending (T1)**; until it is recorded in `docs/architecture.md`, do not
   add one.
2. **Times from network routing, never from isochrone polygons.** Isochrones are display only.
3. **CRS:** EPSG:25832 for storage and computation; Zensus cell ids (EPSG:3035) as keys; EPSG:4326
   only at the API (`ST_Transform`). Never compute distances in degrees.
4. **No hard-coded values:** speeds, tags, trip windows, limits, URLs and paths come from
   `config/` or `.env`.
5. **Store raw travel times;** the fit, rankings and reasons are derived at read time by the API.
6. **Only `publish` writes results to PostGIS;** `cleanup` only drops old run schemas. The API
   reads only `current`.
7. **Stages are idempotent** and write a manifest; each stage checks the previous one.
8. **No public data APIs at runtime** (Overpass, Nominatim, journey planners). OSM data comes
   from the clipped Geofabrik extract; addresses are searched in PostGIS.
9. **Privacy:** nothing personal is stored on the server; the student profile lives in the
   browser/URL; POST bodies are not logged; caches key only on the weight vector. No tracking or
   analytics.
10. **No public ports** for PostGIS, Valhalla or the transit engine in any production config.

## Docs stay in sync with the code

- If the implementation needs to differ from `architecture.md` or `methodology.md`: **stop,
  explain the deviation and the proposed doc change, and ask first.** After the yes, change code
  and document in the same branch. Never diverge silently.
- Every change to `architecture.md` or `methodology.md`: bump the version line, add a change-log
  line (date, what, why), move settled questions to "Settled".
- Update without asking, in the same branch, when affected: `docs/data_contract.md` (the schema
  change itself still needs a yes), `docs/glossary.md`, `docs/notes.md`, `.env.example` (every new
  variable with a comment), config comments, folder `AGENTS.md`, `CHANGELOG.md`, `README.md`.
- `README.md` keeps its section order (title + summary · status · what it does · architecture ·
  layout · getting started · data sources · documentation · team · milestones); every link and
  path must exist or be marked *planned*; never document a command you have not run.
- New ideas and deferred work go to `docs/notes.md`, not into TODO comments.

## Writing efficient code

The server is planned with 8 GB RAM (D1) shared by PostGIS, Valhalla, the transit engine, the API
and the pipeline; the refresh runs its heavy steps one after the other (A4).

- Vectorise (pandas/GeoPandas, spatial indexes); no Python loops over cells or destinations.
- Stream large inputs (PBF, GTFS `stop_times.txt`, Zensus CSV) with DuckDB, pyarrow or osmium.
- Batch routing calls (cell blocks, straight-line prefilter, bounded concurrency).
- Log runtime and peak memory of every stage; mention them in the PR when a stage changes.
- Keep it simple: small pure functions, I/O at the edges, no abstraction "for later", no new
  framework or service without asking. Delete dead code.

## Code style and tests

- Python: ruff (line length 100), type hints on public functions, short docstrings, `logging`
  instead of `print`. Fail loudly with a clear message and a non-zero exit code; retries only for
  network calls.
- Unit tests use small fixtures (< 1 MB) and no network: record a real engine response once and
  replay it. Integration tests run on the test clip. A schema change gets a data-contract test.
- External reference times for validation are stored as fixtures; tests and the pipeline never
  query journey planners.
- Exploration happens on `exp/…` branches and is not merged; results become code with tests or a
  note.

## Branches, commits, pull requests, releases

- Base branch **`dev`** (protected: PR, no force push). `main` (protected: PR with 2 approvals)
  receives only release PRs from `dev`; its push deploys production.
- Branch per topic from fresh `dev` (`git fetch --all --prune` first): `<type>/<name>-<topic>`,
  type `feature`, `fix`, `docs`, `refactor`, `chore`, `data` or `exp`; `<name>` = your human's
  lowercase team name (`rico`, `socke`, `juju`).
- Never commit to, push to or open a PR from a branch that carries another person's name.
- **Conventional Commits:** `<type>(<scope>): <imperative summary>`, body with what and why,
  co-author trailer for the assistant. Not okay: `update`, `wip`, `fix stuff`, `changes`. One
  logical change per commit; `pyproject.toml` and `uv.lock` together; stage files explicitly
  (`git status`, `git diff --staged`; no blind `git add .`). A port from the archive names its
  source path in the commit message.
- Push your own topic branch and open a **draft** PR into `dev`; title in Conventional Commit
  format, body from the PR template, stating on whose behalf you worked.
- Add a line under `## [Unreleased]` in `CHANGELOG.md` for every user-visible or architectural
  change. Releases (version bump, CHANGELOG section, PR `dev` → `main`), tags and GitHub Releases
  only on explicit instruction.

## Delivery rules

- Nobody deploys by hand. Production changes only through a merged release PR into `main`, which
  runs `deploy.yml`: CI on the merge commit → images to GHCR by SHA → frontend to Cloudflare →
  backend on the server → smoke test → rollback and team notification on failure.
- `deploy.yml` runs only on push to `main` and on `workflow_dispatch` (redeploy or rollback of a
  SHA); deploys never overlap (`concurrency`); third-party actions are pinned to a commit SHA;
  every workflow declares least-privilege `permissions:`.
- All deploy secrets live in the GitHub environment `production` or in `.env` on the server.
  **Secrets are created by your human, never by you; never read or print them.** Every secret is
  documented in `docs/deployment.md` and `.env.example`.
- Data never passes through GitHub or Cloudflare; the data refresh runs on the server.

## Boundaries

**Ask first**
- Any change to `docs/architecture.md` or `docs/methodology.md`, or code that deviates from them;
  the fit formula; T1 and D1–D5.
- Adding, removing or upgrading dependencies, services or paid products.
- Changing or removing existing values in `config/`; changes to `compose*.yaml`, `infra/`,
  workflows, the data contract or the repository structure (adding a config key with a comment
  is fine).
- A confirmed step plan in `docs/implementation_plan.md` counts as the confirmation for the
  folders, files, `compose*.yaml`, `infra/`, workflows, tables and structure it **names
  explicitly**; dependencies, existing config values, deviations and `architecture.md` /
  `methodology.md` changes still need their own yes.
- Marking a PR ready, commenting on others' issues or PRs, deleting branches or files, tagging,
  releasing.

**Never**
- Commit or push directly to `main` or `dev`; `git push --force` on `main`/`dev`; `git reset --hard`
  on shared branches; rewrite or delete someone else's branch; merge PRs unless explicitly told to.
- Push to or change `archive/2026-11-21-planner`.
- Commit data, secrets, `.env`, keys, tokens, passwords, files > 10 MB, `.venv/`, caches or build
  output.
- Create, read or print secrets; create or book servers or paid services.
- Use `pip install` or hand-made virtual environments (use uv).
- Disable tests, lint rules or validation checks to make something pass.
- Expose PostGIS, Valhalla or the transit engine publicly.

## Keeping this file useful

Keep it short. When an agent repeats a mistake, add one precise rule here (ask first); remove
rules that no longer apply. Details belong in `docs/` or `CONTRIBUTING.md`.
