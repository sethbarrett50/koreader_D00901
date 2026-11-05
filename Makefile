SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

UV ?= uv

.PHONY: help sync format check lint typecheck test ci build smoke version-check screenshot

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
	$(UV) run --isolated --no-project --with dist/*.whl koreader-d00901-battery --version
	$(UV) run --isolated --no-project --with dist/*.whl python -c "from koreader_d00901.packages import load_manifest; assert len(load_manifest()) == 6"

version-check: ## Fail if src/ or dependencies changed since the last vX.Y.Z tag without a version bump
	@last="$$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null)"; \
	version="$$($(UV) version --short)"; \
	if [ -z "$$last" ]; then echo "no release tag yet; version $$version will be the first release"; exit 0; fi; \
	if git diff --quiet "$$last" HEAD -- src pyproject.toml uv.lock; then echo "no package changes since $$last"; exit 0; fi; \
	highest="$$(printf '%s\n%s\n' "$${last#v}" "$$version" | sort -V | tail -n1)"; \
	if [ "$$version" = "$${last#v}" ] || [ "$$highest" != "$$version" ]; then \
	  echo "error: the package changed since $$last but pyproject version is $$version;"; \
	  echo "bump it (uv version --bump patch|minor|major) so the next PyPI release gets a new version"; exit 1; \
	fi; \
	echo "version $$version > $$last: ok"

screenshot: ## Regenerate docs/tui.svg from the TUI
	$(UV) run python scripts/screenshot.py
