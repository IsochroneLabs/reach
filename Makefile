# Thin wrappers around uv and docker compose (arch. §7, §12). Run from the repository root.
# `make pipeline` runs on the host with uv against the services started by `make up`.
# REACH_CONFIG selects the config, e.g. `make refresh REACH_CONFIG=config/test_clip.yaml`.
# Order: make command line, shell, REACH_CONFIG in .env, then config/config.yaml. Reading .env
# keeps the pipeline on the same config that compose passes to the API.

STAGE ?= run
ifndef REACH_CONFIG
REACH_CONFIG := $(or $(shell sed -n 's/^REACH_CONFIG=//p' .env 2>/dev/null | tail -n 1 | tr -d "\"'"),config/config.yaml)
endif
export REACH_CONFIG
# .env (connection strings, passwords, webhook) is passed to the pipeline when it exists;
# variables already set in the shell or on the make command line win.
PIPELINE = uv run $(if $(wildcard .env),--env-file .env) python -m reach_pipeline
# Stages after `transit verify` in `make refresh` (arch. §7).
REFRESH_STAGES = travel_times validate_results publish cleanup
# data_dir of the selected config; Valhalla tiles live in <data_dir>/valhalla (host bind mount).
DATA_DIR = $(shell uv run --quiet python -c "from reach_pipeline.config import load_config; print(load_config('$(REACH_CONFIG)').data_dir)")
VALHALLA_DIR = $(abspath $(DATA_DIR)/valhalla)
# OpenTripPlanner graph served from <data_dir>/otp (O17); heap sizes from the otp section.
OTP_DIR = $(abspath $(DATA_DIR)/otp)
OTP_HEAPS = $(shell uv run --quiet python -c "from reach_pipeline.config import load_config; o = load_config('$(REACH_CONFIG)').otp; print(f'OTP_BUILD_HEAP={o.build_heap} OTP_SERVE_HEAP={o.serve_heap}' if o else '')")
COMPOSE = VALHALLA_DIR=$(VALHALLA_DIR) OTP_DIR=$(OTP_DIR) $(OTP_HEAPS) docker compose
# Stages that call Valhalla: `make pipeline` first makes sure it runs with config/valhalla.json.
VALHALLA_STAGES = run tiles

.PHONY: help up down logs pipeline migrate refresh tiles-build transit-build otp-up valhalla-config test lint format

help: ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

.env:
	@echo "Missing .env: copy .env.example to .env and set the passwords." >&2; exit 1

up: .env ## start db, api, valhalla and otp (once their graphs exist) and wait until healthy
	@$(COMPOSE) up -d --build --wait db api
	@$(MAKE) --no-print-directory valhalla-config
	@$(MAKE) --no-print-directory otp-up

down: ## stop the local stack (volumes are kept)
	docker compose down

logs: ## follow the logs of all services
	docker compose logs -f

pipeline: $(if $(filter $(firstword $(STAGE)),$(VALHALLA_STAGES)),valhalla-config) ## run all pipeline stages, or one with STAGE=<name>
	$(PIPELINE) $(STAGE)

migrate: .env ## create/update DB roles, meta schema and migrations (needs DATABASE_URL_ADMIN)
	$(PIPELINE) migrate

# Full refresh (arch. §7, O5): new run → tile rebuild only if its inputs changed → swap →
# restart → verify → remaining stages. Without a rebuild, `up` only makes sure Valhalla serves
# this config's tiles (no restart if it already does). The scheduled job on the server (S3.1)
# calls this target.
refresh: .env ## acquire, validate, tiles, transit graph, travel times, checks, publish, cleanup
	$(PIPELINE) acquire
	$(PIPELINE) validate
	$(PIPELINE) tiles check
	@flag="$(DATA_DIR)/runs/$$(ls $(DATA_DIR)/runs | tail -n 1)/tiles/rebuild_needed"; \
	if [ -f "$$flag" ]; then $(MAKE) --no-print-directory tiles-build FLAG="$$flag"; \
	else echo "tiles up to date, no rebuild"; $(MAKE) --no-print-directory valhalla-config; fi
	$(PIPELINE) tiles verify
	$(PIPELINE) transit prepare
	@$(MAKE) --no-print-directory transit-build BUILD_DIR="$(DATA_DIR)/runs/$$(ls $(DATA_DIR)/runs | tail -n 1)/transit"
	$(PIPELINE) transit verify
	@for stage in $(REFRESH_STAGES); do $(PIPELINE) $$stage || exit $$?; done

