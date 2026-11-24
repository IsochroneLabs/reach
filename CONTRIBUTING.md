# Contributing to reach

How we work together: branches, commits, pull requests, reviews and releases. These rules apply to
every team member **and** to every AI assistant working on someone's behalf.

- **This file** = how we collaborate (Git workflow, reviews, releases).
- **[AGENTS.md](AGENTS.md)** = binding rules for coding agents (commands, architecture rules,
  boundaries); folder rules in `pipeline/AGENTS.md`, `api/AGENTS.md` and `web/AGENTS.md`.
- **[docs/architecture.md](docs/architecture.md)** and **[docs/methodology.md](docs/methodology.md)**
  = what the system is and what it computes.
- **[docs/implementation_plan.md](docs/implementation_plan.md)** = steps, status and dates.
- **[README.md](README.md)** = how to install and run the project.

## TL;DR

1. Never commit or push directly to `main` or `dev` (both protected).
2. Every task gets its own short-lived branch from an up-to-date `dev`.
3. Conventional Commits in English; small, self-contained commits.
4. Lint and tests pass before a PR.
5. PRs go into `dev`; a human merges after reviewing. Releases go `dev` → `main` with 2 approvals.
6. Code, `docs/architecture.md` and `docs/methodology.md` never disagree; deviations are agreed
   first, then documented.
7. No data, secrets or large files in Git — ever.
8. AI assistants push only their own topic branch and open draft PRs; they ask before marking
   ready, merging, deleting or changing the architecture or methodology.

## 1. Branches

| Branch | Purpose | Written by |
|---|---|---|
| `main` | Released versions; a push deploys production (`deploy.yml`) | Release PR from `dev`, 2 approvals |
| `dev` | Integration branch (default branch), current shared state | PRs, merged by a human |
| `<type>/<name>-<topic>` | One task | Its author (the person named in it) |

Types: `feature`, `fix`, `docs`, `refactor`, `chore`, `data`, `exp`. `<name>` is the lowercase team
name of the person who drives the work (`rico`, `socke`, `juju`), also when an AI assistant does it
on their behalf: `feature/rico-travel-times`, `fix/socke-gtfs-night-window`,
`docs/juju-data-contract`. The name makes sure two people or sessions never work on the same branch.

- One branch = one topic; a few days, not weeks. Split large tasks into several PRs.
- Never commit to or open a PR from a branch that carries another person's name.
- Never delete or rewrite someone else's branch without asking.
- `exp/…` branches hold explorations and are never merged; results become code with tests or a
  note in `docs/notes.md`.

## 2. Day-to-day workflow

```bash
git fetch --all --prune
git switch dev && git pull --ff-only
git switch -c feature/rico-travel-times

# work in small steps
git status
git add pipeline/src/reach_pipeline/stages/travel_times.py pipeline/tests/test_travel_times.py
git diff --staged
git commit

uv run ruff check . && uv run ruff format --check . && uv run pytest
git push -u origin feature/rico-travel-times   # then open a draft PR into dev
```

## 3. Commits

```
<type>(<scope>): <imperative summary>

<what and why>

Co-Authored-By: …   (pair work or AI assistant)
```

| Type | Use for |
|---|---|
| `feat` | New functionality |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change without behaviour change (also ports from the archive) |
| `test` | Tests |
| `data` | Data sources, pipeline inputs |
| `chore` | Tooling, dependencies, housekeeping |
| `ci` | Workflows |

Scopes: `pipeline`, `api`, `web`, `infra`, `config`, `ci`, `docs`, `repo`, `exp`.

Good: `feat(pipeline): compute transit times per trip window` ·
`fix(api): reject cells outside the city` · `docs(architecture): record T1 decision`.
Not okay: `update`, `wip`, `fix stuff`, `changes`.

- One logical change per commit, code left working; code + tests + required docs together;
  `pyproject.toml` and `uv.lock` together. A port from the archive names its source path.
- `git status` and `git diff --staged` before every commit; stage files explicitly.
- **Never commit:** `data/`, datasets, files > 10 MB, `.env`, keys, tokens, passwords, `.venv/`,
  caches, notebook outputs, build output. Missing `.gitignore` entry → add it in the same PR.
- Secret committed by accident → tell the team immediately and rotate the key.

## 4. Pull requests

