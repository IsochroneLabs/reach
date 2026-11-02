# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Copilot, Cursor, …) working in this repository.
Humans: see `README.md`. Folder-specific rules are in `pipeline/AGENTS.md`, `api/AGENTS.md` and
`web/AGENTS.md`; the nearest `AGENTS.md` to the file you edit takes precedence.

**Project:** `reach` measures 15-minute accessibility (walking, cycling, wheelchair) for the urban
area of Tübingen, finds underserved areas and recommends sites for new facilities. Course project
DS500, University of Tübingen. Read [`docs/architecture.md`](docs/architecture.md) before any
change to structure, data flow or dependencies.

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
| `docs/` | `architecture.md` (system), `data_contract.md` (tables between pipeline and API), `notes.md` (open points) |
| `data/` | Local data, **git-ignored**, never committed |

## Architecture rules (do not break)

1. **Valhalla is the only routing engine.** No OSMnx/NetworkX/pandana/r5py routing.
2. **Count with the matrix (`sources_to_targets`), never with isochrone polygons.** Isochrones are
   display only. Follow the efficiency rules in `docs/architecture.md` §6.5 (one matrix for all
   categories, spatial blocks, exact straight-line prefilter, no per-category requests).
3. **CRS:** convert to EPSG:25832 on ingest; keep Zensus cell IDs (EPSG:3035) as keys; transform
   to EPSG:4326 only at the API (`ST_Transform`). Never compute distances in degrees.
4. **No hard-coded values:** thresholds, speeds, tags, URLs and paths come from `config/` or `.env`.
5. **Store raw counts and times;** classes and deficits are derived at read time.
6. **Only the `publish` stage writes to PostGIS.** The API reads only from the `current` schema.
7. **Pipeline stages are idempotent** and write a manifest; each stage checks the previous manifest.
8. **No public data APIs at runtime** (Overpass, Nominatim). OSM data comes from the clipped Geofabrik extract.

## Code style

- Python: ruff (line length 100), type hints on public functions, short docstrings, `logging`
  instead of `print`, small functions, no notebooks in the pipeline.
- Prefer simple, explicit code over abstractions; no new framework without asking.
- Errors: fail loudly with a clear message; retries only for network calls.

```python
# good: config-driven, metric CRS, explicit
radius_m = cfg.profiles[profile].speed_kmh * 1000 / 60 * cfg.time_budget_min
candidates = facilities[facilities.distance(cell.geometry) <= radius_m]

# bad: magic number, degrees, hidden assumption
candidates = facilities[facilities.distance(cell.geometry) <= 0.008]
```

## Tests and checks

Before every commit that touches code: lint and the tests of the touched package must pass. New
pipeline logic gets a unit test with a small fixture (no network, no real downloads). Report the
command and result in the PR. Never claim tests pass without running them.

## Git workflow

- Base branch: **`dev`**. `main` only receives milestone releases via PR.
- Branch per topic from fresh `dev`: `feature/…`, `fix/…`, `docs/…`, `refactor/…`, `data/…`,
  `exp/…`; prefix the issue number if there is one (`feature/12-matrix-batching`).
- Conventional Commits in English: `type(scope): imperative summary`, types `feat fix docs refactor
  test data chore style ci`. Small, self-contained commits; no "update", "wip", "fix stuff".
- Before committing: `git status` and `git diff --staged`; stage files explicitly (no blind `git add .`).
- Every commit made by an agent ends with a trailer for the assistant, e.g.
  `Co-authored-by: Claude <noreply@anthropic.com>`; the PR states on whose behalf the agent worked.
- Pull requests go to `dev` with: What / Why / How tested / Open points / linked issue.
- Behind `dev`: `git rebase origin/dev` on your own branch, then `git push --force-with-lease`.

## Boundaries

**Always**
- Work on a topic branch; keep the change to the task you were given.
- Update `README.md`, `docs/architecture.md` or `docs/data_contract.md` in the same PR when you
  change commands, structure, data sources or table schemas.
- Ask when a requirement is unclear or the task touches another person's folder (see `.github/CODEOWNERS`).

**Ask first**
- Adding, removing or upgrading dependencies; changing `uv.lock` other than via `uv add`.
- Changing `config/`, `compose*.yaml`, `infra/`, CI workflows or the data contract.
- Changes in more than one top-level folder, or anything outside the task.
- Pushing, opening or updating a PR, deleting branches or files.

**Never**
- Commit or push directly to `main` or `dev`; `git push --force` on `main`/`dev`; `git reset --hard`
  on shared branches; merge PRs.
- Commit data, `.env`, keys, tokens, passwords, files > 10 MB, `.venv/`, notebook outputs.
- Use `pip install` or hand-made virtual environments (use uv).
- Disable tests, lint rules or validation checks to make something pass.
- Expose Valhalla or PostGIS ports publicly in production configs.

## Working in parallel

Each person (and each agent session) works on its own branch; for parallel sessions use separate
git worktrees. Before opening a PR, review the diff in a fresh session or by a teammate; the
author does not approve their own PR.
