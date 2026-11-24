# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

- *Check* for one place (S2.5): address search or pin, fit, rank in the city, weekly travel time, trips by mode and trip window with bus details, optional listing rent kept in the browser, "better places nearby" in *Find*
- *Find* (S2.4): MapLibre map with the cell fits, legend, rank markers and a cell popup; the three best areas with reasons, weekly travel time and data date; "Check here" opens *Check*
- Profile panel (S2.3): programme hint, modes, destinations with importance, fine time and trips per week, example profiles with undo; every change recolours the results
- Web app shell (S2.2): typed API client with a fixture mode on sample data of Tübingen, English/German texts, header with Find/Check switch and address search, responsive layout with a bottom sheet on phones, student profile and places in the URL hash and `localStorage`; default campus mix `campus.default_mix` (Tal + Morgenstelle)
- Screen plan for the web app (S2.1, draft): screens for *Find* and *Check* on desktop and mobile, components, state in the URL hash and `localStorage`, fit request flow, texts EN/DE, basemap options (D5) and default campus mix proposals (`docs/app_screens.md`)
- Product v1.1: two modes *Find* and *Check* instead of U1–U3, map with a default profile and a profile panel instead of an onboarding questionnaire, rent typed in per listing (never in the fit), English first (`docs/product.md`, plan Phase 2, glossary, personas)
- Transit engine decided (T1 → O17): OpenTripPlanner 2.10 for transit and bike + transit; transit time includes the wait at home (M6); bike + transit parks the bike (M5)
- Settled Cloudflare Workers static assets for the frontend and documented the current static asset billing model.
- Emptied dev for the rebuild; old project archived in archive/2026-11-21-planner (21 Nov 2026)
- Implementation plan for the student rebuild with phases, steps, releases and risks (`docs/implementation_plan.md`)
- Foundation ported from the archive (S0.4): uv workspace, pipeline stages acquire → validate (reference date per trip window) → tiles → publish → cleanup, PostGIS roles and run-schema subset, API skeleton with health (build SHA) and CORS allowlist, compose, Makefile, API and pipeline images, folder rules and CONTRIBUTING
- Walking skeleton (S0.5): web placeholder (name, build SHA, API health) with Playwright smoke tests; `ci.yml` (python, db-contract, web, docker-build, Cloudflare previews) and `deploy.yml` (CI on the SHA → GHCR images → Cloudflare Worker with static assets → backend skipped until S1.5 → smoke test → rollback + team webhook → summary)
- OSM source URL updated to Geofabrik's new extract path (old path returns 404)
- Sources of truth for the student rebuild: glossary, AGENTS.md, README, product, architecture and methodology drafts (fit formula, T1 and D1–D5 open), deployment, data contract, notes, OSM tagging; draft config with routing profiles, trip windows, destination types, campus sites and personas
