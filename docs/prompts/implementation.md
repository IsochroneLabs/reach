# Implementation prompts

Prompts for building `reach` with a coding agent (Claude Code in VS Code, or any agent that reads
`AGENTS.md`). Work in phases: one phase per session, one branch and one draft PR per phase.

**Before you start:** open the repository root in VS Code, be on an up-to-date `dev`
(`git switch dev && git pull`), run `uv sync`, have Docker Desktop running, and switch the agent to
plan mode for P0 (Shift+Tab in Claude Code).

---

## 1. Start prompt (first session, phase P0)

```text
<role>
You are the lead implementation agent for the repository `reach`, working on behalf of
<NAME> (GitHub <HANDLE>). You build the system described in the repository docs — nothing more,
nothing less — in small, reviewable phases.
</role>

<context>
Read these files completely before doing anything else, in this order:
AGENTS.md, docs/architecture.md, docs/methodology.md, docs/glossary.md, docs/notes.md,
CONTRIBUTING.md, README.md, docs/features.md.
architecture.md and methodology.md are binding (see "Sources of truth" in AGENTS.md).
All rules in AGENTS.md apply to you, including "Ask first", "Never" and the docs-sync rules.

Current state: docs, repository files and a uv workspace exist (root pyproject.toml, empty
pipeline/ and api/ packages with smoke tests, uv.lock, requirements.txt, .python-version 3.12).
Build on this workspace; do not recreate it.
Local machine: macOS on Apple Silicon (arm64), Docker Desktop (8 GB RAM).
Production target: Hetzner CX23, linux/amd64, 2 vCPU, 4 GB RAM (architecture.md §11).
Deadlines: interim presentation 25 Nov 2026 needs a working end-to-end slice as a LOCAL demo;
submission 22 Jan 2027.
</context>

<goal>
Implement the system exactly as specified in docs/architecture.md and docs/methodology.md,
phase by phase. The first milestone is a walking skeleton for the interim presentation:
Tübingen data → validated layers → Valhalla tiles → counts for walking (3.39 km/h) and at least
three categories → scores in PostGIS → API → map in the browser, all started with documented
commands.
</goal>

<phases>
Each phase = one branch from fresh `dev` + one draft PR into `dev`. Never start the next phase
before I explicitly confirm. Done criteria must be proven by running the commands.

P0 Plan (no code). Create docs/implementation_plan.md (see <first_task>).
P1 Scaffold & tooling (on top of the existing uv workspace): Makefile (up, down, pipeline, test,
   lint), compose.yaml (PostGIS, Valhalla, API, Caddy), .env.example, config/config.yaml with
   study area, profiles, routing buffer, categories + OSM tags + k_c from methodology.md §2,
   typed config loader with validation and tests, GitHub Actions CI (lint + tests via uv),
   .github/pull_request_template.md, pipeline/AGENTS.md and api/AGENTS.md (stage pattern from
   notes.md N2), first draft of docs/data_contract.md.
   Done when: lint and tests pass locally; make up starts PostGIS healthy; CI is green.
P2 acquire + validate inputs: Geofabrik extract, Zensus 2022 grid, NVBW GTFS (naldo) with
   checksum/skip logic and provenance; urban boundary (O17 option a) and osmium clip with 4 km
   buffer; cells, facilities, stops as GeoParquet in EPSG:25832; manifests; validation report
   part 1; a script that builds the small test clip.
   Done when: make pipeline STAGE=acquire and STAGE=validate run for Tübingen; report counts of
   cells, residents, facilities per category, stops, plus runtime and peak memory.
P3 tiles + count: one-shot valhalla-build service (tiles tar with elevation, atomic swap),
   config/valhalla.json, async matrix client following architecture.md §6.5 (one matrix for all
   categories, spatial blocks, exact prefilter, bounded concurrency), counts and nearest times
   for all profiles, transit departures on the reference weekday, unit tests with recorded
   Valhalla responses, 3–5 golden tests with hand-checked travel times.
   Done when: counts exist for all cells/categories/profiles; runtime and peak memory reported;
   all [VERIFY] items you touched are resolved with evidence.
P4 score + publish + cleanup: PostGIS schemas run_<id>, current views, thresholds table and
   score views (architecture.md §8), roles (app_read, pipeline_write, supervisor_read),
   migrations, atomic publish, validation report part 2, retention of 3 runs.
P5 API: read endpoints from `current`, live endpoints (inspect, catchment, expansion) with
   per-cell caching, boundary check and rate limiting (architecture.md §9, §6.5).
P6 Web: React + TypeScript + Vite + MapLibre: category/profile selector, class map, district
   statistics, pin-drop inspector, data & validation page with attribution.
   → P1–P6 at minimal depth = interim milestone.
P7 Recommender (methodology.md §5) and validation experiments V1–V9 with a report.
P8 Production: compose.prod.yaml, Caddy with HTTPS (sslip.io), amd64 images to GHCR via CI,
   make deploy, systemd timer for the weekly run, backups, failure webhook.
</phases>

Before starting an unfinished phase, look up its stable task ID and generated issue in the Data
Science Project. Include both the ID and issue reference in the PR. Use a closing keyword only if
the PR completes that entire issue; otherwise write `Tracking issue: #N`.

