# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project does not
yet use semantic version tags, so entries are grouped by merge date and the PR
that introduced them.

## [Unreleased]

### Security
- **Cross-tenant API isolation** (`api/db.py`, `api/main.py`): every read
  endpoint now scopes by the JWT's `tenant` claim. `list_runs`, `get_run`,
  `get_run_alerts`, `get_run_metrics`, `get_reports`, `get_alerts_cef`
  accept an optional `tenant_id` and filter (or JOIN through `runs`) on
  it. `store_run` persists the tenant. The Postgres schema gains a
  `tenant_id TEXT` column to match SQLite. Tokens were tenant-aware at
  issuance but not enforcement; this closes that gap.
- 3 new tests under `TestTenantIsolation` confirm `bank_a` can't list,
  get, or read alerts for `bank_b`'s runs.
- **Webhook HMAC signing** (`api/main.py`): `WebhookConfig.secret` is now an
  optional field. When provided at registration, the dispatch path computes
  `HMAC-SHA256(secret, body)` and sends it as `X-AML-Signature: sha256=<hex>`
  alongside the JSON payload. Receivers verify by recomputing the HMAC over
  the raw body and comparing constant-time. Same wire convention as Stripe /
  GitHub webhooks. Hooks without a secret continue to work unsigned.
- 4 new tests under `TestWebhookSigning` cover registration response
  shape, the `_sign_webhook` helper matching stdlib `hmac`, and the
  signature header being set on outgoing requests.
- **Audit-ledger snapshot is read-only after finalize** (`engine/audit.py`):
  `manifest.json`, `input_manifest.json`, `spec_snapshot.yaml`,
  `alerts/*.jsonl`, `alerts/*.hash`, and `rules/*.sql` are `chmod 0o444`-ed
  once the runner finishes writing. Accidental rewrites and most malicious
  processes (running as the engine user) now fail loudly. `decisions.jsonl`
  is intentionally left writable so dashboard human decisions can append.
  No-op on Windows (uses ACLs differently). Documented as advisory — for
  real WORM, point `artifacts_root` at a hardware-WORM mount.
- 4 new tests under `TestAuditLedgerFrozen` confirm the snapshot is
  read-only, that direct writes raise `PermissionError`, and that
  `decisions.jsonl` stays append-capable.

### Tests
- **`TestWindowDST` documents engine timezone semantics**: `parse_window` is
  calendar-blind by design; `as_of` and `booked_at` are naive datetimes in
  the same timezone (UTC by convention). Three new tests assert the
  invariants — `parse_window("24h") == parse_window("1d")`,
  `parse_window` is idempotent, and a 24h-window rule still aggregates
  correctly across the US spring-forward DST instant. Closes the quality
  review's flagged untested area.

### Refactor
- **Dashboard pages now use `Event` / `Queue` constants** (`pages/3_Alert_Queue.py`,
  `pages/4_Case_Investigation.py`): the bulk-action and per-case action
  buttons that write to `decisions.jsonl` (and the `isin([...])` filters that
  drive the open-case view) reference the `engine.constants` enums instead
  of inline string literals. Closes the original review's smell about
  audit-log strings drifting between the engine and UI writers.
- **`engine/constants.py` — single source of truth for event + queue names.**
  String literals like `"case_opened"`, `"escalated_to_str"`,
  `"closed_no_action"` were duplicated across `runner.py`, dashboard pages,
  and metrics dispatch. They're now `Event.CASE_OPENED`, `Queue.STR_FILING`,
  etc. Decisions written to the audit log are forever — a typo in one place
  used to silently drift; importing the constant now catches the change at
  type-check time.
- 3 new tests under `TestEngineConstants` freeze the literal values (so
  renames are explicit decisions, not silent breaks of past audit logs)
  and confirm a real run emits the canonical strings.

### Refactor (later)
- **`api/db.py` Postgres/SQLite dedup**: `_with_conn()` context manager
  yields a thin wrapper that translates `?` placeholders to `%s` for
  psycopg2 on the fly. Each public CRUD function now writes its query
  once instead of carrying two near-identical SQL bodies. ~50 LOC removed.
  No public API changes; existing Postgres mock tests pass unchanged.
- **`data/synthetic.py` `_make_txn` helper**: extracted from eight near-
  identical planted-positive blocks. Each used to be 7-8 lines of dict
  literal repeating the same keys (`txn_id`, `customer_id`, `amount`,
  `currency`, `channel`, `direction`, `booked_at`); call sites are now a
  single `_make_txn(tid, customer, amount, booked_at, channel=..., ...)`
  invocation. Output is byte-identical — the existing
  `test_run_is_reproducible` test verifies this.

### Changed
- **`list_match` fuzzy matcher upgrade** (`engine/runner.py`): the previous
  token-overlap matcher missed common sanctions-screening edge cases —
  diacritics (`Müller` vs `Mueller`), edit-distance differences (`VOLKOV`
  vs `VOLKOVA`, `JON` vs `JOHN`), and substring suffixes. The new matcher
  ASCII-folds accents via `unicodedata.NFKD`, scores each entry by
  `max(token_overlap, SequenceMatcher.ratio)`, and returns the
  highest-scoring match above threshold. No new dependency — pure stdlib.
