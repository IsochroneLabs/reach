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
# Stages after `tiles verify` in `make refresh` (O19).
REFRESH_STAGES = count score housing recommend validate_results publish cleanup
# data_dir of the selected config; Valhalla tiles live in <data_dir>/valhalla (host bind mount).
DATA_DIR = $(shell uv run --quiet python -c "from reach_pipeline.config import load_config; print(load_config('$(REACH_CONFIG)').data_dir)")
VALHALLA_DIR = $(abspath $(DATA_DIR)/valhalla)
COMPOSE = VALHALLA_DIR=$(VALHALLA_DIR) docker compose
# Stages that call Valhalla: `make pipeline` first makes sure it runs with config/valhalla.json.
VALHALLA_STAGES = run tiles count housing recommend validate_results
# Validation experiments (methodology §6, config/experiments.yaml); RUN_ID defaults to the
# latest run. One process per experiment, so each result.json reports its own peak RSS.
EXPERIMENTS ?= v01 v02 v03 v04 v05 v06 v07 v08 v09 v10 v11
EXPERIMENT = uv run $(if $(wildcard .env),--env-file .env) python -m reach_pipeline.experiments
# LaTeX decks: one folder per deck, slides/<deck>/<deck>.tex (docs/presentations.md);
# DECK=2026-11-25-interim builds one. Build output goes to slides/<deck>/build/ (git-ignored);
# the PDF is copied to slides/<deck>/<deck>.pdf and committed. Each deck folder holds its own
# theme copy and figures, and the theme takes the PDF date from the deck name, so the same PDF
# comes out of `make slides` and of a TeX editor.
DECKS = $(strip $(or $(DECK),$(foreach d,$(notdir $(wildcard slides/*)),$(if $(wildcard slides/$(d)/$(d).tex),$(d)))))
LATEXMK = latexmk -pdf -outdir=build -interaction=nonstopmode -halt-on-error
PDFLATEX = pdflatex -interaction=nonstopmode -halt-on-error
# Files a TeX editor writes next to the deck (git-ignored, removed by `make slides-clean`).
SLIDES_AUX = aux log nav out snm toc fls fdb_latexmk synctex.gz vrb bbl blg

.PHONY: help up down logs pipeline migrate refresh tiles-build valhalla-config experiments test lint format slides slides-check slides-editor-check slides-clean slides-new

help: ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

.env:
	@echo "Missing .env: copy .env.example to .env and set the passwords." >&2; exit 1

up: .env ## start db, api, caddy and valhalla (once tiles exist) and wait until they are healthy
	@$(COMPOSE) up -d --build --wait db api caddy
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
valhalla-config: ## recreate valhalla if config/valhalla.json changed (count fails otherwise)
	@if [ ! -f "$(VALHALLA_DIR)/valhalla_tiles.tar" ]; then \
	  echo "No tiles in $(VALHALLA_DIR) yet: valhalla not started (run make refresh)" >&2; \
	elif cmp -s config/valhalla.json "$(VALHALLA_DIR)/valhalla.effective.json"; then \
	  $(COMPOSE) up -d --wait valhalla; \
	else echo "config/valhalla.json differs from the config valhalla runs with: recreating it"; \
	  $(COMPOSE) up -d --wait --force-recreate valhalla; fi

experiments: valhalla-config ## validation experiments V1–V11 on RUN_ID (default latest), summary, figures
	@for e in $(EXPERIMENTS); do $(EXPERIMENT) $$e $(if $(RUN_ID),--run-id $(RUN_ID)) || exit $$?; done
	$(EXPERIMENT) summary figures $(if $(RUN_ID),--run-id $(RUN_ID))

test: ## run all Python tests
	uv run pytest

lint: ## lint and format check
	uv run ruff check . && uv run ruff format --check .

format: ## apply formatting and safe lint fixes
	uv run ruff format . && uv run ruff check --fix .

slides: ## build every deck to slides/<deck>/<deck>.pdf (or one with DECK=<deck>) and check the logs
	@command -v latexmk >/dev/null || { echo "latexmk not found: install TeX Live with latexmk (README, Getting started)" >&2; exit 1; }
	@for d in $(DECKS); do \
	  test -f "slides/$$d/$$d.tex" || { echo "no deck slides/$$d/$$d.tex" >&2; exit 1; }; \
	  echo "$$d" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}-' \
	    || { echo "deck name must start with YYYY-MM-DD: $$d" >&2; exit 1; }; \
	  (cd "slides/$$d" && $(LATEXMK) "$$d.tex") || exit $$?; \
	  cp "slides/$$d/build/$$d.pdf" "slides/$$d/$$d.pdf"; done
	@$(MAKE) --no-print-directory slides-check
	@echo "slides: $(foreach d,$(DECKS),slides/$(d)/$(d).pdf)"

slides-check: ## fail if a deck's build log has an overfull box or a LaTeX error ("!")
	@for d in $(DECKS); do log="slides/$$d/build/$$d.log"; \
	  test -f "$$log" || { echo "$$log missing: run make slides" >&2; exit 1; }; \
	  if grep -n 'Overfull\|^!' "$$log"; then echo "$$log: overfull box or LaTeX error" >&2; exit 1; fi; \
	done; echo "slides-check: no overfull boxes, no errors ($(DECKS))"

# Builds every deck as a TeX editor does: plain pdflatex twice in the deck folder, no TEXINPUTS,
# output into a temporary directory, so the committed PDF is never touched.
slides-editor-check: ## build every deck (or DECK=<deck>) like a TeX editor and check its log
	@command -v pdflatex >/dev/null || { echo "pdflatex not found: install TeX Live (README, Getting started)" >&2; exit 1; }
	@for d in $(DECKS); do \
	  test -f "slides/$$d/$$d.tex" || { echo "no deck slides/$$d/$$d.tex" >&2; exit 1; }; \
	  tmp=$$(mktemp -d); \
	  (cd "slides/$$d" && unset TEXINPUTS && $(PDFLATEX) -output-directory="$$tmp" "$$d.tex" >/dev/null \
	    && $(PDFLATEX) -output-directory="$$tmp" "$$d.tex" >/dev/null); rc=$$?; \
	  if [ $$rc -ne 0 ] || grep -n 'Overfull\|^!' "$$tmp/$$d.log"; then \
	    echo "slides/$$d: editor build failed or log has an overfull box/error (log: $$tmp/$$d.log)" >&2; exit 1; fi; \
	  echo "slides/$$d: editor build ok, $$(pdfinfo "$$tmp/$$d.pdf" 2>/dev/null | awk '/^Pages/{print $$2}') pages"; \
	  rm -rf "$$tmp"; done

slides-clean: ## remove build/ and the editor files (aux, log, …) of every deck; keeps the PDFs
	rm -rf slides/*/build $(foreach e,$(SLIDES_AUX),slides/*/*.$(e))

# New deck from an existing one: source, facts and figures without PDF and build files; the
# "% !TEX root" lines and the title date follow the new name.
slides-new: ## new deck: DECK=<YYYY-MM-DD-topic> FROM=<existing deck>
	@test -n "$(DECK)" -a -n "$(FROM)" || { echo "usage: make slides-new DECK=<YYYY-MM-DD-topic> FROM=<deck>" >&2; exit 2; }
	@echo "$(DECK)" | grep -Eq '^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])-[a-z0-9][a-z0-9-]*$$' \
	  || { echo "DECK must be YYYY-MM-DD-<topic> (lowercase, digits, -): $(DECK)" >&2; exit 2; }
	@test -f "slides/$(FROM)/$(FROM).tex" || { echo "no deck slides/$(FROM)/$(FROM).tex" >&2; exit 2; }
	@test ! -e "slides/$(DECK)" || { echo "slides/$(DECK) exists already" >&2; exit 2; }
	@set -e; new="slides/$(DECK)"; cp -R "slides/$(FROM)" "$$new"; \
	rm -rf "$$new/build" "$$new/$(FROM).pdf" $(foreach e,$(SLIDES_AUX),"$$new"/*.$(e)); \
	mv "$$new/$(FROM).tex" "$$new/$(DECK).tex"; \
	for f in "$$new"/facts.tex "$$new"/figures/*.tex; do [ -f "$$f" ] || continue; \
	  sed 's|^% !TEX root = \(.*\)$(FROM)\.tex$$|% !TEX root = \1$(DECK).tex|' "$$f" > "$$f.tmp"; mv "$$f.tmp" "$$f"; done; \
	dates=$$(echo "$(DECK)" | awk -F- '{split("January February March April May June July August September October November December",M," "); \
	  m=M[$$2+0]; printf "%d %s %s|%d %s %s", $$3, substr(m,1,3), $$1, $$3, m, $$1}'); \
	sed 's|^\\date\[.*\]{.*}$$|\\date['"$${dates%%|*}"']{'"$${dates#*|}"'}|' "$$new/$(DECK).tex" > "$$new/$(DECK).tex.tmp"; \
	mv "$$new/$(DECK).tex.tmp" "$$new/$(DECK).tex"; \
	echo "created $$new from slides/$(FROM): $$(grep '^\\date' "$$new/$(DECK).tex")"; \
	echo "next: in $$new/facts.tex set the run id of the run the app shows and update every number"; \
	echo "      with its source; edit the title and header comment in $$new/$(DECK).tex; then"; \
	echo "      make slides DECK=$(DECK) (rules: docs/presentations.md, 'How to add a deck')"
