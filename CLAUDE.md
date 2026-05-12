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

The repo's `Makefile` has a `pre-push` umbrella target that runs the
**exact same commands every CI job runs**. Use it. There is also a git
`pre-push` hook in `.githooks/` that invokes `make pre-push`
automatically — enable it once per clone:

```bash
make install-hooks      # one-time: git config core.hooksPath .githooks
```

After that, every `git push` first runs `make pre-push`, which is:

```bash
make ci-lint ci-unit ci-coverage ci-api ci-e2e ci-deployment ci-security
```

Each `ci-*` sub-target maps 1:1 to a job in `.github/workflows/ci.yml`:

| Make target        | CI job                | Notes                                  |
|--------------------|-----------------------|----------------------------------------|
| `ci-lint`          | lint                  | `ruff check` + `ruff format --check`   |
| `ci-unit`          | unit-tests            | excludes `test_api.py` + e2e           |
| `ci-coverage`      | coverage              | `--cov-fail-under=99` (matches CI)     |
| `ci-api`           | api-tests             | `pytest tests/test_api.py`             |
| `ci-e2e`           | e2e-dashboard         | Playwright, ~15 min                    |
| `ci-deployment`    | deployment-validation | `helm lint` + template + compose config|
| `ci-security`      | security-audit        | `bandit` + `pip-audit`                 |

**The PR is the last gate, not a feedback loop.** If something fails on
CI that `make pre-push` didn't catch, that's a gap in `make pre-push`
— fix the gap. Don't push broken code expecting CI to find it.

The hook can be bypassed with `git push --no-verify`, but only for
pure-WIP pushes you don't intend to merge.

## PR Workflow With Codex Review

This repository uses local Codex review through `openai/codex-plugin-cc`.

Before shipping or merging a PR, run Codex review from Claude Code:

/codex:review --base main

For larger changes, prefer background review:

/codex:review --base main --background
/codex:status
/codex:result

Do not self-approve by posting `LGTM` markers.
Do not require or wait for the old GitHub `codex-pr-review-gate` check.

A PR may merge only when:
1. CI is green.
2. GitHub says the PR is mergeable.
3. Codex local review reports no blocking issues.
4. There are no unresolved review comments or merge conflicts.

If Codex review reports blockers:
1. Keep the PR open.
2. Fix the issues.
3. Run relevant local checks.
4. Push a follow-up commit.
5. Run Codex review again.

If the PR has merge conflicts:
1. Update the branch against the latest base branch.
2. Resolve conflicts carefully.
3. Run relevant local checks.
4. Push the resolution.
5. Run Codex review again.

If CI passes and Codex review passes:
- Merge the PR using the repository's normal merge method.
- Do not manually close the PR as the success path.

If GitHub blocks the merge:
- Report the exact blocker.
- Leave the PR open.

Only close without merging if the work is abandoned, duplicated, or superseded,
and leave a PR comment explaining why.

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
  → dashboard/             32-page Streamlit web app
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

32 Streamlit pages across 8 categories. `state.py` runs the engine once, caches in `st.session_state`. `audience.py` maps personas to relevant pages. Sidebar audience selector hides non-relevant pages. Run History (page 15) and Comparative Analytics (page 19) call `aml_framework.api.db.list_runs()` directly with whatever env the dashboard pod sees; both the Helm chart (PR #271) and the Terraform Container Apps deploy now inject `DATABASE_URL` on the Postgres path so the dashboard and API read/write the same backend. Pinned by `TestHelmPostgresFirstPrecedence` and `test_database_url_injected_on_both_container_apps`.

### Specs

10 example specs across 5 jurisdictions: US (FinCEN/FATF/RTP-FedNow), CA (FINTRAC/OSFI), EU (EBA/AMLD6), UK (FCA/POCA/PSR), Cross-border (FATF R.16 crypto/VASP).

## Python

- Python >=3.10, `from __future__ import annotations` throughout
- Pydantic v2 with `extra="forbid"` and `frozen=True`
- Ruff for lint/format, line length 100
- `src/` layout with setuptools
