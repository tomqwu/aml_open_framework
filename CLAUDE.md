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

## Builder agent — GitHub-enforced review gate

I am the builder / coding agent for this repo. I may write code, push branches,
open PRs, respond to PR feedback, resolve merge conflicts, and merge my own PR
only after GitHub branch protection passes.

Do not merge before the review gate passes.

### After opening or updating a PR

1. Push the branch.
2. Wait for CI to finish.
3. Wait for the required `codex-pr-review-gate` check.
4. Treat `Not LGTM yet` as blocking feedback.

### A PR is mergeable only when ALL of these are true

1. The PR is not draft.
2. GitHub branch protection says the PR is mergeable.
3. Required CI checks are green.
4. The required `codex-pr-review-gate` check is green for the current head SHA.
5. There are no merge conflicts.
6. There is no newer blocking review feedback.

The `codex-pr-review-gate` check is the source of truth for Codex review
approval. Do not bypass it by reading old comments directly.

### If reviewer says `Not LGTM yet`

1. Treat it as blocking feedback.
2. Fix the issue in code / tests / docs.
3. Run relevant local checks.
4. Push a follow-up commit.
5. Reply on the PR summarizing what changed.
6. Wait for CI and `codex-pr-review-gate` again.

### If the PR has merge conflicts

1. Update the branch against the latest base branch.
2. Resolve conflicts carefully, preserving requested changes and current base
   behavior when possible.
3. Run relevant local checks.
4. Commit and push the resolution.
5. Wait for CI and `codex-pr-review-gate` again.

### Before merging

Re-fetch PR state immediately:

```bash
gh pr view <PR> --json number,url,isDraft,headRefName,headRefOid,mergeStateStatus,statusCheckRollup,comments,reviews
gh pr checks <PR>
```

Merge only if GitHub reports the PR is mergeable and every required check,
including `codex-pr-review-gate`, is passing for the current head SHA.

Preferred merge command:

```bash
gh pr merge <PR> --squash --delete-branch
```

If GitHub blocks the merge, report the exact blocker and leave the PR unmerged.
Do not work around branch protection.

### Don'ts

- Don't post `LGTM` yourself.
- Don't treat an old Codex approval as valid after pushing a new commit.
- Don't merge with unresolved review threads or merge conflicts.
- Keep review / fix discussion visible on the PR, not only in local chat.

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

32 Streamlit pages across 8 categories. `state.py` runs the engine once, caches in `st.session_state`. `audience.py` maps personas to relevant pages. Sidebar audience selector hides non-relevant pages.

### Specs

10 example specs across 5 jurisdictions: US (FinCEN/FATF/RTP-FedNow), CA (FINTRAC/OSFI), EU (EBA/AMLD6), UK (FCA/POCA/PSR), Cross-border (FATF R.16 crypto/VASP).

## Python

- Python >=3.10, `from __future__ import annotations` throughout
- Pydantic v2 with `extra="forbid"` and `frozen=True`
- Ruff for lint/format, line length 100
- `src/` layout with setuptools
