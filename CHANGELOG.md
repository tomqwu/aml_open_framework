# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project does not
yet use semantic version tags, so entries are grouped by merge date and the PR
that introduced them.

## [Unreleased]

### Security
- **JWT_SECRET hardening** (`api/auth.py`): refuse to import when the env var is
  set but shorter than 32 bytes; when unset, log a warning and use a per-process
  random secret (tokens do not survive a restart). Removes the hardcoded
  `aml-framework-dev-secret` fallback that previously let anyone with repo
  access forge tokens against a misconfigured deployment.
- **Path traversal** (`api/main.py`): `_safe_spec_path` resolves and verifies
  every API-supplied `spec_path` is inside the project root. `POST /runs`,
  `POST /validate`, and any future spec-loading endpoint reject `..`, absolute
  paths, and out-of-tree resolutions with `400`.
- **Validate endpoint info leak** (`api/main.py`): `POST /validate` no longer
  echoes the raw parser exception. Server logs the detail; the response is a
  generic message.
- **Role enforcement** (`api/main.py`): `POST /runs` and `POST /upload` now
  require `admin`/`manager`/`analyst`. `POST /webhooks` requires `admin`.
  Auditors are confirmed read-only by tests.
- **OIDC mode disables `/login`** (`api/main.py`): when `OIDC_ISSUER_URL` is
  set, the local-login endpoint returns 404 so demo credentials cannot be used.

### Documentation
- Refresh README test counts to match the 288-test suite across 9 files.
- Sync `docs/spec-reference.md` with the schema (rule `status` and `tags`,
  top-level `metrics` and `reports`).
- Add `CHANGELOG.md`, `docs/deployment.md`, `docs/api-reference.md`.
- Update repo-layout block to surface `docs/case-studies/`, `docs/pitch/`.
- README dashboard intro now says "21 purpose-built pages" (was 20).
- `CONTRIBUTING.md` checklist now requires a `CHANGELOG.md` entry per feature.

## 2026-04-26 — PR #17 (`feature/docs-screenshots-coverage`)

### Added
- Persona workflow screenshots (CCO, VP, Manager, Analyst, Auditor, Developer)
  under `docs/screenshots/workflows/`.
- README sections per persona with linked screenshots.
- Coverage tests for previously uncovered branches across the engine and API.

### Fixed
- README and CLAUDE.md page count drift (now 21 pages).

## 2026-04-25 — PR #16 (`feature/code-quality-and-new-features`)

### Added
- Refactored engine runner with `_open_cases_for_alerts` and `_finalize_run`
  helpers.
- Split dashboard `data_layer.py` (636 lines) into `maturity.py`,
  `frameworks.py`, `roadmap.py`.
- Test consolidation into 9 files: `test_api`, `test_engine`, `test_generators`,
  `test_spec`, `test_metrics`, `test_data_sources`, `test_integrations`,
  `test_performance`, `test_e2e_dashboard`.

### Fixed
- CI test references updated for consolidated test layout.
- Latin-1 encoding fallback for PDF export when reportlab is unavailable.

## 2026-04-24 — PR #15 (`feature/nice-to-haves`)

### Added
- SLA timers per case (countdown + breach detection).
- Narrative persistence on Case Investigation page.
- Data validator (`aml validate-data`) for CSV / Parquet inputs against the
  data contract.
- Case workflow polish: assigned-to filter, resolution code, soft-delete.

## 2026-04-23 — PR #14 (`feature/ux-production-readiness`)

### Added
- Docker Compose with PostgreSQL + API + Dashboard.
- API Swagger docs at `/docs`.
- One-command `make demo` target.
- Audit tamper verification (`aml verify` against decisions hash chain).
- `CONTRIBUTING.md`.

## 2026-04-22 — PRs #11–#13 (`feature/sprint-final`, `feature/final-gaps`, `feature/polish-round`)

### Added
- Spec Editor page with live YAML validation and interactive Rule Builder.
- API pagination + 600 req/min rate limiting (configurable).
- SSO/OIDC stub for downstream IdP integration.
- Adverse media screening rule template.
- OpenTelemetry instrumentation stub.
- Alert acknowledge / snooze actions.
- Typology Catalogue page (20+ template rules across 9 categories).
- Comparative Analytics page (run-over-run trend view).
- Email digest CLI for scheduled exports.

## 2026-04-21 — PRs #9–#10 (`feature/final-roadmap-items`, `feature/next-sprint`)

### Added
- UK / FCA spec (`examples/uk_bank/aml.yaml`) — POCA 2002, OFSI sanctions.
- S3 and GCS data source loaders.
- Audit ledger tamper detection (`AuditLedger.verify_decisions`).
- Customer 360 page.
- EU / AMLD6 spec (`examples/eu_bank/aml.yaml`) with PEP screening.
- Role-based page visibility via audience selector.
- Scheduled run runner (`aml schedule`).

## 2026-04-20 — PR #8 (`feature/complete-roadmap`)

### Added
- Helm chart for Kubernetes deployment (`deploy/helm/`).
- XGBoost scorer reference for `python_ref` rules.
- Snowflake / BigQuery warehouse connectors.
- Multi-tenant scaffolding and load tests.
- Coverage push to 99 % with 206 tests.

## 2026-04-19 — PR #7 (CI verification)

### Fixed
- CI: auto-format on push, Dockerfile build, Playwright stability.
- CI: `httpx` added to API extras (FastAPI TestClient requirement).
- CI: skip OIDC / RBAC tests when `jwt` is not installed.

## 2026-04-18 — initial AML framework merge

### Added
- Spec layer (`schema/aml-spec.schema.json`, `src/aml_framework/spec/`).
- Engine on DuckDB with 4 rule types: `aggregation_window`, `custom_sql`,
  `list_match`, `python_ref`.
- Generators: SQL, DAG stubs, control matrix, STR narratives.
- Metrics engine with RAG bands and audience-routed reports.
- 21-page Streamlit dashboard.
- FastAPI REST layer with JWT auth.
- Audit ledger with SHA-256 hash chain.
- Synthetic data generator with planted positives (C0001–C0009).
- TD Bank 2024 case study (`docs/case-studies/td-2024.md`).
- Five example specs across US, CA, EU, UK jurisdictions.
