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
