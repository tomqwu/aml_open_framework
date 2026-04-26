# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Spec-driven AML (Anti-Money Laundering) automation framework. A single `aml.yaml` file is the source of truth for data contracts, detection rules, case workflow, metrics, and regulator reporting. All runtime artifacts (SQL, DAG stubs, audit logs, reports, SAR exports) are generated from it.

## CI/CD & Testing Rules

All PRs to main run 5 CI jobs: lint, unit-tests, api-tests, e2e-dashboard (Playwright), docker-build.

**Before every commit/push, always run:**
```bash
ruff format src/ tests/                    # auto-format
ruff check src/ tests/                     # lint
pytest tests/ --ignore=tests/test_e2e_dashboard.py -q   # unit + API tests
```

**Before opening a PR, also run:**
```bash
pytest tests/test_e2e_dashboard.py -q      # Playwright browser tests
```

**Key rules:**
- Never push to main without all tests passing locally
- Dashboard code (audience.py, data_layer.py) must NOT import `streamlit` at module level — the unit-test CI job only installs `.[dev]`, not `.[dashboard]`. Use lazy imports inside functions.
- Tests that need `jwt`, `fastapi`, or `streamlit` must use `pytest.mark.skipif` guards
- Every new feature needs: tests, screenshots (if UI), README section, CLAUDE.md update

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run tests
pytest
pytest tests/test_runner.py                    # single file
pytest tests/test_runner.py::test_end_to_end_detects_planted_structurer  # single test

# Lint
ruff check src/ tests/
ruff format --check src/ tests/

# CLI commands (all take a spec path as first arg)
aml validate examples/community_bank/aml.yaml
aml generate examples/community_bank/aml.yaml
aml run examples/community_bank/aml.yaml --seed 42
aml report examples/community_bank/aml.yaml --audience svp --stdout
aml export examples/community_bank/aml.yaml

# Dashboard (requires dashboard extras)
pip install -e ".[dev,dashboard]"
aml dashboard examples/community_bank/aml.yaml       # launches on port 8501
aml dashboard examples/community_bank/aml.yaml --port 8502
```

## Architecture

### Spec-first pipeline

```
aml.yaml → spec/loader.py (JSON Schema + Pydantic validation)
         → generators/    (SQL, DAG stubs, control matrix, docs)
         → engine/runner.py (execute rules on in-memory DuckDB)
         → metrics/engine.py (compute metrics from run results)
         → metrics/reports.py (render audience-specific markdown reports)
         → engine/audit.py (immutable evidence ledger with hashes)
         → export.py (zip into regulator-ready bundle)
```

### Key design decisions

- **Two-layer spec validation**: `spec/loader.py` first validates against `schema/aml-spec.schema.json` (JSON Schema), then loads into Pydantic models (`spec/models.py`) which enforce cross-reference integrity (rules reference real data_contracts, escalate to real queues, report sections reference real metrics).
- **DuckDB as reference engine**: Rules execute against in-memory DuckDB tables named by `data_contract.id`, not the institution's warehouse layout. This keeps the engine portable.
- **Deterministic runs**: Every execution records `spec_version`, `input_hash`, `output_hash`, and `engine_version`. Two runs with the same inputs must produce identical output hashes (tested by `test_run_is_reproducible`).
- **Rule logic is a discriminated union**: `RuleLogic` in `spec/models.py` uses Pydantic's `discriminator="type"` — supports `aggregation_window`, `list_match`, `custom_sql`, and `python_ref`. Only `aggregation_window` and `custom_sql` are executable in the reference engine.
- **Metrics formula types**: Count, sum, ratio, coverage, and SQL formulas. Coverage and SQL formulas return 0.0 in the reference engine (forward-compatible stubs). Metrics feed RAG-banded audience reports.
- **Synthetic data**: `data/synthetic.py` generates deterministic test transactions with planted positives — C0001 (structuring), C0002 (rapid movement), C0003 (high-risk jurisdiction), C0004 (large cash CTR), C0005 (volume spike), C0006 (dormant reactivation).
- **Custom SQL templates**: `custom_sql` rules use `{as_of}`, `{window_start}`, `{recent_start}`, `{baseline_start}`, `{dormant_cutoff}` placeholders, auto-substituted by `generators/sql.py`.

### Spec schema

The canonical contract is `schema/aml-spec.schema.json`. The Pydantic models in `spec/models.py` mirror it with typed access. When changing the spec shape, update both.

### Artifacts layout

`aml run` writes to `.artifacts/run-<timestamp>/` containing:
- `rules/` — compiled SQL per rule
- `alerts/` — JSON alert sets per rule
- `cases/` — one JSON file per case
- `decisions.jsonl` — append-only decision log
- `metrics/metrics.json` — computed metric values
- `reports/` — rendered markdown per audience report
- `manifest.json` — full run metadata with hashes

### Dashboard (`dashboard/`)

Streamlit multi-page web app that runs the engine once on startup and caches results in `st.session_state`. 20 pages:
- Executive Dashboard, Program Maturity (spider chart), Alert Queue (with CSV export + bulk actions), Case Investigation (timeline + Sankey + STR generator), Rule Performance, Risk Assessment (heatmaps), Audit & Evidence (search + tamper detection), Framework Alignment (FATF/FinCEN/PCMLTFA/OSFI/AMLD6/Wolfsberg), Transformation Roadmap (Gantt), Network Explorer (temporal correlation graph), Live Monitor (spec-derived screening), Sanctions Screening (list_match results), Model Performance (python_ref analytics), Data Quality (contract validation), Run History (stored runs), Rule Tuning (threshold what-if), Customer 360 (single-customer deep-dive).
- `state.py` initializes session: `load_spec` → `generate_dataset` or CSV → `run_spec` → DataFrames.
- `data_layer.py` holds consulting content (maturity model, framework mappings for 4 jurisdictions, roadmap phases).
- `audience.py` defines per-persona page visibility (role-based filtering).
- `components.py` has shared UI helpers (KPI tiles, RAG badges, metric tables).
- Sidebar: audience filter (hides non-relevant pages), guided demo toggle.

## Python

- Python >=3.10, uses `from __future__ import annotations` throughout
- Pydantic v2 models with `extra="forbid"` and `frozen=True`
- Ruff for linting/formatting, line length 100
- `src/` layout with `setuptools`