- **Base: `dev`.** Only release PRs go from `dev` to `main`.
- **Title** in Conventional Commit format; **body** from `.github/pull_request_template.md`
  (What, Why, How tested, Docs, Open points, Related; on whose behalf an assistant worked).
- Small enough to review in ~15 minutes where possible; ports and skeletons may be larger, split
  into one commit per area.
- Update `docs/data_contract.md`, `docs/glossary.md`, `docs/notes.md`, `README.md`,
  `CHANGELOG.md` and the status block of `docs/implementation_plan.md` in the same PR when the
  change affects them.

### Review and merge

- **Into `dev`:** CI must be green (required status checks); no approval count is enforced. A
  human merges after reviewing the diff — ideally someone other than the author; nobody merges a
  PR they have not read.
- **Into `main` (release):** 2 approvals, then a human merges; the push runs `deploy.yml`.
- Merge with **"Squash and merge"** into `dev`; the topic branch is deleted by its author.
- AI assistants never merge and never mark a PR ready unless their human explicitly says so.

## 5. Staying up to date and conflicts

```bash
git fetch origin
git rebase origin/dev            # only on your own topic branch
uv run ruff check . && uv run pytest
git push --force-with-lease      # never plain --force
```

- Force-pushing only on your own topic branch, never on `main` or `dev`; no `git reset --hard`
  on shared branches.
- Conflicts: understand both sides and combine them deliberately; ask the owner before resolving
  conflicts in their code; re-run checks afterwards.

## 6. Architecture and methodology changes

`docs/architecture.md` and `docs/methodology.md` are binding. If the code has to differ from them:

1. Raise it (issue or PR comment) with the reason and the proposed doc change.
2. Get agreement from the team.
3. Implement and update the document in the same PR: bump the version line, add a change-log
   line, move the decision to "Settled".

## 7. Versions, releases and deployment

- **`CHANGELOG.md`** ([Keep a Changelog](https://keepachangelog.com/)): every PR with a visible or
  architectural change adds a line under `## [Unreleased]`.
- **Versions** follow [Semantic Versioning](https://semver.org/); milestones in
  `docs/implementation_plan.md`:

| Version | Milestone | Target |
|---|---|---|
| `v0.1.0` | Walking skeleton: placeholder page deployed through `main` → `deploy.yml` → Cloudflare | 30 Nov 2026 |
| `v0.2.0` | Backend in production (pipeline + API on the server) | 14 Dec 2026 |
| `v0.3.0` | Student web app (U1–U3) | 9 Jan 2027 |
| `v0.4.0` | Hardening | 16 Jan 2027 |
| `v1.0.0` | Submission | 22 Jan 2027 |

- **Release procedure:** PR `dev` → `main` titled `chore(release): vX.Y.Z`; in it, move the
  `Unreleased` entries into a version section of `CHANGELOG.md` and bump `version` in the
  `pyproject.toml` files and `web/package.json`. After 2 approvals a human merges; `deploy.yml`
  deploys (CI → images by SHA → frontend → backend → smoke test → rollback on failure). Tags and
  GitHub Releases only on explicit decision of the team.
- **Nobody deploys by hand** (`docs/deployment.md`).

## 8. Code quality

See `AGENTS.md` (efficient code, code style, tests). In short: ruff (line length 100), type hints,
short docstrings, `logging`, config over hard-coding, vectorised and streamed data processing,
tests for new logic, no notebooks in the pipeline.

## 9. Working with AI assistants

AI assistants follow this file and `AGENTS.md`. They may push their own topic branch and open draft
PRs into `dev`. They ask their human before marking a PR ready, merging, deleting, tagging,
releasing, changing dependencies, services, existing config values or structure, changing
`docs/architecture.md` or `docs/methodology.md` or deviating from them, and touching another
member's code. They never create, read or print secrets. They state a plan before larger changes,
attribute their commits with a co-author trailer, and end with a report (branch, commits, PR link,
checks, open points).

## 10. Communication

- GitHub Issues for tasks, bugs and questions; reference them in branches and PRs.
- Interface changes (data contract, config keys, shared code) are agreed with the affected owners
  first.
- Decisions are recorded in `docs/architecture.md` (O-, T-, D-numbers) and `docs/methodology.md`
  (M-numbers); findings and deferred work in `docs/notes.md`.
