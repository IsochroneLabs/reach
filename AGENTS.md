# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Copilot, Cursor, …) working in this repository.
This is a placeholder while the project is rebuilt. The previous project and its full rules live in
the locked branch `archive/2026-11-21-planner`.

Project definition, architecture and commands follow in the rebuild; until then ask before creating structure.

## Terms and roles

| Term | Meaning |
|---|---|
| **you** | The coding agent reading this file (any tool, any session). |
| **your human** | The team member who started your session and gives you the task. Confirmations come from them. |
| **we / the team** | **Rico** (GitHub `RicoS03`), **Socke** (`konstantinholl`), **Juju** (`nicholas-tuebi`). |
| **ask first** | Stop, describe what you want to do and why, and wait for your human's explicit "yes". |

## Basics

- **Python via uv only.** No `pip install`, no hand-made virtual environments.
- **No data or secrets in git.** Never commit datasets, `data/`, `.env`, keys, tokens, passwords,
  files > 10 MB, `.venv/`, caches or build output.
- Code, comments, commit messages, PRs and docs are in English.

## Branches and commits

- Base branch **`dev`**; `main` only receives milestone releases via PR from `dev`.
- Branch per topic from fresh `dev` (`git fetch --all --prune` first), named
  `<type>/<name>-<topic>`: type `feature`, `fix`, `docs`, `refactor`, `chore`, `data` or `exp`;
  `<name>` = your human's lowercase team name (`rico`, `socke`, `juju`).
- Never commit to, push to or open a PR from a branch that carries another person's name.
- **Conventional Commits:** `<type>(<scope>): <imperative summary>`, body with what and why, and a
  co-author trailer for the assistant used. Not okay: `update`, `wip`, `fix stuff`, `changes`.
- One logical change per commit; stage files explicitly (no blind `git add .`).
- Add a line under `## [Unreleased]` in `CHANGELOG.md` for every user-visible change.

## Never

- Commit or push directly to `main` or `dev`; `git push --force` on `main`/`dev`; `git reset --hard`
  on shared branches; rewrite or delete someone else's branch; merge PRs unless explicitly told to.
- Push to or change `archive/2026-11-21-planner`.
- Commit data, secrets or large files.
- Use `pip install` or hand-made virtual environments (use uv).
- Disable tests, lint rules or validation checks to make something pass.
