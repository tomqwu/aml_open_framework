.PHONY: install test test-coverage test-all test-e2e lint run dashboard api docker clean help demo

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install with all optional dependencies
	pip install -e ".[dev,dashboard,api]"

test: ## Run unit + API tests (fast, no browser)
	pytest tests/ \
		--ignore=tests/test_e2e_dashboard.py \
		--ignore=tests/test_e2e_dashboard_mobile.py -q

test-coverage: ## Run non-browser tests with the configured coverage gate
	pytest tests/ \
		--ignore=tests/test_e2e_dashboard.py \
		--ignore=tests/test_e2e_dashboard_mobile.py \
		--cov=aml_framework \
		--cov-report=term-missing \
		--cov-fail-under=89 \
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

clean: ## Remove build artifacts and temp files
	rm -rf .artifacts/ dist/ build/ *.egg-info .pytest_cache .ruff_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
