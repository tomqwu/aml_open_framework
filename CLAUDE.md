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
  → dashboard/             45-page Streamlit web app
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
- **Graph mule-ring detection (#498):** the offline `aml detect-mule-rings` CLI runs deterministic union-find + density community detection over the customer identity-link graph (`resolved_entity_link` — shared phone/email/device/etc.), emitting a governed `mule_rings.json` (`engine/mule_ring.py`). Pure stdlib (no sklearn/networkx), NEVER in the engine run path. Advisory — a community lens surfaced on Network Explorer; an investigator confirms, nothing auto-escalates.
- **GenAI case copilot (#499):** a governed Case Copilot sidebar on the Case Investigation page (`dashboard/case_copilot.py`) reuses the existing assistant (`get_assistant` + AssistantContext/AssistantReply + the `ai_interactions.jsonl` audit) for case-scoped DRAFTS — summarize / typology / draft STR-SAR narrative / counterparty network / risk. Dashboard-only, NEVER the engine run path. SR-26-2 carve-out: human-reviewed DRAFT (no auto-disposition), audited as `ai_case_copilot_action` with backend/model + confidence, `program.ai_audit_log` gates PII transit. Pure context-builder + prompts are stdlib (unit-testable under `.[dev]`); streamlit is lazy-imported in the UI only.

- **Fraud↔AML cross-program case links (#523):** `_finalize_run` now materializes the `cases/linkage.py::find_linked_customers` output as a frozen, manifest-pinned **`case_links.jsonl`** — one JSON object per customer with open cases in BOTH the fraud domain and the AML domain (domain = `aml_priority: fraud` (or a fraud rule-id hint) vs anything else). Pure read over the run's own cases + the spec's rule-domain map — never changes alert counts, cases, or dispositions; always written (empty when nothing links), `customer_id` masked under `AML_PII_MASKING`. `examples/uk_app_fraud/aml.yaml` is the bundled demonstrator: its four APP rules carry `aml_priority: fraud` and a new AML-domain `rapid_outbound_dispersal` (POCA s.327 layering — ≥3 outbound CHAPS/Faster-Payments ≥£1,500 in 7d; keys on volume not distinct-payee count, which `aggregation_window` having can't express) rule fires on the planted mule **C0019** (3 extra deterministic dispersal legs appended at the end of `data/synthetic.py`'s planted section so no later txn_id shifts; txn anchor 1311→1314), so the mule is linked across domains. Under `AML_PII_MASKING` the `customer_id` is masked both top-level and token-masked inside every compound `*_case_ids` entry (mirrors `audit_pack._mask_compound_string`). Surfaced on the Case Investigation page's "Linked across domains" panel; the full-run `aml export` ZIP carries the artifact.
- **Defect-ticket lifecycle (#529, Pillar 2):** the minted `defect_log.jsonl` stays frozen (manifest-pinned), so post-run triage transitions go on an append-only **companion** `defect_lifecycle.jsonl` (`engine/defect_lifecycle.py`) written by the offline `aml defect-update <run-dir> <defect_id> --status acknowledged|resolved|closed --reviewer <id> [--resolution …]`. Mirrors `decisions.jsonl`'s append-only posture (open `"ab"`, one canonical-JSON line, never rewritten); event `timestamp` derives from the run's `manifest.json::as_of` (NOT wall-clock) for byte-stability; `resolved`/`closed` require a non-empty resolution; an unknown `defect_id` (not in the frozen log) is rejected so the companion can't drift. Offline / post-run — never on the engine run path. Closes North-Star Pillar 2 (Evidence as a product).
- **Expected `risk_tier` on active rules (#529, Pillars 4+5):** `Rule.risk_tier` (low/medium/high) stays an OPTIONAL pydantic field (a legacy spec without it still loads — additive contract, never a required field), but a new advisory validation pass (`spec/validation.py::validate_risk_tier_coverage`) makes it *expected* on every `active` rule: an active rule missing it is a WARN from `aml validate` and a hard ERROR under `aml validate --strict` (mirrors the runtime env-gating WARN-by-default / raise-under-strict posture). All 14 example specs now tier every active rule. Independent axis from `severity` (alert urgency) and `model_tier` (MRM cadence); already weighted into the advisory `priority_score`. Closes North-Star Pillars 4 (DQ + defect management) and 5 (risk-based controls).
- **Model-risk approval gate (#529, Pillar 7):** new optional `Rule.approval_status` (pending/approved/rejected, default `pending`) + `program.model_risk_monitoring.require_approval_before_prod` (default false). When the gate is opted in AND `program.environment == "prod"` AND `program.strict_environment_gating`, the runner BLOCKS any material-tier rule (`model_tier` medium/high — tier-1 `low` is never gated) whose `approval_status` is not `approved`, raising the same `EnvironmentGatingError` (now carrying an optional `reason`) the env-gate uses and recording an `approval_gate_check` event on `decisions.jsonl` (mirrors `environment_gate_check`). Gate predicates live in `engine/promotion.py` (`model_approval_gate_applies` / `is_rule_model_approved` / `model_approval_audit_event`). Disabled path (not opted in / not prod-strict / immaterial tier) emits nothing — byte-identical to the pre-#529 baseline. `approval_status` is excluded from `rule_version_hash` at its `pending` default so the schema bump doesn't churn existing rule versions. `examples/canadian_schedule_i_bank` is the demonstrator (its medium-tier `passthrough_funnel_scorer` ships `approval_status: approved`). Closes North-Star Pillar 7 (DS as governed augmentation).

- **AMLA RTS effectiveness telemetry (#528):** the offline `aml amla-effectiveness-report <spec> <run-dir>` CLI emits a frozen, deterministic `amla_effectiveness_report.json` (`metrics/amla_effectiveness.py::build_amla_effectiveness_report`) rolling a run into the alert→case→STR funnel + per-rule precision/recall (funnel REUSED from `metrics.outcomes.compute_outcomes`, never reinvented) + **AMLA RTS citation coverage** — which rules carry the three AMLR effectiveness citations (CDD **AMLR Art. 28(1)** CDD-information RTS, ongoing monitoring of the business relationship **AMLR Art. 26** (CDD measure Art. 20(1)(f)), targeted-financial-sanctions screening **AMLR Art. 20(1)(d)**; all AMLR = Reg (EU) 2024/1624, article numbers verified vs EUR-Lex 2026-06 — the original issue's Art. 19(9)/AMLD6 53(10) were wrong; all in `CITATION_URL_MAP`). Pure stdlib+pydantic, OFFLINE (post-run report like `aml model-inventory`, NEVER in the engine run path), deterministic (`generated_at` = manifest `as_of`, atomic write, `--markdown` MRC table). Derived only — STR *acceptance* is a regulator-feedback event the run doesn't record, so `str_acceptance` is reported `not_tracked`, never fabricated; per-rule `recall` stays `None` (needs the ground-truth positive population). `examples/eu_bank/aml.yaml` carries the citations; surfaced on Framework Alignment (page 8) as an EU-only "AMLA RTS coverage" tab via the streamlit-free `dashboard/frameworks.py::build_amla_rts_alignment` (✓ mapped / ∼ partial=cited-but-no-evidence / ✗ gap).

- **FinCEN Whistleblower internal-channel audit (#531):** the offline `aml whistleblower-audit <spec> <run-dir>` CLI (`engine/whistleblower_audit.py`) reads a finalized run's `manifest.json` + `decisions.jsonl` + `cases/` and rolls five governance signals into a frozen `whistleblower_audit_report.json`: `sar_backlog_exposure` (open alerts >30d with no genuinely-TERMINAL close-out — `closed`/`escalated_to_str`, the SAME set reused from `engine/sla.py::_TERMINAL_EVENTS` so an in-flight `escalated`/`manual_review` case still counts as backlog), `escalation_coverage_pct` (% of disposition decisions with a documented reviewer + rationale vs system-auto), `triage_time` (median + p95 alert→close-out days, derived from ledger `case_opened.ts`→terminal `.ts`, with `resolution_hours` only as a fallback when both timestamps aren't present), `board_documented_decisions` (decisions tied to a board-report event — **not-tracked** when no board markers exist), and `ledger_integrity` (`AuditLedger.verify_decisions()`). `--markdown` emits a board-report pipe table; `--format nprm-gap` emits a ✓/⚠/✗ readiness table against the NPRM's proposed expectations. Pure stdlib+pydantic, deterministic (`generated_at` = run's `as_of`; FAILS CLOSED with a non-zero exit if the manifest lacks `as_of` rather than inventing a `datetime.now()`), OFFLINE — NEVER in the engine run path, never blocks/changes a run. A signal a run doesn't record is reported 0/not-tracked, never fabricated. Source: Federal Register 2026-06271 (FinCEN Whistleblower Incentives and Protections NPRM).

### Data Flow

- `data/synthetic.py` generates deterministic test data: 100 customers / 1,314 txns by default (v0.1.16 re-base + 3 #523 C0019 layering legs). Planted positives C0001–C0029 (per-spec typologies) plus a scale-up replica band on C0030–C0059 (the six core community-bank typologies; replica slots are stripped of incidental noise so each carries only its planted shape). Planted bands (C0001–C0059) are the **labelled** ground-truth positives (pin seed 42); the remaining customers are **unlabelled realistic background** — NOT a zero-alert guarantee. At the scaled volume some background activity coincidentally trips a tight rule shape even at seed 42 (by design — that's the realistic false-positive surface FP-analysis/tuning/backtest exist for; the engine never assumes planted-exclusivity). This is an intentional global re-base: the `≥60` guard gates only the replica band, while the new defaults + a universal ≥90-day onboarding floor apply to all calls (explicit-arg callers keep the same txn *count* but customer rows still re-base via the floor — fine, since determinism tests are self-consistency and no test pins exact onboarded_at).
- `data/sources.py` resolves data sources: synthetic, CSV, Parquet, DuckDB, S3, GCS, Snowflake, BigQuery.
- `data/input/` has sample CSVs (1,311 txns, 100 customers) for immediate testing.

### Dashboard

45 Streamlit pages across 8 categories (43 operational + 2 navigation surfaces Start here/Today). Round 27 (2026-05-23) added 6 universally-routed surfaces: Decision Trail, Experiment Tracking, Threshold Sensitivity, Equivalence, Anomaly Discovery, Drift Monitor. Page 54 Regulatory Calendar (#511) is a universally-routed forward-deadline surface (live days-remaining + per-deadline spec-field readiness). Round 32 (2026-05-24) retired the in-app Knowledge category (the 10 pages 33–42 ported from the old GH-Pages site in PR-U2/U3) once the new MkDocs docs site at `tomqwu.github.io/aml_open_framework_docs/` shipped in Round 31 — content now lives in one canonical place; the dashboard sidebar carries two external links (Research & whitepapers · How-to recipes) pointing to the docs site (`AML_DOCS_URL` env override). `state.py` runs the engine once, caches in `st.session_state`. `audience.py` maps personas to relevant pages. Sidebar audience selector hides non-relevant pages. Run History (page 15) and Comparative Analytics (page 19) call `aml_framework.api.db.list_runs()` directly with whatever env the dashboard pod sees; both the Helm chart (PR #271) and the Terraform Container Apps deploy now inject `DATABASE_URL` on the Postgres path so the dashboard and API read/write the same backend. Pinned by `TestHelmPostgresFirstPrecedence` and `test_database_url_injected_on_both_container_apps`.

### Specs

14 example specs across 6 jurisdictions: US (FinCEN/FATF/RTP-FedNow), CA (FINTRAC/OSFI), EU (EBA/AMLD6), UK (FCA/POCA/PSR), Cross-border (FATF R.16 crypto/VASP), AU (AUSTRAC Tranche 2 DNFBPs — lawyers/accountants/real-estate/precious-metals; SMR/TTR — Australia files Suspicious Matter Reports, not STRs) — plus two stablecoin-issuer specs (PPSI under the US FinCEN GENIUS Act, US jurisdiction not a separate one): the basic `genius_ppsi_issuer` (mint/burn, nested-VASP, sanctioned-wallet, rapid-redemption; SAR — #500) and the richer NPRM-grounded `genius_ppsi_stablecoin` (FR 2026-06963 — new 31 CFR Part 502 OFAC program, ISO 20022 fields, SAR/CTR filing-latency SLA, PPSI-specific GENIUS Act s.4 / NPRM citations not the MSB 1022 rules, six stablecoin typologies; SAR + the proposed PPSI currency-transaction report at proposed 31 CFR 1033.310 — #513).

## Python

- Python >=3.10, `from __future__ import annotations` throughout
- Pydantic v2 with `extra="forbid"` and `frozen=True`
- Ruff for lint/format, line length 100
- `src/` layout with setuptools
