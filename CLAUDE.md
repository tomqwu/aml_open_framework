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
- For multi-step tasks, outline your approach inline in 1-2 sentences as prose, then proceed directly to implementation. Do not call exit_plan_mode.

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
| `ci-coverage`      | coverage              | floor in `pyproject` enforced by `scripts/check_coverage_floor.py` |
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
- **Every new feature needs**:
  - **Tests** — unit, plus e2e/integration where applicable
  - **Screenshots** — if the feature has a UI
  - **Docs updates on every affected surface**:
    - `README.md` — top-level command, env var, deploy step, persona-facing feature
    - `CLAUDE.md` (this file) — architecture, conventions, or invariants
    - `docs/dashboard-tour.md` — new dashboard page (`test_dashboard_tour_coverage.py` enforces page-count + per-page mention)
    - `docs/spec-reference.md` — new spec field
    - `docs/api-reference.md` — new REST endpoint
    - `docs/how-to/<name>.md` — new task-oriented recipe; new CLI command must appear in README OR getting-started OR a how-to (`tests/test_docs_cli_coverage.py` enforces this)
    - `docs/progress.md` — Round-N entry after deploy
  - **PR body** — TODO checklist + closes #N + test plan
  - Enforced mechanically: see `feedback_every_change_needs_tests_and_docs.md` memory + the dashboard / docs-coverage tests above.

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
  → dashboard/             44-page Streamlit web app
  → api/                   FastAPI REST layer with JWT/OIDC auth