- 9 new tests under `TestFuzzyMatcher` cover accents, typos, suffixes,
  transposed tokens, the genuinely-different-name negative case, and the
  best-of-many tie-break.
- **`python_ref` error boundary** (`engine/runner.py`): a scorer that raises
  (missing module, missing attribute, runtime exception inside the model)
  no longer aborts the whole run mid-write. The engine logs the exception,
  records zero alerts for that rule, appends a `rule_failed` decision event
  with the error class + message, and continues with the remaining rules.
  The audit ledger now reflects which rules failed instead of being left
  partially written. Spec-level violations (allow-list miss) still raise —
  those indicate a bad spec, not a runtime fault.
- **Rate-limiter eviction + Retry-After** (`api/main.py`): the in-memory
  `_request_counts` dict no longer grows unbounded under IP-rotation
  attacks — empty windows are deleted, and a global cap (configurable via
  `API_RATE_LIMIT_MAX_IPS`, default 10000) evicts the IPs with the oldest
  activity when exceeded. 429 responses now include a `Retry-After`
  header pointing to when the oldest tracked request leaves the window.

### Refactor
- **`metrics/engine._compute_sql_proxy` split** — the 110-line keyword-dispatch
  is now six named handler functions (`_proxy_repeat_alert`,
  `_proxy_filing_latency`, `_proxy_lctr_completeness`, `_proxy_edd_review`,
  `_proxy_sla_compliance`, `_proxy_avg_resolution`) routed by a small
  `_PROXY_DISPATCH` table. Each handler is independently readable and
  reviewable. The dispatch table preserves the original first-match-wins
  ordering so behaviour is unchanged.
- Extract `_resolve_run_dir` in `cli.py` — the "default to latest run-* under
  artifacts" block was duplicated in `report`, `export`, and `export-alerts`.
- Dashboard `Rule_Tuning` page now calls `engine.runner._build_warehouse`
  twice instead of re-implementing the DDL+insert loop inline. Removes ~50
  lines and an unintentional closure-over-`dtype` in the sensitivity loop
  (the second copy referenced `dtype` from outer scope, which would crash
  if every contract had `rows = []`).

### Tests
- **`TestThresholdBoundaries`** in `test_engine.py` adds nine just-below-
  threshold cases for the Canadian Schedule I spec: structuring (count<3,
  sum<20k, amounts outside the [5k–9999] filter), large_cash_lctr
  (sum<10k), and high_risk_jurisdiction (safe country, sum<5k). Three
  positive controls confirm the rules still fire when thresholds are met.
  False-positive containment is now exercised, not just coverage %.

### Security
- **Webhook SSRF blocked** (`api/main.py`): `_validate_webhook_url` resolves
  every registered URL and rejects private (RFC 1918), loopback, link-local
  (169.254/16, including the 169.254.169.254 cloud-metadata endpoint),
  multicast, and reserved addresses. Re-validates at fire time so DNS
  rebinding between registration and dispatch is contained. Bypass with
  `WEBHOOK_ALLOW_PRIVATE=1` for local dev.
- **DuckDB lockdown** (`engine/runner.py:_harden_duckdb`): every engine
  connection sets `enable_external_access=false`,
  `autoload_known_extensions=false`, `autoinstall_known_extensions=false`,
  `allow_unsigned_extensions=false`. A malicious `custom_sql` rule can no
  longer `INSTALL httpfs`, `ATTACH 'http://...'`, or `COPY TO '/tmp/exfil'`.
- **`python_ref` module allow-list** (`engine/runner.py`): callables must live
  under `aml_framework.models.` by default; `AML_PYTHON_REF_PREFIX` extends
  the list (comma-separated) for institution-specific scorer packages. A
  spec with `callable: os:getcwd` is now rejected before import.
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

### Changed
- **Audit-ledger determinism** (`engine/audit.py`): engine-time decisions now
  stamp `ts` from `as_of` (or an explicit per-decision time like the simulated
  resolution time) instead of wall-clock `datetime.now()`. The hash chain over
  `decisions.jsonl` is now reproducible — re-running with the same spec, data,
  and `as_of` produces an identical `decisions_hash`.
- **`AuditLedger.append_to_run_dir`** is the single canonical entry point for
  human-time decision writes. Both dashboard pages (`Alert_Queue`,
  `Case_Investigation`) now route through it instead of opening
  `decisions.jsonl` directly with drifted shapes.
- **`AuditLedger.verify_decisions`** accepts an optional `expected_hash` for
  out-of-band tamper detection. The default behaviour (read the hash from the
  same `manifest.json` that lives next to `decisions.jsonl`) is documented as
  weaker, with the recommended path explicitly called out.

### Tests
- `test_run_is_reproducible` now asserts equality of `decisions_hash`,
  `spec_content_hash`, and the full `inputs` manifest across re-runs.
- New `TestAuditLedgerDeterminism` covers `append_to_run_dir` and the
  external-hash path through `verify_decisions`.

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
