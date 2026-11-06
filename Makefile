# Thin wrappers around uv and docker compose (arch. §7, §14). Run from the repository root.
# `make pipeline` runs on the host with uv against the services started by `make up`.
# REACH_CONFIG selects the config (default config/config.yaml), e.g.
# `make refresh REACH_CONFIG=config/test_clip.yaml`.

STAGE ?= run
REACH_CONFIG ?= config/config.yaml
export REACH_CONFIG
# .env (connection strings, passwords, webhook) is passed to the pipeline when it exists;
# variables already set in the shell or on the make command line win.
PIPELINE = uv run $(if $(wildcard .env),--env-file .env) python -m reach_pipeline
# Stages after `tiles verify` in `make refresh` (O19); recommend follows in P7.
REFRESH_STAGES = count score validate_results publish cleanup
# data_dir of the selected config; Valhalla tiles live in <data_dir>/valhalla (host bind mount).
DATA_DIR = $(shell uv run --quiet python -c "from reach_pipeline.config import load_config; print(load_config('$(REACH_CONFIG)').data_dir)")
VALHALLA_DIR = $(abspath $(DATA_DIR)/valhalla)
COMPOSE = VALHALLA_DIR=$(VALHALLA_DIR) docker compose
# Stages that call Valhalla: `make pipeline` first makes sure it runs with config/valhalla.json.
VALHALLA_STAGES = run tiles count validate_results

.PHONY: help up down logs pipeline migrate refresh tiles-build valhalla-config test lint format

help: ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

.env:
	@echo "Missing .env: copy .env.example to .env and set the passwords." >&2; exit 1

up: .env ## start db, api, caddy and valhalla (once tiles exist) and wait until they are healthy
	@if [ -f "$(VALHALLA_DIR)/valhalla_tiles.tar" ]; then $(COMPOSE) up -d --build --wait; \
	else echo "No tiles in $(VALHALLA_DIR) yet: starting without valhalla (run make refresh)" >&2; \
	$(COMPOSE) up -d --build --wait db api caddy; fi
	@$(MAKE) --no-print-directory valhalla-config

down: ## stop the local stack (volumes are kept)
	docker compose down

logs: ## follow the logs of all services
	docker compose logs -f

pipeline: $(if $(filter $(firstword $(STAGE)),$(VALHALLA_STAGES)),valhalla-config) ## run all pipeline stages, or one with STAGE=<name>
	$(PIPELINE) $(STAGE)

migrate: .env ## create/update DB roles, meta schema and migrations (needs DATABASE_URL_ADMIN)
	$(PIPELINE) migrate

# Full refresh (O19): new run → tile rebuild only if its inputs changed → swap → restart →
# verify → remaining stages. Without a rebuild, `up` only makes sure Valhalla serves this
# config's tiles (no restart if it already does). The systemd timer (P8) calls this target.
refresh: .env ## acquire, validate, rebuild + swap tiles if needed, restart valhalla, count … cleanup
	$(PIPELINE) acquire
	$(PIPELINE) validate
	$(PIPELINE) tiles check
	@flag="$(DATA_DIR)/runs/$$(ls $(DATA_DIR)/runs | tail -n 1)/tiles/rebuild_needed"; \
	if [ -f "$$flag" ]; then $(MAKE) --no-print-directory tiles-build FLAG="$$flag"; \
	else echo "tiles up to date, no rebuild"; $(MAKE) --no-print-directory valhalla-config; fi
	$(PIPELINE) tiles verify
	@for stage in $(REFRESH_STAGES); do $(PIPELINE) $$stage || exit $$?; done

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
# otherwise only make sure it runs. `count` fails if they still differ (notes N9).
valhalla-config:
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