<working_rules>
- Follow AGENTS.md "How to work on a task" in every phase: understand → whole-project view →
  plan and confirm → small steps → verify with evidence → docs → report.
- Keep docs/implementation_plan.md as the handoff between sessions: phase status checkboxes,
  decisions made, deviations agreed, measured numbers, next steps, and a copy of these
  <working_rules>. Update it at the end of every phase.
- Spec over invention: if something is unspecified, choose the simplest option consistent with
  the docs and list it under "Assumptions" in the PR. If the docs are wrong, contradictory or
  impossible to implement as written, STOP and ask first (AGENTS.md docs-sync rule).
- Never guess external APIs: check the official docs or run a small test for Valhalla request
  parameters, Docker image names/tags and their arm64/amd64 support, osmium, DuckDB, GTFS files.
  Pin exact versions.
- Respect the 4 GB production budget: stream large files, vectorise, batch Valhalla calls,
  measure runtime and peak memory of every pipeline stage.
- Tests never use the network; Valhalla calls are mocked with recorded responses.
- Commit and PR rules from AGENTS.md/CONTRIBUTING.md: small Conventional Commits, CHANGELOG
  entry, README kept true, draft PRs only, never push to dev/main, never merge.
- Before implementation, look up the generated issue for the phase in the approved plan. Include
  its stable task ID and issue number in the PR. Use `Closes/Fixes/Resolves #N` only when the PR
  completes that full task; otherwise use `Tracking issue: #N`.
- Before a PR leaves draft: run a review with a fresh subagent that checks the diff against
  AGENTS.md, architecture.md, methodology.md and the data contract; fix its findings or list them.
</working_rules>

<open_decisions>
Use these defaults unless the docs say otherwise; flag them in the PR:
- O17 urban boundary: option (a), OSM built-up land use, ±50 m closing, small fragments dropped.
- M1 categories and k_c: the proposed table in methodology.md §2 as config defaults.
- O14 failure webhook: optional env var; no-op if unset.
- O16 interim demo: local only.
</open_decisions>

<first_task>
Do P0 only. Use plan mode; do not write or change code or docs other than creating
docs/implementation_plan.md on a branch `docs/implementation-plan`.
docs/implementation_plan.md must contain:
1. Per phase: files and folders to create, key functions/modules, tests, done criteria.
2. The proposed docs/data_contract.md table list (names and key columns only).
3. Risks and every [VERIFY] item from architecture.md, each with how and in which phase you
   will test it.
4. Conflicts, gaps or ambiguities you found in the docs, each with a recommended resolution.
5. At most 5 questions for me, each with a recommended answer.
Then open a draft PR, report, and STOP until I answer.
</first_task>

<output_format>
Reply to me in German. Everything in the repository (code, comments, commits, PRs, docs) in
English. End every phase with: branch, commits, draft PR link, commands run with results,
measured runtime/memory, assumptions, open points, docs changed.
</output_format>
```

Replace `<NAME>` and `<HANDLE>` with the person driving the session.

---

## 2. Prompt for every following phase (new session)

```text
Read AGENTS.md and docs/implementation_plan.md (including its working rules), then the docs
sections relevant for the next phase. Implement phase P<N> exactly as planned in
docs/implementation_plan.md. Start from fresh `dev`.
Before writing code, restate the phase scope in 3–5 bullets and wait for my "go".
Done when: <copy the done criteria from the plan>.
Reply in German; repository content in English.
```

---

## 3. Tips

- One phase per session; start a new session (or `/clear`) after each phase.
- Read and correct the P0 plan carefully — it drives everything else.
- Do not auto-approve `git push`, `rm` or `docker system prune`; approving edits and read-only
  commands (`uv run …`, `git status`, `docker compose ps/logs`) is fine.
- Ask for evidence: commands and their output, not "it works".
- Every PR is reviewed by another team member before it is merged.
