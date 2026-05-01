# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Behavioral Guidelines

### 1. Think Before Coding

- State assumptions explicitly before implementing. If uncertain, ask.
- This is a compliance framework — incorrect behavior has regulatory consequences. When in doubt, halt and clarify rather than guess.
- If a spec change could break cross-reference integrity (rules → contracts, reports → metrics), say so before editing.

### 2. Simplicity First

- The spec YAML is the source of truth. Don't add logic to Python that belongs in the spec.
- No features beyond what was asked. No speculative abstractions.
- Dashboard pages are Streamlit scripts, not modules — keep them self-contained.
- Ask: "Would this survive a compliance audit?" If the answer requires explanation, simplify.

### 3. Surgical Changes

- Touch only what the task requires. Don't "improve" adjacent code.
- Match existing patterns: `_Base` models with `extra="forbid"`, `frozen=True`.
- Every changed line should trace to the user's request.
- If you notice unrelated issues, mention them — don't fix them silently.

### 4. Goal-Driven Execution

- Convert tasks into verifiable goals with test assertions.
- "Add a rule" → validate spec, run engine, assert alerts fire, verify audit trail.
- For multi-step tasks, state a brief plan before coding.

## Before Every Commit

```bash
ruff format src/ tests/                                          # auto-format
ruff check src/ tests/                                           # lint
pytest tests/ --ignore=tests/test_e2e_dashboard.py -q            # unit + API (~20s)
pytest tests/test_e2e_dashboard.py -q                            # Playwright (~2min, run before PR)
```

Never push without all tests passing locally. CI runs 5 jobs: lint, unit-tests, api-tests, e2e-dashboard, docker-build.

## Project-Specific Rules

- **Lazy imports**: Dashboard modules (audience.py, data_layer.py, pages/) must NOT import `streamlit` at module level. Unit-test CI only installs `.[dev]`.
- **Skip guards**: Tests needing `jwt`, `fastapi`, or `streamlit` must use `pytest.mark.skipif`.
- **Spec + schema sync**: When changing the spec shape, update both `schema/aml-spec.schema.json` AND `spec/models.py`.
- **Every new feature needs**: tests, screenshots (if UI), README section, CLAUDE.md update if architecture changes.

## Commands

```bash
pip install -e ".[dev,dashboard,api]"           # install everything
make help                                        # show all 15+ make targets
make test                                        # unit + API tests
make demo                                        # validate → run → launch dashboard
aml validate examples/canadian_schedule_i_bank/aml.yaml
aml run examples/canadian_schedule_i_bank/aml.yaml --seed 42
aml validate-data examples/canadian_schedule_i_bank/aml.yaml data/input/
aml dashboard examples/canadian_schedule_i_bank/aml.yaml
aml api --port 8000                              # REST API at /docs
```

## Architecture

```
aml.yaml (spec)
  → spec/loader.py        JSON Schema + Pydantic validation
  → generators/            SQL, DAG stubs, control matrix, STR narratives
  → engine/runner.py       Execute rules on in-memory DuckDB
  → metrics/engine.py      Compute metrics → RAG bands
  → engine/audit.py        Immutable evidence ledger (SHA-256 hash chain)
  → export.py              Regulator-ready ZIP bundle
  → dashboard/             21-page Streamlit web app
  → api/                   FastAPI REST layer with JWT/OIDC auth
```

### Key Design Decisions

- **Two-layer validation**: JSON Schema (structural) → Pydantic (cross-reference integrity).
- **DuckDB in-memory**: Tables named by `data_contract.id`. Portable, deterministic.
- **Discriminated union for rules**: `RuleLogic` with `discriminator="type"` — 4 types: `aggregation_window`, `custom_sql`, `python_ref`, `list_match`. All execute in the reference engine.
- **Deterministic runs**: Same spec + same data + same seed = identical output hashes. Tested by `test_run_is_reproducible`.
- **Custom SQL templates**: Placeholders `{as_of}`, `{window_start}`, `{recent_start}`, `{baseline_start}`, `{dormant_cutoff}` auto-substituted.
- **Audit hash chain**: `decisions.jsonl` is append-only. Each line hashed with previous hash. `AuditLedger.verify_decisions()` detects tampering.

### Data Flow

- `data/synthetic.py` generates deterministic test data with planted positives (C0001–C0009).
- `data/sources.py` resolves data sources: synthetic, CSV, Parquet, DuckDB, S3, GCS, Snowflake, BigQuery.
- `data/input/` has sample CSVs (438 txns, 25 customers) for immediate testing.

### Dashboard

29 Streamlit pages (plus 2 navigation surfaces — Welcome + Today). `state.py` runs the engine once, caches in `st.session_state`. `audience.py` maps personas to relevant pages. Sidebar audience selector hides non-relevant pages.

### Specs

10 example specs across 5 jurisdictions: US (FinCEN/FATF/RTP-FedNow), CA (FINTRAC/OSFI), EU (EBA/AMLD6), UK (FCA/POCA/PSR), Cross-border (FATF R.16 crypto/VASP).

## Python

- Python >=3.10, `from __future__ import annotations` throughout
- Pydantic v2 with `extra="forbid"` and `frozen=True`
- Ruff for lint/format, line length 100
- `src/` layout with setuptools