```

### Key Design Decisions

- **Two-layer validation**: JSON Schema (structural) → Pydantic (cross-reference integrity).
- **DuckDB in-memory**: Tables named by `data_contract.id`. Portable, deterministic.
- **Discriminated union for rules**: `RuleLogic` with `discriminator="type"` — 4 types: `aggregation_window`, `custom_sql`, `python_ref`, `list_match`. All execute in the reference engine.
- **Deterministic runs**: Same spec + same data + same seed = identical output hashes. Tested by `test_run_is_reproducible`.
- **Custom SQL templates**: Placeholders `{as_of}`, `{window_start}`, `{recent_start}`, `{baseline_start}`, `{dormant_cutoff}` auto-substituted.
- **Point-in-time joins (M4 / #484, Pillar 3)**: a `DataContract` may declare `effective_dated: {valid_from, valid_to}`; an `aggregation_window` rule's optional `enrich: {contract, key, where}` makes the SQL generator emit an as-of JOIN (`ref.valid_from <= booked_at < ref.valid_to`) inside the `filtered` CTE, so a rule resolves reference state contemporaneous with each txn, not the latest row. (`enrich.key`, not `on` — YAML 1.1 coerces a bare `on:` to boolean `true`.)
- **Equivalence divergence clustering (#494):** `engine/equivalence_clustering.py` groups an `EquivalenceReport`'s NEW_ONLY/LEGACY_ONLY cells by a deterministic shape signature `(classification, rule_id, severity, window_days)` — a triage lens, pure stdlib+pydantic, no sklearn (determinism + `.[dev]`-only unit CI forbid stochastic clustering). The four-way classification stays authoritative in the ledger; clusters are explanations surfaced in the `aml equivalence` markdown and on dashboard page 48.
- **Risk segmentation + governed suppression (#495):** optional `program.risk_segmentation` declares customer-risk segments + per-segment `deprioritize_below` thresholds; `engine/suppression.py` flags alerts in a low-risk segment whose advisory `priority_score` is below the threshold as `suppression.applied` — pure stdlib, deterministic, ADVISORY (never auto-closes; the rule alert stays in the ledger). Emits a frozen, PII-masked, manifest-pinned `suppression_report.json`; surfaced on Triage Queue + FP Analysis. Requires `program.prioritization` enabled (the score it gates on).
- **Model-risk monitoring (#497):** optional `program.model_risk_monitoring` makes the engine emit a frozen, manifest-pinned `model_risk_report.json` rolling the model inventory + per-rule count drift (current vs prior run, `drift_high_ratio`) + validation cadence (`engine/model_risk_monitoring.py`). Pure stdlib, deterministic (`generated_at` = ledger `as_of`), disabled path byte-identical. Advisory/monitoring only — never blocks a run or changes a model; SR 11-7 / OSFI E-23. Surfaced on the Drift Monitor page.
- **Typology auto-discovery (#496):** the offline `aml discover-typologies` CLI profiles a run's UNEXPLAINED customers (not caught by any rule), deterministically clusters high-anomaly customers by shape signature (stdlib z-score — no sklearn, NEVER in the engine run path — `engine/typology_discovery.py`), and emits `candidate_typologies.yaml` of proposed rule stubs (`status: pending_promotion`). Proposals only — human reviews + `aml typology-import`/edits the spec; nothing auto-promotes. Feeds the existing spec → validate → approval path.
- **Audit hash chain**: `decisions.jsonl` is append-only. Each line hashed with previous hash. `AuditLedger.verify_decisions()` detects tampering.

### Data Flow

- `data/synthetic.py` generates deterministic test data: 100 customers / ~1,311 txns by default (v0.1.16 re-base). Planted positives C0001–C0029 (per-spec typologies) plus a scale-up replica band on C0030–C0059 (the six core community-bank typologies; replica slots are stripped of incidental noise so each carries only its planted shape). Planted bands (C0001–C0059) are the **labelled** ground-truth positives (pin seed 42); the remaining customers are **unlabelled realistic background** — NOT a zero-alert guarantee. At the scaled volume some background activity coincidentally trips a tight rule shape even at seed 42 (by design — that's the realistic false-positive surface FP-analysis/tuning/backtest exist for; the engine never assumes planted-exclusivity). This is an intentional global re-base: the `≥60` guard gates only the replica band, while the new defaults + a universal ≥90-day onboarding floor apply to all calls (explicit-arg callers keep the same txn *count* but customer rows still re-base via the floor — fine, since determinism tests are self-consistency and no test pins exact onboarded_at).
- `data/sources.py` resolves data sources: synthetic, CSV, Parquet, DuckDB, S3, GCS, Snowflake, BigQuery.
- `data/input/` has sample CSVs (1,311 txns, 100 customers) for immediate testing.

### Dashboard

44 Streamlit pages across 8 categories (42 operational + 2 navigation surfaces Start here/Today). Round 27 (2026-05-23) added 6 universally-routed surfaces: Decision Trail, Experiment Tracking, Threshold Sensitivity, Equivalence, Anomaly Discovery, Drift Monitor. Round 32 (2026-05-24) retired the in-app Knowledge category (the 10 pages 33–42 ported from the old GH-Pages site in PR-U2/U3) once the new MkDocs docs site at `tomqwu.github.io/aml_open_framework_docs/` shipped in Round 31 — content now lives in one canonical place; the dashboard sidebar carries two external links (Research & whitepapers · How-to recipes) pointing to the docs site (`AML_DOCS_URL` env override). `state.py` runs the engine once, caches in `st.session_state`. `audience.py` maps personas to relevant pages. Sidebar audience selector hides non-relevant pages. Run History (page 15) and Comparative Analytics (page 19) call `aml_framework.api.db.list_runs()` directly with whatever env the dashboard pod sees; both the Helm chart (PR #271) and the Terraform Container Apps deploy now inject `DATABASE_URL` on the Postgres path so the dashboard and API read/write the same backend. Pinned by `TestHelmPostgresFirstPrecedence` and `test_database_url_injected_on_both_container_apps`.

### Specs

10 example specs across 5 jurisdictions: US (FinCEN/FATF/RTP-FedNow), CA (FINTRAC/OSFI), EU (EBA/AMLD6), UK (FCA/POCA/PSR), Cross-border (FATF R.16 crypto/VASP).

## Python

- Python >=3.10, `from __future__ import annotations` throughout
- Pydantic v2 with `extra="forbid"` and `frozen=True`
- Ruff for lint/format, line length 100
- `src/` layout with setuptools
