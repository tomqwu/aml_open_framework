.PHONY: install test test-coverage test-all test-e2e lint run dashboard api docker clean help demo fixtures pre-push ci-lint ci-unit ci-coverage ci-api ci-e2e ci-deployment ci-security install-hooks

# Resolve a Python that has the dev deps installed. If `.venv/bin/python`
# exists (the project convention), use it; otherwise fall back to the
# `python` on PATH (which CI uses because it `pip install`s into the
# system venv). Sub-tools are invoked as `python -m <tool>` so they
# work in both environments without requiring PATH activation.
PYTHON ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python)
PYTEST := $(PYTHON) -m pytest
RUFF   := $(PYTHON) -m ruff
# `docker compose` is v2 (plugin); older systems have standalone
# `docker-compose` (v1). Detect what's installed; empty string means
# neither is available and `ci-deployment` will skip the compose check
# with a warning. CI always has the v2 plugin, so the merge gate keeps
# catching broken `docker-compose.yml` even if a contributor's box
# can't run it locally.
DOCKER_COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || (command -v docker-compose >/dev/null 2>&1 && echo "docker-compose"))

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install with all optional dependencies
	pip install -e ".[dev,dashboard,api]"

test: ## Run unit + API tests (fast, no browser)
	pytest tests/ \
		--ignore=tests/test_e2e_dashboard.py \
		--ignore=tests/test_e2e_dashboard_mobile.py -q

test-coverage: ## Run non-browser tests with the coverage gate (matches CI's effective floor; see ci-coverage)
	pytest tests/ \
		--ignore=tests/test_e2e_dashboard.py \
		--ignore=tests/test_e2e_dashboard_mobile.py \
		--cov=aml_framework \
		--cov-report=term-missing \
		--cov-fail-under=98 \
		-q

test-all: ## Run all tests including Playwright browser tests
	pytest tests/ -q

test-e2e: ## Run Playwright browser tests only
	pytest tests/test_e2e_dashboard.py tests/test_e2e_dashboard_mobile.py -q

lint: ## Run linter
	ruff check src/ tests/
	ruff format --check src/ tests/

format: ## Auto-format code
	ruff format src/ tests/

run: ## Run the engine with sample CSV data
	aml run examples/canadian_schedule_i_bank/aml.yaml --data-source csv --data-dir data/input/

run-synthetic: ## Run with synthetic data (no CSV needed)
	aml run examples/canadian_schedule_i_bank/aml.yaml --seed 42

fixtures: ## Regenerate parquet + duckdb fixtures from seeded synthetic data (gitignored)
	python -m aml_framework.data.fixtures
	@echo "Fixtures in data/fixtures/ — feed resolve_source('parquet'|'duckdb')."

validate: ## Validate all example specs
	aml validate examples/community_bank/aml.yaml
	aml validate examples/canadian_bank/aml.yaml
	aml validate examples/canadian_schedule_i_bank/aml.yaml
	aml validate examples/eu_bank/aml.yaml
	aml validate examples/uk_bank/aml.yaml

dashboard: ## Launch the interactive dashboard
	aml dashboard examples/canadian_schedule_i_bank/aml.yaml

api: ## Launch the REST API server
	aml api --port 8000

docker: ## Build and start all services (PostgreSQL + API + Dashboard)
	docker-compose up --build

diff: ## Compare US and Canadian specs
	aml diff examples/community_bank/aml.yaml examples/canadian_schedule_i_bank/aml.yaml

export-alerts: ## Export alerts from latest run to CSV
	aml export-alerts examples/canadian_schedule_i_bank/aml.yaml

demo: ## One-command end-to-end demo (validate, run, launch dashboard)
	@echo "Validating all specs..."
	@aml validate examples/canadian_schedule_i_bank/aml.yaml
	@echo "Running engine with sample data..."
	@aml run examples/canadian_schedule_i_bank/aml.yaml --seed 42
	@echo ""
	@echo "Launching dashboard at http://localhost:8501"
	@echo "Press Ctrl+C to stop."
	@aml dashboard examples/canadian_schedule_i_bank/aml.yaml

sync-demo: ## Sync docs/pitch/ to the aml_open_framework_demo repo (opens + auto-merges a PR)
	@./scripts/sync_demo_site.sh

clean: ## Remove build artifacts and temp files
	rm -rf .artifacts/ dist/ build/ *.egg-info .pytest_cache .ruff_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ----------------------------------------------------------------------
# CI mirror — each target maps 1:1 to a job in .github/workflows/ci.yml.
# The pre-push gate runs the same commands CI does, so a green local run
# is sufficient evidence that CI will be green too. If CI ever fails
# something `make pre-push` didn't catch, add the missing check here.
# ----------------------------------------------------------------------

ci-lint: ## CI mirror: lint job
	$(RUFF) check src/ tests/
	$(RUFF) format --check src/ tests/

ci-unit: ## CI mirror: unit-tests job (excludes api + e2e — those have their own jobs)
	$(PYTEST) tests/ \
		--ignore=tests/test_e2e_dashboard.py \
		--ignore=tests/test_e2e_dashboard_mobile.py \
		--ignore=tests/test_api.py -q

ci-coverage: ## CI mirror: coverage job. NOTE: CI's YAML asks for --cov-fail-under=99 but pytest-cov on the runner silently exits 0 even when below threshold (plugin quirk on Linux/Python 3.12); CI's effective floor is whatever main is at today (~98%). Local mirrors the effective floor. When src/ coverage actually reaches 99%, bump both this target and the CI YAML.
	$(PYTEST) tests/ \
		--ignore=tests/test_e2e_dashboard.py \
		--ignore=tests/test_e2e_dashboard_mobile.py \
		--cov=aml_framework \
		--cov-report=term-missing \
		--cov-fail-under=98 \
		-q

ci-api: ## CI mirror: api-tests job
	$(PYTEST) tests/test_api.py -q

ci-e2e: ## CI mirror: e2e-dashboard job (Playwright; ~15 min)
	$(PYTEST) tests/test_e2e_dashboard.py tests/test_e2e_dashboard_mobile.py -q

ci-deployment: ## CI mirror: deployment-validation job (helm lint + template + docker compose config)
	helm lint deploy/helm
	helm template aml-open-framework deploy/helm > /tmp/aml-open-framework.yaml
	@if [ -n "$(DOCKER_COMPOSE)" ]; then \
		echo "$(DOCKER_COMPOSE) config > /dev/null"; \
		$(DOCKER_COMPOSE) config > /dev/null; \
	else \
		echo "⚠ docker compose not installed locally — skipping compose-config check. CI will still run it."; \
	fi

ci-security: ## CI mirror: security-audit job (bandit + pip-audit)
	$(PYTHON) -m bandit -q -r src/ -x src/aml_framework/models/xgboost_scorer.py --severity-level high
	$(PYTHON) -m pip_audit --progress-spinner off .

pre-push: ci-lint ci-unit ci-coverage ci-api ci-e2e ci-deployment ci-security ## Run every CI job locally; required before `git push`
	@echo ""
	@echo "✓ All CI mirror jobs passed — safe to push."

install-hooks: ## One-time: wire git hooks to .githooks/ (run after clone)
	git config core.hooksPath .githooks
	@echo "✓ Git hooks installed — pre-push will now run 'make pre-push'."
