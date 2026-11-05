SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

UV ?= uv

.PHONY: help sync format check lint typecheck test ci build smoke

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

build: ## Build the sdist and wheel into dist/ (clearing old builds)
	$(UV) build --clear

smoke: ## Install the built wheel in a clean env and run both commands
	@ls dist/*.whl >/dev/null 2>&1 || { echo "run make build first"; exit 1; }
	$(UV) run --isolated --no-project --with dist/*.whl koreader-d00901 --version
	$(UV) run --isolated --no-project --with dist/*.whl koreader-d00901-tui --version
	$(UV) run --isolated --no-project --with dist/*.whl python -c "from koreader_d00901.packages import load_manifest; assert len(load_manifest()) == 6"