# Internal step of `refresh` (O17): build the OTP graph in the run's transit/ directory with the
# one-shot otp-build container (a few seconds), copy graph.obj and router-config.json into
# $(OTP_DIR) (previous graph kept as graph.prev.obj) and recreate otp.
transit-build:
	@test -n "$(BUILD_DIR)" || { echo "BUILD_DIR=<run>/transit is required" >&2; exit 2; }
	@set -e; start=$$(date +%s); \
	OTP_BUILD_DIR="$(abspath $(BUILD_DIR))" $(COMPOSE) --profile build run --rm otp-build; \
	echo "transit graph build took $$(( $$(date +%s) - start )) s"; \
	mkdir -p "$(OTP_DIR)"; \
	if [ -f "$(OTP_DIR)/graph.obj" ]; then mv "$(OTP_DIR)/graph.obj" "$(OTP_DIR)/graph.prev.obj"; fi; \
	cp "$(BUILD_DIR)/graph.obj" "$(BUILD_DIR)/router-config.json" "$(OTP_DIR)/"; \
	rm -f "$(BUILD_DIR)/graph.obj"; \
	$(COMPOSE) up -d --wait --force-recreate otp; \
	echo "transit graph swapped in and otp restarted ($(OTP_DIR))"

# Start otp if a graph exists (make up).
otp-up:
	@if [ -f "$(OTP_DIR)/graph.obj" ]; then $(COMPOSE) up -d --wait otp; \
	else echo "No transit graph in $(OTP_DIR) yet: otp not started (run make refresh)" >&2; fi

# Internal step of `refresh`: build into $(VALHALLA_DIR)/build, then swap with two `mv` on the
# same file system (live tiles kept as valhalla_tiles.prev.tar for rollback) and restart.
tiles-build:
	@test -n "$(FLAG)" || { echo "FLAG=<rebuild_needed file> is required" >&2; exit 2; }
	@set -e; . "$(abspath $(FLAG))"; \
	mkdir -p "$(VALHALLA_DIR)/build" "$(VALHALLA_DIR)/elevation"; \
	ln -f "$$PBF" "$(VALHALLA_DIR)/build/routing.osm.pbf" 2>/dev/null || cp "$$PBF" "$(VALHALLA_DIR)/build/routing.osm.pbf"; \
	start=$$(date +%s); \
	ELEVATION="$$ELEVATION" BBOX="$$BBOX" $(COMPOSE) --profile build run --rm valhalla-build; \
	echo "tile build took $$(( $$(date +%s) - start )) s"; \
	mv "$(VALHALLA_DIR)/build/valhalla_tiles.tar" "$(VALHALLA_DIR)/valhalla_tiles.new.tar"; \
	rm -f "$(VALHALLA_DIR)/build/routing.osm.pbf"; \
	if [ -f "$(VALHALLA_DIR)/valhalla_tiles.tar" ]; then \
	  mv "$(VALHALLA_DIR)/valhalla_tiles.tar" "$(VALHALLA_DIR)/valhalla_tiles.prev.tar"; fi; \
	mv "$(VALHALLA_DIR)/valhalla_tiles.new.tar" "$(VALHALLA_DIR)/valhalla_tiles.tar"; \
	$(COMPOSE) up -d --wait --force-recreate valhalla; \
	echo "$$SHA256" > "$(VALHALLA_DIR)/tiles_source.sha256"; \
	echo "tiles swapped in and valhalla restarted ($(VALHALLA_DIR))"

# Valhalla reads its config only at start and serves the copy valhalla.effective.json written
# then (compose.yaml): recreate the service if that copy differs from config/valhalla.json,
# otherwise only make sure it runs (notes N5).
valhalla-config: ## recreate valhalla if config/valhalla.json changed
	@if [ ! -f "$(VALHALLA_DIR)/valhalla_tiles.tar" ]; then \
	  echo "No tiles in $(VALHALLA_DIR) yet: valhalla not started (run make refresh)" >&2; \
	elif cmp -s config/valhalla.json "$(VALHALLA_DIR)/valhalla.effective.json"; then \
	  $(COMPOSE) up -d --wait valhalla; \
	else echo "config/valhalla.json differs from the config valhalla runs with: recreating it"; \
	  $(COMPOSE) up -d --wait --force-recreate valhalla; fi

test: ## run all Python tests
	uv run pytest

lint: ## lint and format check
	uv run ruff check . && uv run ruff format --check .

format: ## apply formatting and safe lint fixes
	uv run ruff format . && uv run ruff check --fix .
