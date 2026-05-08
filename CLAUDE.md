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

## Builder agent — review gate, then merge

I am the builder / coding agent for this repo. I may **write code, push branches, open PRs, respond to PR feedback, and merge my own PR** — but only after the review gate passes. **Do not merge before the review gate passes.**

### After opening or updating a PR

1. Push the branch.
2. Wait for CI to finish.
3. Wait for independent review.
4. Treat "Not LGTM yet" as blocking feedback.

### A PR is mergeable only when ALL of these are true

1. The PR is **not draft**.
2. CI / checks are **green** — no failing, cancelled, skipped-required, or pending required checks.
3. An independent-reviewer comment says exactly:
   ```
   LGTM
   <!-- codex-pr-review: <head_sha> -->
   ```
4. The `<head_sha>` marker **exactly matches** the current PR head SHA.
5. No newer comment, review, or review thread after that LGTM contains blocking feedback.
6. No new commit was pushed after the LGTM marker.

### Polling cadence (every 2–5 minutes while waiting)

Check:
- PR head SHA (`gh pr view <PR> --json headRefOid`)
- CI / check status (`gh pr checks <PR>`)
- PR comments (`gh api repos/<OWNER>/<REPO>/issues/<PR>/comments`)
- PR reviews + inline review threads (`gh api repos/<OWNER>/<REPO>/pulls/<PR>/comments`)
- Whether the latest reviewer marker matches the current head SHA

### If reviewer says "Not LGTM yet"

1. Treat it as blocking feedback for that head SHA.
2. Fix the issue in code / tests / docs.
3. Run relevant local checks (ruff + pytest + terraform fmt/validate / helm lint as applicable).
4. Push a follow-up commit (this **invalidates** any prior LGTM).
5. Reply on the PR summarizing what changed and which finding each change addresses.
6. Wait for review on the new head SHA.

### If CI fails

1. Inspect the failing job / logs (`gh run view --job <id> --log`).
2. Fix the root cause.
3. Push a follow-up commit.
4. Wait for CI **and** re-review on the new head SHA.

### Before merging

Re-fetch PR state **immediately** with:
```bash
gh pr view <PR> --json number,url,isDraft,headRefName,headRefOid,mergeStateStatus,statusCheckRollup,comments,reviews
gh pr checks <PR>
```
Verify all 6 conditions still hold against the fresh state.

### Merge command

```bash
gh pr merge <PR> --squash --delete-branch
```
(Unless repo policy or branch protection mandates otherwise.)

### If GitHub blocks the merge

Report the exact blocker and leave the PR unmerged. Do **not** work around it.

### Don'ts

- Don't post `LGTM` yourself.
- Don't treat your own comments as review approval.
- Don't treat an LGTM for an older commit as valid.
- Don't merge with unresolved review threads, even with an LGTM.
- Don't argue with reviewer feedback unless it is technically wrong. If wrong, reply on the PR with concise reasoning and wait for the user / reviewer to resolve.
- Keep all review / fix discussion visible on the PR, not only in local chat.

This gate applies to every repo this assistant works in (including the landing zone), not just `aml_open_framework`.

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
