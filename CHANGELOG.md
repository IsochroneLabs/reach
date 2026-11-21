# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

- Emptied dev for the rebuild; old project archived in archive/2026-11-21-planner (21 Nov 2026)
- Implementation plan for the student rebuild with phases, steps, releases and risks (`docs/implementation_plan.md`)
- Foundation ported from the archive (S0.4): uv workspace, pipeline stages acquire → validate (reference date per trip window) → tiles → publish → cleanup, PostGIS roles and run-schema subset, API skeleton with health (build SHA) and CORS allowlist, compose, Makefile, API and pipeline images, folder rules and CONTRIBUTING
- OSM source URL updated to Geofabrik's new extract path (old path returns 404)
- Sources of truth for the student rebuild: glossary, AGENTS.md, README, product, architecture and methodology drafts (fit formula, T1 and D1–D5 open), deployment, data contract, notes, OSM tagging; draft config with routing profiles, trip windows, destination types, campus sites and personas
