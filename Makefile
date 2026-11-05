SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

UV ?= uv

.PHONY: help sync format check lint typecheck test ci

help: ## Show targets
	@grep -E '^[a-zA-Z0-9_.-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

sync: ## Install/sync deps (including dev group)
	$(UV) sync --dev

format: ## Format code
	$(UV) run ruff format .

check: ## Lint (no fixes)
	$(UV) run ruff check .

lint: ## Format + lint with fixes
	$(UV) run ruff format .
	$(UV) run ruff check . --fix

typecheck: ## Type check with ty
	$(UV) run ty check

test: ## Run tests
	$(UV) run pytest -q

ci: ## Everything CI runs, no fixes
	$(UV) run ruff format --check .
	$(UV) run ruff check .
	$(UV) run ty check
	$(UV) run pytest -q
