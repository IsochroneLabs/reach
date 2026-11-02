# reach — 15-Minute City Tübingen

`reach` measures how well residents of Tübingen can reach everyday services — supermarkets,
pharmacies, doctors, childcare, schools, parks, public transport — within 15 minutes on foot,
by bike or by wheelchair. It shows underserved areas on an interactive map and recommends
where new facilities would help the most people.

Course project for **DS500 Data Science Project** (M.Sc. Data Science in Business and Economics,
University of Tübingen, winter term 2026/27), Topic 9 "The 15-Minute City".

> **Status: scaffold (phase P1).** Architecture and team rules are defined; the local stack
> (PostGIS, API and web placeholders), the configuration, the pipeline stage pattern and CI exist.
> Data stages, routing and the map are being built. Commands below marked *planned* become
> available step by step; progress: [`docs/implementation_plan.md`](docs/implementation_plan.md).

## What it does

- **Accessibility map** — 15-minute reachability per facility category and travel profile on the
  official Zensus 2022 100 m grid, aggregated to city districts.
- **Public transport supply** — scheduled weekday departures at stops within a 10-minute walk.
- **Pin-drop inspector** — click anywhere in the city: what is reachable, how long it takes, and
  which category is the weakest.
- **Recommendations** — candidate zones for new facilities, ranked by the number of residents who
  would gain 15-minute access.
- **Automated and validated** — a weekly pipeline downloads open data, validates it and publishes
  new results only if all checks pass.

## Architecture in one picture

```mermaid
flowchart LR
    SRC["Open data<br/>OSM · GTFS · Zensus 2022"] --> PIPE["Pipeline<br/>(weekly)"]
    PIPE --> VAL["Valhalla<br/>routing"]
    PIPE --> DB[("PostGIS")]
    USER["Browser<br/>React + MapLibre"] --> CADDY["Caddy (HTTPS)"] --> API["FastAPI"]
    API --> DB
    API --> VAL
```

Valhalla is the single routing engine for counting, isochrones and live queries. Everything runs
with Docker Compose on one small server. Details: [`docs/architecture.md`](docs/architecture.md).

## Repository layout

| Path | Content | Status |
|---|---|---|
| `docs/` | Architecture, methodology, features, glossary, notes, team decisions | ✅ |
| `AGENTS.md`, `CLAUDE.md` | Rules for coding agents | ✅ |
| `CONTRIBUTING.md` | Branches, commits, pull requests, releases | ✅ |
| `CHANGELOG.md` | Change history | ✅ |
| `pipeline/` | Data pipeline (Python, uv workspace member): stage pattern, config loader | scaffold |
| `api/` | FastAPI backend (Python, uv workspace member): health endpoint | placeholder |
| `web/` | React + MapLibre frontend | planned |
| `config/` | Study area, profiles, categories, thresholds (`config.yaml`); Valhalla limits planned | partial |
| `infra/` | Caddyfile and placeholder page; Dockerfiles, DB roles, scheduler planned | partial |
| `Makefile`, `compose.yaml`, `.env.example` | Local stack and command wrappers | ✅ |
| `.github/` | CI (lint + tests), PR template, CODEOWNERS | ✅ |

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/), Docker (Desktop) with Compose, Node.js for the
frontend. Without uv: `pip install -r requirements.txt` (exported from `uv.lock`).

```bash
git clone https://github.com/IsochroneLabs/reach.git
cd reach
git switch dev

uv sync                 # Python 3.12 environment (.venv) for pipeline and api
make test               # tests (uv run pytest)
make lint               # ruff check + format check

cp .env.example .env    # then replace every "change-me"
make up                 # start PostGIS, API and Caddy; http://127.0.0.1:8080
make pipeline STAGE=hello   # no-op stage, writes data/runs/<run_id>/hello/manifest.json
make down               # stop the stack
make pipeline           # planned: download data, compute and publish results
```

Valhalla joins `make up` once routing tiles exist (phase P3). If port 5432, 8002 or 8080 is taken
on your machine, change `DB_PORT`, `VALHALLA_PORT` or `WEB_PORT` in `.env`.

## Data sources

| Source | Used for | Licence |
|---|---|---|
| [Geofabrik](https://download.geofabrik.de/europe/germany/baden-wuerttemberg/tuebingen-regbez.html) OpenStreetMap extract | Street network, facilities, boundaries, land use | ODbL 1.0 |
| [NVBW](https://www.nvbw.de/open-data/fahrplandaten) GTFS (naldo) | Public transport stops and departures | dl-de/by-2-0, ODbL |
| [Destatis Zensus 2022](https://www.zensus2022.de/) 100 m grid | Residents per cell | dl-de/by-2-0 |
| Elevation tiles via Valhalla | Slopes (per-profile setting) | per source |

© OpenStreetMap contributors · © Statistisches Bundesamt (Destatis) · NVBW.

## Documentation

| Document | Content |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | **Binding** system description, decisions and change log |
| [`docs/methodology.md`](docs/methodology.md) | **Binding** categories, thresholds, scoring, recommender, validation experiments |
| [`docs/data_contract.md`](docs/data_contract.md) | Table and file schemas between pipeline and API (draft) |
| [`docs/features.md`](docs/features.md) | Features, priorities and roadmap |
| [`docs/glossary.md`](docs/glossary.md) | Project vocabulary |
| [`docs/notes.md`](docs/notes.md) | Open points and future work |
| [`docs/implementation_plan.md`](docs/implementation_plan.md) | Phase plan, status and decisions of the implementation (handoff between sessions) |
| [`docs/prompts/implementation.md`](docs/prompts/implementation.md) | Prompts for building the system with a coding agent, phase by phase |
| [`docs/project_management_decisions.md`](docs/project_management_decisions.md) | Team and course organisation |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How we work together |
| [`AGENTS.md`](AGENTS.md) | Rules for coding agents |

## Team

| Name | GitHub |
|---|---|
| Rico | [RicoS03](https://github.com/RicoS03) |
| Socke | [konstantinholl](https://github.com/konstantinholl) |
| Juju | [nicholas-tuebi](https://github.com/nicholas-tuebi) |

## Milestones

| Date | Milestone |
|---|---|
| 25 Nov 2026 | Interim presentation (`v0.1.0`) |
| 22 Jan 2027, 23:59 | Submission: code, documentation, video (`v1.0.0`) |
| 29 Jan 2027 | Final presentation |
