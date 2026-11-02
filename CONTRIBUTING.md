# Contributing to reach

How we work together: branches, commits, pull requests, reviews and releases. These rules apply
to every team member **and** to every AI assistant working on someone's behalf.

- **This file** = how we collaborate (Git workflow, reviews, releases).
- **[AGENTS.md](AGENTS.md)** = binding rules for coding agents (commands, architecture rules, boundaries).
- **[docs/architecture.md](docs/architecture.md)** = what the system is and how it works.
- **[README.md](README.md)** = how to install and run the project.

> Our GitHub plan may not enforce branch protection. Nothing technically stops a direct push to
> `main` or `dev` — these rules work because we all follow them.

## TL;DR

1. Never commit or push directly to `main` or `dev`.
2. Every task gets its own short-lived branch from an up-to-date `dev`.
3. Conventional Commits in English; small, self-contained commits.
4. Lint and tests pass before a PR (`uv run ruff check . && uv run pytest`).
5. PRs go into `dev` and need an approving review by **another** team member.
6. Code and `docs/architecture.md` never disagree; deviations are agreed first, then documented.
7. No data, secrets or large files in Git — ever.
8. AI assistants ask their human before pushing, opening PRs, merging, deleting or changing the architecture.

## 1. Branches

| Branch | Purpose | Written by |
|---|---|---|
| `main` | Tagged milestone releases only | PR from `dev` at milestones |
| `dev` | Integration branch, current shared state | Reviewed PRs only |
| `<type>/<topic>` | One task | Its author |

Types: `feature`, `fix`, `docs`, `refactor`, `data`, `exp`. Lowercase, hyphenated, issue number
first if there is one: `feature/12-matrix-batching`, `fix/gtfs-reference-weekday`,
`docs/data-contract`.

- One branch = one topic; a few days, not weeks. Split large tasks into several PRs.
- No personal long-running branches (`rico`, `konsti`).
- Never delete or rewrite someone else's branch without asking.

## 2. Day-to-day workflow

```bash
git fetch --all --prune
git switch dev && git pull --ff-only
git switch -c feature/12-matrix-batching

# work in small steps
git status
git add pipeline/src/reach_pipeline/count.py pipeline/tests/test_count.py
git diff --staged
git commit

uv run ruff check . && uv run ruff format --check . && uv run pytest
git push -u origin feature/12-matrix-batching   # then open a PR into dev
```

## 3. Commits

```
<type>(<scope>): <imperative summary>

<what and why>

Closes #12
Co-authored-by: …   (pair work or AI assistant)
```

| Type | Use for |
|---|---|
| `feat` | New functionality |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change without behaviour change |
| `test` | Tests |
| `data` | Data sources, pipeline inputs |
| `chore` | Tooling, dependencies, housekeeping |
| `style` | Formatting only |
| `ci` | CI configuration |

Scopes: `pipeline`, `api`, `web`, `infra`, `config`, `docs`, `repo`.

Good: `feat(pipeline): count reachable facilities with batched Valhalla matrix` ·
`fix(api): reject pin-drops outside the urban boundary` · `docs(architecture): record O17 decision`.
Not okay: `update`, `wip`, `fix stuff`, `final version 2`.

- One logical change per commit, code left working; code + tests + required docs together;
  `pyproject.toml` and `uv.lock` together.
- `git status` and `git diff --staged` before every commit; stage files explicitly.
- **Never commit:** `data/`, datasets, files > 10 MB, `.env`, keys, tokens, passwords, `.venv/`,
  caches, notebook outputs, build output. Missing `.gitignore` entry → add it in the same PR.
- Secret committed by accident → tell the team immediately and rotate the key.

## 4. Pull requests

- **Base: `dev`.** Only release PRs go from `dev` to `main`.
- **Title** in Conventional Commit format (becomes the squash commit on `dev`).
- **Description template:**

```markdown
## What
Short summary.

## Why
Problem or motivation.

## How tested
Commands and results (e.g. `uv run pytest` → 14 passed), manual checks
(e.g. "pipeline on test clip: 312 cells, 41 s, peak 0.6 GB").

## Docs
architecture.md / data_contract.md / README / CHANGELOG updated? Which sections?

## Open points
Limitations, follow-ups, questions.

## Related
Closes #12

<!-- If an AI assistant prepared this PR: -->
Prepared by <assistant> on behalf of @<github-user>.
```

- Small enough to review in ~15 minutes.
- Update `docs/architecture.md`, `docs/data_contract.md`, `README.md` and `CHANGELOG.md` in the
  same PR when the change affects them.

### Review and merge

- At least **one approving review by another team member**; nobody approves their own PR.
- Reviewers check: it runs, tests exist and pass, readable, consistent with `architecture.md`
  and the data contract, docs updated, no data or secrets.
- The author merges with **"Squash and merge"** after approval and deletes the branch.
- AI assistants never merge unless their human explicitly says so.

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

## 6. Architecture changes

`docs/architecture.md` is binding. If the code has to differ from it:

1. Raise it (issue or PR comment) with the reason and the proposed doc change.
2. Get agreement from the team (at least the owners of the affected folders).
3. Implement and update `architecture.md` in the same PR: bump the version line, add a change-log
   line, move the decision to "Settled" in §13.

## 7. Versions and history

- **`CHANGELOG.md`** ([Keep a Changelog](https://keepachangelog.com/)): every PR with a visible or
  architectural change adds a line under `## [Unreleased]`.
- **Releases** ([Semantic Versioning](https://semver.org/)) are tags on `main`:

| Version | Milestone |
|---|---|
| `v0.1.0` | Interim presentation (25 Nov 2026) |
| `v0.x.0` | Intermediate milestones |
| `v1.0.0` | Final submission (22 Jan 2027, 23:59) |

Release procedure: PR `dev` → `main` titled `chore(release): v0.1.0` (reviewed); in it, move the
`Unreleased` entries to a new version section in `CHANGELOG.md` and bump `version` in the
`pyproject.toml` files; after merge tag `main` (`git tag -a v0.1.0 -m "Interim presentation"`)
and create a GitHub Release with the changelog section.

## 8. Code quality

See `AGENTS.md` (code style, efficient code, tests). In short: ruff, type hints, docstrings,
`logging`, config over hard-coding, vectorised and streamed data processing, tests for new
pipeline logic, no notebooks in the pipeline.

## 9. Working with AI assistants

AI assistants follow this file and `AGENTS.md`. They ask their human for explicit confirmation
before pushing, opening or updating PRs/issues, merging, deleting, force-pushing, tagging,
releasing, changing dependencies or structure, changing `docs/architecture.md` or deviating from
it, and touching another member's code. They state a plan before larger changes, attribute their
commits with a co-author trailer, never commit secrets, ask instead of guessing, and end with a
summary (branch, commits, PR link, open points).

## 10. Communication

- GitHub Issues for tasks, bugs and questions; reference them in branches and PRs (`Closes #12`).
- Interface changes (data contract, config keys, shared code) need an issue and agreement of the
  affected owners first.
- Decisions are recorded in `docs/architecture.md` §13 (technical) and
  `docs/project_management_decisions.md` (team).
