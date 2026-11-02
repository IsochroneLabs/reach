# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Every PR with a user-visible or architectural change
adds a line under `Unreleased`.

## [Unreleased]

### Added
- `docs/architecture.md`: target architecture with Valhalla as the single routing engine,
  Zensus 100 m grid, weekly validated pipeline, PostGIS, FastAPI, React + MapLibre, Hetzner CX23 hosting.
- `AGENTS.md` and `CLAUDE.md`: shared rules for coding agents, incl. task workflow, docs-sync rule,
  efficiency rules, commit and version-history rules, prompting guide, terms and roles.
- `CONTRIBUTING.md`: branch, commit, PR, review and release workflow.
- `.gitignore` for Python/uv, secrets, local data and frontend builds.
- `README.md` rewritten: summary, status, features, architecture diagram, layout, setup, data
  sources, documentation, team, milestones; agents keep it up to date automatically.
- `docs/methodology.md`: binding categories, thresholds, scoring, recommender, validation
  experiments (V1–V9) and open methodology questions (M1–M6).
- `docs/glossary.md`: project vocabulary, moved out of `AGENTS.md`.

### Changed
- `AGENTS.md`: project status line, sources of truth, test/fixture rules (mocked Valhalla),
  notebook policy, `.env.example` rule; agents may push their own branch and open draft PRs;
  new config keys and docs-only changes no longer need confirmation.
- `docs/features.md` and `docs/project_management_decisions.md` updated to the current
  architecture (profiles, Hetzner hosting, O/M/V numbers, new roadmap).
- `docs/architecture.md` v0.9: methodology references point to `methodology.md`.

### Removed
- `docs/architecture_proposal.md` (superseded by `architecture.md` and `methodology.md`).
- `docs/2026_10_19_kickoff.md` (superseded early concept).
