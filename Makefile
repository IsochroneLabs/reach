# Thin wrappers around uv and docker compose (arch. §7, §14). Run from the repository root.
# `make pipeline` runs on the host with uv against the services started by `make up`.

STAGE ?= run

.PHONY: help up down logs pipeline test lint format

help: ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

.env:
	@echo "Missing .env: copy .env.example to .env and set the passwords." >&2; exit 1

up: .env ## start db, api and caddy and wait until they are healthy
	docker compose up -d --wait

down: ## stop the local stack (volumes are kept)
	docker compose down

logs: ## follow the logs of all services
	docker compose logs -f

pipeline: ## run all pipeline stages, or one with STAGE=<name>
	uv run python -m reach_pipeline $(STAGE)

test: ## run all Python tests
	uv run pytest

lint: ## lint and format check
	uv run ruff check . && uv run ruff format --check .

format: ## apply formatting and safe lint fixes
	uv run ruff format . && uv run ruff check --fix .
