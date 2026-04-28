# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project does not
yet use semantic version tags, so entries are grouped by merge date and the PR
that introduced them.

## [Unreleased]

### Changed
- **Persona workflow rebalance (Phase D)**
  (`dashboard/audience.py`, `tests/test_dashboard_workflows.py`,
  `docs/dashboard-tour.md`). Phase D of the dashboard workflow plan
  — fixes the muddled persona arcs the workflow audit flagged. Each
  persona now has a coherent task flow and no persona exceeds 8
  pages (the cognitive-load cap from the audit).
  - **Manager**: dropped Case Investigation (overlaps Investigations).
    Reordered to match daily arc: triage (Alert Queue) → investigate
    (Investigations / My Queue / Analyst Review Queue) → assess (Risk
    + Live Monitor) → tune (Tuning Lab). 8 → 7 pages.
  - **Developer**: added Spec Editor, Rule Tuning, Tuning Lab,
    Analyst Review Queue. Spec authoring + model performance + tuning
    is the actual dev workflow. 4 → 8 pages.
  - **PM**: added Risk Assessment + Case Investigation. PM needs both
    scope (Risk) + impact (specific case) when planning roadmap. 5 → 7.
  - **Director**: added Investigations (drill-down when KPIs spike).
    Tuning Lab dropped — Director consumes tuning *outcomes* via
    Comparative Analytics, doesn't tune themselves. 6 → 7.
  - **VP**: Tuning Lab dropped (same reasoning as Director). Added
    Comparative Analytics. 5 → 5.
  - **Auditor**: added Investigations + Case Investigation. Auditor
    reviews specific cases, not just aggregate evidence. 4 → 6.
  Also exposes a new `MAX_PAGES_PER_PERSONA = 8` constant + 3 new
  source-level tests in TestAudienceMapCoverage that pin the new
  assignments so future drift surfaces in CI:
  `test_no_persona_exceeds_page_cap`,
  `test_phase_d_persona_assignments`,
  `test_tuning_lab_only_for_tuners`. Tests 1107 → 1123 (+16 — Phase
  C contributed 17, Phase D contributed 3, one moved). Updated the
  Audience Filtering table in `docs/dashboard-tour.md` to match.

### Added
- **FINTRAC audit-pack download + VoP outcomes panel (Phase B-3)**
  (`dashboard/pages/7_Audit_Evidence.py`,
  `dashboard/pages/12_Sanctions_Screening.py`,
  `tests/test_dashboard_audit_pack_button.py`). Phase B-3 of the
  dashboard workflow plan — surfaces `generators/audit_pack.py`
  (Round-7 PR #78) and the PSD3 VoP vocabulary from
  `data/psd3/parser.py` (Round-7 PR #77) on the relevant
  pages. These were the last two Round-7 modules unreachable
  from the GUI; with this PR every shipped module has at least
  one dashboard entry point.
  **Page #7 Audit & Evidence** now ends with a **Pre-Examination
  Audit Pack** section. When the spec's jurisdiction is `CA`,
  loads cases + decisions from the run_dir then renders a
  **📥 FINTRAC Audit Pack (ZIP)** download button that calls
  `build_audit_pack(spec, cases, decisions, jurisdiction="CA-FINTRAC")`.
  Same 9-file deterministic ZIP the CLI `aml audit-pack` ships
  (program.md + inventory.json + alerts_summary.json +
  cases_summary.json + audit_trail_verification.json +
  sanctions_evidence.json + pcmltfa_section_map.md +
  osfi_b8_pillars.md + manifest.json). For non-CA jurisdictions
  shows an informative caption explaining the planned UK FCA /
  EU AMLA / US FinCEN templates rather than a non-functional
  button. Wrapped in try/except.
  **Page #12 Sanctions Screening** now ends with a **Verification
  of Payee outcomes (PSD3 / UK CoP)** section. When the txn frame
  carries a `confirmation_of_payee_status` column (populated by
  `data/psd3` ingestion or the UK CoP scheme), renders 5 KPI
  cards for the canonical PSD3 outcomes
  (`match` / `close_match` / `no_match` / `not_checked` /
  `outside_scope`) plus a fallback table that captures
  non-canonical buckets (`not_set` for unscreened txns,
  institution-specific extensions). Same vocabulary covers
  EU PSD3 VoP and UK Confirmation of Payee — one txn column,
  two regulators. When the column is missing, shows guidance
  on how to populate it (via `data/psd3` adapter or by extending
  the txn data contract) instead of an empty table.
  11 source-level tests under `TestAuditPackButton` +
  `TestVoPOutcomes` guard against drift (import presence,
  jurisdiction gating, 5-outcome KPI rendering, missing-column
  + empty-frame defenses, try/except wrapping). Tests
  1102 → 1113 (+11). With this PR, **every Round-6/7 module
  is reachable from the dashboard** — the original goal of
  Phase B is met.

- **Live SLA + STR-bundle download on case-facing pages (Phase B-1)**
  (`dashboard/pages/4_Case_Investigation.py`,
  `dashboard/pages/21_My_Queue.py`,
  `dashboard/pages/17_Customer_360.py`,
  `tests/test_dashboard_sla_integration.py`). Phase B-1 of the
  dashboard workflow plan — surfaces `cases/sla.py` and
  `cases/str_bundle.py` (Round-6 modules) on the three pages
  analysts spend most of their time on. Previously these modules
  were only reachable via CLI or the Investigations page (#24).
  **Page #4 Case Investigation** now shows three new affordances
  in a row right after the case header:
  - **SLA timer** — live `compute_sla_status(case, queue, as_of)`
    with band color (green > 50% remaining, amber 10-50%, red
    < 10%, breached ≤ 0%) + remaining hours + due timestamp.
  - **Escalation recommendation** — when SLA has breached, calls
    `apply_escalation(case, status, queue)` and surfaces the
    suggested next queue + reason. Operator sees "→ l2_investigator
    · sla breach" without leaving the page.
  - **📥 STR submission ZIP** download button — wraps the single
    case via `aggregate_investigations([case], strategy="per_case")`
    then calls `bundle_investigation_to_str()`. Same deterministic
    ZIP shape (narrative.txt + goAML XML + Mermaid network
    diagrams + manifest.json with file-by-file SHA-256) the
    Investigations page produces. Wrapped in try/except so a
    bundle-gen failure shows a caption instead of crashing the page.
  Page also gains deep-link support: `consume_param("case_id")`
  pre-selects a case when arrived via `?case_id=...` from Alert
  Queue / Customer 360 / Investigations (Phase C will add the
  outbound links). Replaces inline `sev_colors` dict + ad-hoc
  `st.warning + st.stop` with the Phase A `severity_color()` and
  `empty_state()` helpers.
  **Page #21 My Queue** now adds two columns (`sla_state`,
  `sla_remaining`) to the open-cases table, computed live from
  `compute_sla_status()` per row. Caption documents the band
  thresholds so analysts learn them once.
  **Page #17 Customer 360** cases table gains an `sla_state`
  column with the same per-case computation + a caption pointing
  toward the Phase C deep-link drill-down.
  18 source-level tests under `TestCaseInvestigationSLA`,
  `TestMyQueueSLA`, `TestCustomer360SLA`, `TestCrossPageConsistency`
  guard against drift (helper imports, no inline band-classification
  reimplementation, no inline severity dicts). Total tests
  1089 → 1107.
- **Effectiveness funnel + regulation drift on dashboard (Phase B-2)**
  (`dashboard/pages/1_Executive_Dashboard.py`,
  `dashboard/pages/7_Audit_Evidence.py`,
  `tests/test_dashboard_outcomes_panel.py`). Phase B-2 of the
  dashboard workflow plan — surfaces `metrics/outcomes.py`
  (Round-7 PR #75) on the Executive Dashboard for SVP/CCO
  consumption + `compliance/regwatch.py` (Round-7 PR #74) on
  Audit & Evidence for auditor review.
  **Page #1 Executive Dashboard** now ends with an
  **Effectiveness Funnel** section: 4 KPI cards (Alerts / Cases /
  STR filed / Alert→STR%) + per-rule funnel breakdown table
  (alerts / cases / str_filed / closed / pending / SLA-breach % /
  precision-when-labeled) + **📥 AMLA RTS JSON download** button.
  Same numbers FinCEN's April 2026 NPRM and AMLA's RTS
  (due 2026-07-10) treat as the canonical effectiveness measure.
  For production submission with LEI / reporting period the CLI
  `aml outcomes-pack` is still the right tool; the dashboard
  download serves the demo + ad-hoc preview path.
  **Page #7 Audit & Evidence** now ends with a **Regulation
  Drift** section: 4 KPI cards (Citations / Resolvable URLs /
  In baseline / Baseline path) + per-citation table showing
  baseline-vs-current state. When no baseline exists, shows
  the exact `aml regwatch <spec> --update` command to capture
  one. The "why now" anchor (FinCEN BOI Mar 2025 narrowing) is
  preserved in code comments so the panel doesn't get
  accidentally removed by future maintainers.
  Both panels wrapped in try/except — a missing decisions.jsonl,
  schema mismatch, or absent module never crashes the page.
  13 source-level tests under `TestExecutiveFunnel`,
  `TestAuditEvidenceRegwatch`, `TestCrossPageInvariants`. Tests
  1089 → 1102 (+13).

- **Dashboard cross-cutting helpers (Phase A)**
  (`dashboard/components.py`, `dashboard/query_params.py`,
  `tests/test_dashboard_components_helpers.py`). First PR of the
  dashboard workflow + design plan. Adds the foundations every
  subsequent integration PR depends on:
  - **`severity_color(severity)`** — single-source-of-truth resolver
    over `SEVERITY_COLORS`. Replaces the `_sev_style` / inline color
    dicts duplicated in pages #4, #5, #12, #17, #21, #22 (cleanup
    happens in Phase E).
  - **`sla_band_color(state)`** — resolver over a new
    `SLA_BAND_COLORS` constant covering the four `cases/sla.py`
    states (green/amber/red/breached) plus `unknown` fallback. Used
    by the SLA timer ring + backlog tables Phase B-1 introduces.
  - **`empty_state(message, *, icon, detail, stop)`** — consistent
    empty-state block. Replaces the ad-hoc
    `st.warning(...) + st.stop()` patterns scattered across analyst
    pages so operators see the same shape every time.
  - **`link_to_page(page_path, label, **query_params)`** — Streamlit
    `st.page_link` wrapper that mirrors query params into
    `st.session_state["selected_<key>"]` so destination pages can
    pre-select (Streamlit's native page-link doesn't pass query
    params). Foundation for Phase C drill-downs.
  - **New `dashboard/query_params.py` module** with `read_param`,
    `set_param`, `consume_param`, `clear_param`. URL-first with
    session-state fallback so deep links work whether the user
    arrived via URL or in-app navigation. `consume_param` clears
    on read so refreshes don't re-trigger one-shot drill-down state;
    `clear_param` removes from both URL and session state for
    explicit retirement after the drill-down resolves into the
    page's canonical state.
  - 21 new source-level tests under `TestSeverityColorHelper`,
    `TestSLABandColorHelper`, `TestEmptyStateHelper`,
    `TestLinkToPageHelper`, `TestQueryParamsModule`,
    `TestNamespaceConsistency`. The cross-module test catches the
    silent-broken-deep-link failure mode where `link_to_page` and
    `query_params.read_param` could drift apart on the
    `selected_<key>` namespace convention.
  Total tests 1068 → 1089.

- **Progress snapshot + competitive positioning research** (`docs/progress.md`,
  `docs/research/2026-04-competitive-positioning.md`, `README.md`).
  Two new docs:
  - **`docs/progress.md`** — fact-based audit of what's shipped as of
    2026-04-27: 19,642 lines of source, 991 tests across 34 files,
    1,852 lines of documentation, 24 dashboard pages, 7 example
    specs across 4+ jurisdictions, 61+ unique regulation citations.
    Round-by-round delivery breakdown for Round 5 (payment rails)
    and Round 6 (case management). Module surface, regulatory
    coverage matrix, and a documented "what we won't ship"
    section (generative-AI rule authoring, native graph DB,
    in-tree alert-scoring ML).
  - **`docs/research/2026-04-competitive-positioning.md`** —
    deep-research-agent output positioning the framework against
    the 2026 commercial + OSS landscape. Three sections:
    competitive landscape (NICE Actimize, Hawk:AI, ComplyAdvantage,
    Quantexa, Marble, Jube, FINOS OpenAML), where the framework
    actually wins (deterministic rerun, ISO 20022 native, "every
    line written by a human" moat under SR 26-2), and top 5
    next features ranked by impact ÷ effort (regulatory-change
    diff watcher, AMLA STR/RTS effectiveness pack, TBML+APP-fraud
    spec pair, PSD3/VoP adapter, FINTRAC pre-exam audit pack)
    with "why now" anchored to AMLA July 2026 + FinCEN NPRM
    comment-period closing June 9 2026. ~30 cited sources.
  Both documents linked from the README documentation map.

- **AMLA STR/RTS effectiveness telemetry pack**
  (`metrics/outcomes.py`, `cli.py:outcomes_pack_cmd`,
  `tests/test_metrics_outcomes.py`). Round-7 PR #2 — second-ranked
  feature from the 2026-04 positioning research. AMLA's RTS due
  2026-07-10 + FinCEN's April 2026 NPRM both treat the
  alert→case→STR conversion ratio as the canonical effectiveness
  measure; the framework's existing per-rule alert counts didn't
  roll up into that funnel.
  New `compute_outcomes(cases, decisions, *, labels)` returns an
  `OutcomesReport` with: per-rule funnel counts, conversion ratios
  (alert→case, case→STR, alert→STR), SLA-breach rate, precision
  per rule when label data supplied. Pure functions over the
  engine's existing case + decision dicts — no new schema needed.
  New `format_amla_rts_json` renders the AMLA RTS draft 2026-02
  shape with deterministic `AMLA-<sha256[:16]>` submission id so
  retransmissions are idempotent. New `aml outcomes-pack` CLI
  takes the latest run dir, optionally loads `--labels` CSV, writes
  the JSON. Same shape works for AMLA submission + FinCEN narrative
  effectiveness pack.
  21 new tests under `TestComputeOutcomes`, `TestSLABreaches`,
  `TestLabelledPrecision`, `TestAMLARTSRenderer`,
  `TestEndToEndWithEngine`. Total tests 953 → 974.

- **Regulatory-change diff watcher** (`compliance/regwatch.py`,
  `compliance/__init__.py`, `cli.py:regwatch_cmd`,
  `spec/models.py`, `schema/aml-spec.schema.json`,
  `tests/test_compliance_regwatch.py`). Round-7 PR #1 — top-ranked
  feature from the 2026-04 deep-research-agent positioning report
  (impact/effort: HIGHEST). FinCEN BOI was silently narrowed in
  March 2025 — the canonical example of regulator pages changing
  without redirect, leaving every downstream spec citation stale.
  No commercial vendor ships drift detection because they own
  the rule library themselves; the framework needs it precisely
  because it doesn't.
  New `aml regwatch <spec>` CLI command with three modes:
  - **default** — fetch every cited URL, hash content, compare to
    `.regwatch.json` baseline, exit 1 on any drift/unreachable/new/
    removed finding. Suitable for cron / weekly CI.
  - **`--update`** — write current state as new baseline (after
    operator acknowledges drift in a manual review).
  - **`--offline`** — skip network, only verify baseline file's
    internal consistency. Air-gapped envs + CI smoke tests.
  Cosmetic-edit guard: hashes the *normalized* content (collapsed
  whitespace, stripped script/style tags, stripped HTML comments,
  lowercased text) so trivial template tweaks don't false-positive.
  Built-in citation→URL resolver covers 28 common citations across
  US (FinCEN, OFAC, eCFR), Canada (PCMLTFA, FINTRAC), EU (AMLD6,
  EU regulations, transfer-of-funds), and FATF (R.16, R.19,
  Cyber-Enabled Fraud). Operators with novel citations add a
  `url:` field to the spec's `regulation_refs` entry — the new
  optional field is added to both Pydantic model + JSON Schema.
  Pure stdlib HTTP (urllib) so no new runtime deps; HEAD-then-GET
  pattern + 15s timeout. Fetch failures swallowed silently and
  reported as `unreachable` findings (not exceptions) since
  network errors are ops signals, not bugs.
  31 new tests under `TestCitationResolver`, `TestContentHash`
  (cosmetic-edit tolerance + invalid UTF-8), `TestScanSpec` (real
  US/EU specs + dedup + sorted output), `TestFetchCurrent` (with
  injected fetch_fn — no network calls), `TestCheckDrift`
  (no-drift + drift detected + unreachable separate from drift +
  has_findings), `TestBaselinePersistence` (round-trip + missing
  file + deterministic file bytes), `TestCitationMapCoverage`
  (every regime represented + every URL HTTPS).
  Bug fix: `engine/runner.py` now drops None-valued fields from
  `regulation_refs` when writing cases so downstream narrative
  consumers expecting `dict[str, str]` don't choke on the new
  optional `url` field. Test count 953 → 984.

- **TBML + UK APP-fraud example specs** (`examples/trade_based_ml/`,
  `examples/uk_app_fraud/`, `docs/jurisdictions.md`,
  `tests/test_specs_tbml_app_fraud.py`). Round-7 PR #3 — third-
  ranked feature from the 2026-04 positioning research. Both specs
  answer the FRAML-convergence buyer question without building a
  fraud engine — just demonstrating the framework can express the
  typologies cleanly.
  `examples/trade_based_ml/aml.yaml` ships 5 TBML rules
  (over/under-invoicing vs WCO baseline, phantom_shipping,
  multiple_invoicing, TRAD-to-high-risk-jurisdiction). New
  `hs_code_baseline` data contract carries the WCO median/p5/p95
  unit prices the over/under-invoicing rules join against. All 5
  rules cite FATF Trade-Based Money Laundering (Sep 2025) +
  Egmont TBML Indicators (Sep 2024).
  `examples/uk_app_fraud/aml.yaml` ships 4 APP-fraud rules
  (first-use-payee >GBP 1000, Confirmation-of-Payee mismatch
  override, vulnerable-customer atypical payment, rapid
  pass-through mule). Workflow includes `customer_intervention`
  (30m SLA), `payment_held` (4h freeze), `reimbursement_decision`
  (96h, PSR_REIMBURSEMENT form). L1 SLA is 1h — APP fraud requires
  intervention before settlement. Cites PSR Specific Directions
  (SD17 CoP, SD20 reimbursement) + FCA FG24/4 + POCA 2002.
  Both specs documented in jurisdictions.md.
  17 new tests for spec validity, rule shape, citation coverage,
  workflow queue presence, severity classification, and the
  no-python-ref guard (no callables shipped for these specs;
  enforces first-run cleanliness). Tests 953 → 970.

- **PSD3 / Verification-of-Payee (VoP) ingestion adapter**
  (`data/psd3/parser.py`, `data/psd3/sample_vop_responses.jsonl`,
  `tests/test_psd3_vop.py`). Round-7 PR #4 — fourth-ranked feature
  from the 2026-04 positioning research. PSD3 + PSR reached
  Council/Parliament provisional agreement end-Q2 2026; VoP
  liability applies 24 months after Official Journal entry into
  force (~Q3 2028). The 2-year window is the right time for a
  reference implementation to exist before banks have to procure.
  Status: **DRAFT** — pinned to provisional text via
  `VOP_SCHEMA_VERSION = "psd3-vop-2026-q2-draft"`.
  `parse_vop_response(payload)` returns a `VopResponse` dataclass
  (request/payment ids, payer+payee IBANs, names, match score,
  outcome, account status, response time, received_at). Tolerates
  both camelCase and snake_case field variants. Never raises on
  malformed input.
  `vop_match_outcome(*, score, ...)` classifies into the 5 PSD3
  outcomes: match (≥0.85), close_match (0.70-0.84), no_match,
  not_checked, outside_scope. Same value vocabulary as the UK
  CoP scheme (Round-7 #3 UK APP-fraud spec) — one txn column
  works for both schemes.
  Bundled sample exercises all 5 outcomes. 25 new tests covering
  classifier thresholds, parser robustness, schema pinning, bulk
  loader. Tests 953 → 978.

- **FINTRAC pre-examination audit pack**
  (`generators/audit_pack.py`, `cli.py:audit_pack_cmd`,
  `tests/test_audit_pack.py`). Round-7 PR #5 (final from the
  positioning research). FINTRAC's January 2026 examination manual
  update made the pre-exam evidence demand explicit. New
  `aml audit-pack <spec> --jurisdiction CA-FINTRAC --out
  audit-pack.zip` produces a deterministic ZIP containing 9 files:
  program.md + inventory.json + alerts_summary.json +
  cases_summary.json + audit_trail_verification.json +
  sanctions_evidence.json + pcmltfa_section_map.md (every cited
  PCMLTFA section + which rules cover it) + osfi_b8_pillars.md
  (OSFI B-8 4-pillar coverage) + manifest.json (file-by-file
  SHA-256). Same determinism guarantee as the Round-6 STR bundle.
  Per-jurisdiction by design — `SUPPORTED_JURISDICTIONS` frozenset
  gates `--jurisdiction`. CA-FINTRAC ships in v1; UK FCA / EU
  AMLA / US FinCEN clone the same skeleton.
  20 new tests covering structure, manifest contract, determinism,
  per-section content, jurisdiction guard, end-to-end against a
  real CA Schedule-I bank engine run.

- **Synthetic data enriched with ISO 20022 fields** (`data/synthetic.py`,
  `tests/test_iso20022_purpose_codes.py`). The default demo
  (`aml run --seed 42`) didn't exercise any Round 5/6 features
  because synthetic txns had no purpose_code, no UETR, no BICs,
  hiding ~6 PRs of work from new users. Now `_make_txn()`
  auto-populates 5 ISO 20022 fields for wire / sepa / e_transfer
  channels (purpose_code from a benign-biased noise distribution,
  deterministic UETR, BICs from per-country pools, counterparty
  country). Cash / ACH / card stay empty.
  Two new planted positives:
  - **C0010 (Klara Becker, DE)** — 3 outbound INVS wires to CH
    in 14 days summing to EUR 8300. Triggers EU spec's
    `invs_velocity_investment_scam` rule (FATF Feb 2026
    pig-butchering signature).
  - **C0011 (ROAMR LTD, GB)** — 3 pacs.004 return events
    (AC03/AC04/MD07) on a new `txn_return` output list. Composes
    with Round-5 #5 return-reason mining library.
  Determinism preserved (test_run_is_reproducible still passes).
  `test_synthetic_data_yields_no_invs_alerts` inverted to
  `test_synthetic_data_fires_invs_planted_positive` — now
  asserts the exact planted positive on C0010 fires.

- **Workflow audit + executive font scale + page interactivity**
  (`dashboard/components.py`, `dashboard/app.py`,
  `dashboard/audience.py`, `dashboard/pages/5_Rule_Performance.py`,
  `dashboard/pages/6_Risk_Assessment.py`,
  `dashboard/pages/12_Sanctions_Screening.py`,
  `dashboard/pages/19_Comparative_Analytics.py`,
  `tests/test_dashboard_workflows.py`). User-driven workflow audit
  — verify every persona has a complete experience.

  **Executive font scale** — new `EXECUTIVE_AUDIENCES` frozenset
  ({svp, vp, director, cto, cco}) drives an additional CSS overlay
  injected by `apply_theme()` when the audience selector is set to
  one of those personas. KPI values jump from 1.8rem → 2.4rem,
  metric-card values from 2rem → 2.8rem, headers up by ~30%, body
  text +5%. Tables stay at base size to avoid breaking dense
  layouts. The use case: SVP/CTO reading from a meeting-room
  display want bigger numbers without leaning in.

  **Two new personas** in the audience map: `cto` (Executive
  Dashboard, Program Maturity, Framework Alignment, Model
  Performance, Run History, Transformation Roadmap) and `cco`
  (Executive Dashboard, Program Maturity, Framework Alignment,
  Risk Assessment, Audit & Evidence, Investigations,
  Transformation Roadmap). Audience selectbox updated to expose
  all 10 personas with a help line explaining the executive font
  scale.

  **Pages 22 + 23 registered in `ALL_PAGES`** — Analyst Review
  Queue and Tuning Lab existed on disk and were referenced in the
  audience map but never registered in `app.py`'s sidebar nav, so
  they were invisible to operators. Drift bug from a previous PR.
  Both now appear with appropriate icons.

  **Filters added to 4 previously-static pages**:
  - **Rule Performance** — multiselect severity + multiselect
    logic-type + "only fired" toggle
  - **Risk Assessment** — multiselect country + multiselect risk
    rating; filtered df cascades to all KPIs/charts/tables on the
    page so the view stays consistent
  - **Sanctions Screening** — multiselect match type + multiselect
    severity + min-score slider; filtered counter shows
    "N of M shown"
  - **Comparative Analytics** — multiselect severity + "hide silent
    rules" toggle for the per-rule alert chart

  **15 new tests** under `tests/test_dashboard_workflows.py` —
  audience-map ↔ pages-on-disk coverage (handles three
  page_header patterns: positional string, kwarg string,
  PAGE_TITLE constant), executive-personas always include
  Executive Dashboard, EXECUTIVE_CSS constant present + wired into
  apply_theme, audience selectbox exposes every mapped persona,
  every persona's pages exist as registered file in `ALL_PAGES`
  (regression guard for the pages-22/23-missing bug), every
  previously-non-interactive page now carries a widget (regression
  guard against filters being stripped), every page reads session
  state or is in the documented STATIC_PAGES exception list.

### Fixed
- **`aml --help` crashed on fresh installs** (`pyproject.toml`).
  Bumped `typer>=0.12` floor to `typer>=0.16`. typer 0.15 was
  built against click 8.1.x but allowed by the old floor; click
  8.3.0 changed `Parameter.make_metavar()` to require a `ctx`
  argument, breaking typer 0.15's rich-help renderer with
  `TypeError: Parameter.make_metavar() missing 1 required
  positional argument: 'ctx'`. CI ran fine because fresh CI
  installs picked typer 0.25; only locally-cached typer 0.15
  installs hit the bug. New floor blocks the broken combination
  at install time.

### Added (docs sweep)
- **`docs/jurisdictions.md` — `crypto_vasp` spec** added to the
  bundled-specs table (was on disk in `examples/crypto_vasp/`
  since Round-3 but only mentioned in passing). Its specialty
  section now lists the regulatory hooks (FATF R.15-16, FinCEN
  FIN-2019-G001, FINTRAC PCMLTFR s.7.7), the framework features
  it exercises (network_pattern rule type, wallet sanctions
  screening, VASP counterparty attribution), and a launch
  command. Drift item from the 30-day docs sweep (issue #68).

### Added
- **Mobile-responsive dashboard overlay** (`dashboard/components.py`,
  `dashboard/app.py`, `tests/test_dashboard_mobile_css.py`,
  `tests/test_e2e_dashboard_mobile.py`, `.github/workflows/ci.yml`).
  Closes [issue #66](https://github.com/tomqwu/aml_open_framework/issues/66).
  Lightweight overlay path from the issue's two options — no
  separate JS client, just CSS + a Streamlit page-config tweak.
  CSS additions to `CUSTOM_CSS` in `components.py`:
  - `@media (max-width: 768px)` block — tightens container padding,
    forces `[data-testid="stHorizontalBlock"]` to
    `flex-direction: column` so 4-up KPI rows stack on tablets and
    phones, compresses headers, caps Plotly chart height at 60vh,
    enables horizontal-scroll on dataframes (so wide tables don't
    blow out the page width)
  - `@media (max-width: 480px)` block — phone-specific further
    tightening + sidebar capped at 85vw so users can see page
    content beneath when sidebar is opened
  - 44px `min-height` on buttons / `[role="button"]` / inputs at
    ≤768px (Apple HIG + Material Design touch-target standard)
  `app.py` change: `initial_sidebar_state="expanded"` →
  `"auto"` — Streamlit's auto mode collapses the sidebar by
  default on narrow viewports while keeping desktop UX unchanged.
  New `responsive_plotly_config()` helper exports
  `{"responsive": True, "displayModeBar": False}` for pages to
  pass via `st.plotly_chart(fig, config=responsive_plotly_config())`
  — makes Plotly charts re-layout on viewport changes (rotation,
  sidebar collapse).
  10 unit tests under `test_dashboard_mobile_css.py` — source-
  level CSS-presence checks. Runs on the minimal unit-test CI
  image (no streamlit dep).
  9 e2e tests under `test_e2e_dashboard_mobile.py` parametrized
  over 3 viewports (375x667 iPhone SE, 414x896 iPhone XR,
  768x1024 iPad portrait): no horizontal scroll on landing,
  sidebar collapsed at phone size, mobile CSS in DOM, no error
  banners. Separate port (8600) so the two suites can run in
  parallel.
  CI config updated: unit-tests + docker-build jobs ignore the
  new mobile e2e file; e2e-dashboard runs both suites, timeout
  bumped from 5 to 8 minutes.

- **Documentation refactor + Getting Started guide** (`README.md`,
  `docs/getting-started.md`, `docs/dashboard-tour.md`,
  `docs/jurisdictions.md`, `tests/test_docs_links.py`). README
  shrunk **582 → 123 lines (-79%)** by extracting the bulky
  dashboard-page tour, multi-jurisdiction section, and persona
  workflows into dedicated docs and converting the README into a
  hub-style entry point with a single-glance documentation map.
  Three new top-level docs:
  - **`docs/getting-started.md`** — focused 15-minute path from
    `git clone` to a running audit bundle. Seven numbered steps
    (install → pick spec → run → dashboard → BYOD → first custom
    rule → audit bundle), a "Common First-Time Issues" section,
    and a "What Next?" routing table to every other doc.
  - **`docs/dashboard-tour.md`** — every dashboard page (22 now
    with #24 Investigations) organized into Operational /
    Strategic / Engineering / Audit / Export sections.
  - **`docs/jurisdictions.md`** — US (FinCEN/BSA), CA (FINTRAC +
    OSFI), EU (EBA/AMLD6), UK (FCA/POCA) plus cyber-fraud +
    crypto VASP specialty specs, with a 5-step "adapt to your
    institution" checklist.
  README now leads with hero image, 5-line "Why", 3-command
  Quickstart, and a **Documentation Map** table organized as
  Start Here / Reference / Operations — every other doc is one
  hop away. Repository layout, key CLI commands, and testing
  one-liners stay; everything else moves out.
  19 new link-validation tests under `tests/test_docs_links.py`
  parametrized over `README.md` + every `docs/*.md` +
  `CHANGELOG.md` + `CONTRIBUTING.md` — every relative link must
  resolve. Plus guard tests for the README ≤200-line size cap
  and the documentation map's presence + key cross-links.

- **Investigations dashboard page** (#24)
  (`dashboard/pages/24_Investigations.py`,
  `dashboard/audience.py`, `dashboard/app.py`). Round-6 PR #5 of 5
  — **closes the case-management arc**. Surfaces the investigation
  aggregator (PR #61) + SLA timer (PR #63) in one operator-facing
  view that consolidates the per-alert case backlog into the
  unit FinCEN's effectiveness rule + FCA's Mar 2026 Dear CEO
  letter both treat as canonical. Three sections: queue backlog
  (per-queue green/amber/red/breached counts with breach-rate +
  oldest-age columns), investigations list (sortable by severity →
  total_amount), and an investigation detail drill-down with KPI
  metrics + per-constituent-case live SLA state + escalation
  recommendation. Sidebar exposes aggregation-strategy control
  (per_customer_window / per_customer_per_run / per_case) and an
  "evaluate SLA against now()" toggle for live-ops vs backtest
  view. Wired into `audience.py` for `manager` + `analyst`
  personas, registered in `app.py` ALL_PAGES with the
  `:material/group_work:` icon. Bails out gracefully with a
  warning when no cases are loaded.
  9 new unit tests under `TestPageFile`, `TestAudienceWiring`,
  `TestAppRegistration`, `TestEndToEndComputables` (verifies the
  4 case-module functions the page calls compose against a real
  CA Schedule-I bank engine run without raising). Streamlit
  rendering exercised by the e2e-dashboard CI job; unit tests
  don't import streamlit so they run on the minimal CI image.

- **SLA timer + escalation engine** (`cases/sla.py`). Round-6 PR #3.
  The framework's engine already records `within_sla` and
  `resolution_hours` in the simulated decisions ledger, but those
  are *retrospective*. **The FCA's March 2026 Dear CEO letter on
  SAR backlogs** named real-time SLA tracking + active escalation
  discipline as the gap UK firms most often failed on in
  supervisory visits. This module gives operators the live-queue
  view examiners want.
  New `compute_sla_status(case, queue, *, as_of)` returns an
  `SLAStatus` dict: `state` (green >50% / amber 10-50% / red 0-10%
  / breached <0%), `queue_sla_hours`, `time_in_queue_hours`,
  `time_remaining_hours`, `pct_remaining`, `opened_at`, `due_at`.
  Bands fully overridable via `sla_thresholds` arg. Cases with no
  resolvable open time return None (not silently misclassified
  breached) so callers can surface data-quality issues separately.
  Companion `apply_escalation(case, status, queue)` returns an
  `EscalationAction` (frozen dataclass) only when SLA has actually
  breached AND the queue's `next` list contains a non-closure
  destination — picks the first non-`closed_*` / non-`*_no_action`
  entry, typically the higher-tier investigator queue. Returns None
  for green/amber/red (escalation is breach-only by policy),
  terminal queues, and pure-closure next lists.
  Companion `summarise_backlog(cases, spec, *, as_of)` rolls SLA
  states up by queue. Returns one `BacklogStats` per queue defined
  in the spec's workflow (zero-count rows preserved so the
  dashboard's queue-health table doesn't omit empty rows). Each
  row carries: queue_id, queue_sla_hours, total_cases, green/
  amber/red/breached counts, oldest_age_hours, breach_rate_pct.
  Composes with PR #61 investigation aggregator (per-investigation
  backlog stats), feeds Round-6 #5 case dashboard page, and
  contributes to Round-7 #1 outcome metrics (SLA-breach rate per
  rule per quarter is one of the FinCEN NPRM funnel ratios).
  25 new tests under `TestComputeSLAStatus`, `TestApplyEscalation`,
  `TestSummariseBacklog`, `TestEndToEndWithEngine`.

- **Case-to-STR auto-bundling** (`cases/str_bundle.py`). Round-6
  PR #4. The framework's existing artifacts make analyst handoff
  work but require operator stitching: narrative.txt comes from
  `generators/narrative.py`, the regulator-format XML from
  `generators/goaml_xml.py`, the Mermaid network diagram from
  `engine/explain.py`, and the case JSON itself from the audit
  ledger. **Wolfsberg's Feb 2026 correspondent-banking guidance**
  named "submission-ready packages" as the expectation for
  issuer-FI handoffs to FIU; ad-hoc PDF bundles no longer cut it.
  New `bundle_investigation_to_str(investigation, cases, *, spec,
  customers, transactions)` produces one self-contained
  `<investigation_id>.zip` containing:
  - `investigation.json` — the Investigation dict from PR #61
  - `cases/<case_id>.json` — every constituent case file
  - `narrative.txt` — analyst-ready narrative joining all
    constituent cases (auditors complained that per-case narratives
    lost the link between alerts that fired together)
  - `goaml_report.xml` — regulator-format XML covering all cases
  - `network/<case_id>.mmd` — Mermaid diagram per case that has a
    `network_pattern` subgraph (skipped for non-network rules)
  - `manifest.json` — bundle metadata + per-file SHA-256 + bundle-
    wide hash + spec_program + jurisdiction + sorted case_ids
  Pure function returning bytes (no IO; caller decides where to
  write). **Deterministic by construction**: sorted file order,
  fixed `_ZIP_FIXED_TIME` baked into every ZipInfo, sorted JSON
  keys, pinned `_FIXED_SUBMISSION_DATE` for the embedded goAML XML
  so identical inputs produce byte-identical archives. Real
  submission timestamps go in the audit ledger; the artifact uses
  a synthetic anchor so deterministic-rerun verification holds
  (composes with PR #53 MRM bundle). Companion `bundle_hash(bytes)`
  returns SHA-256 over the entire ZIP for receipt records.
  Robust to: cases not in the investigation's case_ids list
  (silently dropped), unknown customers (narrative falls back),
  malformed subgraph payloads (network diagram skipped, bundle
  still valid), empty constituent set, mixed datetime / ISO-string
  shapes in alert window bounds.
  23 new tests under `TestBundleStructure`, `TestManifest`,
  `TestDeterminism`, `TestNarrative`, `TestGoamlXml`,
  `TestEdgeCases`, `TestEndToEndWithEngine`.

- **Investigation aggregator** (`cases/aggregator.py`,
  `cases/__init__.py`). Round-6 PR #1 — opens the case-management
  arc. The engine emits one case per alert
  (`case_id = "{rule_id}__{customer_id}__{window_end}"`), so a
  customer hit by 3 different rules in one run produces 3 separate
  cases. **FinCEN's 2024 effectiveness rule (and its 2026
  supervisory guidance) measures program effectiveness in terms of
  *investigations*, not alerts** — an investigation is one subject
  reviewed once with all related signals together. Without this
  entity the framework couldn't compute the alert → investigation
  → SAR funnel that FinCEN now treats as the canonical program
  metric.
  New `aggregate_investigations(cases, *, strategy=...)` is a pure
  function over the engine's case list (no IO; the audit ledger
  remains the persistence layer). Three grouping strategies in v1:
  - `per_customer_window` (default) — group by (customer_id, 30-day
    bucket from a fixed 2020-01-01 epoch). Two cases for the same
    customer 25 days apart land in the same investigation; 35 days
    apart land in different ones. Bucket epoch is fixed so
    investigation IDs don't drift across runs.
  - `per_customer_per_run` — every case for a customer in this run
    becomes one investigation regardless of timing.
  - `per_case` — singleton investigations (legacy compat for
    operators who don't want grouping).
  Each `Investigation` carries: `investigation_id` (deterministic
  `INV-<sha256[:16]>` over sorted constituent case_ids — same input
  always produces same ID), `customer_id`, `case_ids` / `rule_ids`
  (sorted, deduped), `severity` (max across cases using
  low<medium<high<critical ordering), `queues` / `tags` /
  `evidence_requested` (union, sorted), `total_amount` (sum of
  alert sum_amount fields, Decimal-safe with string-coercion
  fallback), `window_start` / `window_end` (min/max across alert
  windows), `case_count`, `rule_count`, `strategy`. Companion
  helper `bucket_window_for(dt)` returns the 30-day [start, end)
  bounds for dashboard queries that want to show "all cases in
  this investigation's window" without recomputing bucket math.
  Foundation for Round-6 features 3-5 (SLA timer, case-to-STR
  auto-bundling, case dashboard page) and Round-7 #1 (outcome
  metrics — alert-to-investigation conversion + investigation-to-
  SAR conversion are the two FinCEN-mandated funnel ratios).
  34 new tests across `TestPerCustomerWindow` (collapse +
  bucket-split + customer-split + default-strategy assertion),
  `TestPerCustomerPerRun` (cross-bucket collapse + customer
  separation), `TestPerCase` (singleton invariant),
  `TestSeverityEscalation` (max-wins + ordering + unknown-severity
  default), `TestSumAmount` (Decimal sum + missing-defaults-zero +
  string-coercion + unparseable-skipped), `TestWindowBounds`
  (datetime + ISO-string + no-timestamps), `TestDeterminism`
  (same-input same-IDs + order-independence + ID format + distinct
  inputs distinct IDs + sorted output), `TestBucketing` (30-day
  width + abutting consecutive buckets + monotonic indices),
  `TestEdgeCases` (empty input + missing customer_id dropped +
  unknown strategy raises + no-window collapse + tag/evidence/queue
  union), `TestEndToEndWithEngine` (aggregator runs over a real
  Canadian Schedule-I bank engine run; all cases end up in some
  investigation — no losses; Investigation TypedDict shape
  matches). Total test count 792 → 826.

- **Multi-tenant dashboard surfacing** (`dashboard/tenants.py`,
  `dashboard/app.py`, `dashboard/state.py`,
  `dashboard_tenants.example.yaml`). Round-6 PR #2. The REST API
  already had full tenant isolation (`api/auth.py:create_token`
  carries a `tenant` claim; every `api/db.py` query filters by
  `tenant_id`), but the Streamlit dashboard hardcoded a single
  spec path. This PR brings the dashboard up to surface parity
  with the API's tenant model — a single dashboard process can
  now register multiple programs (e.g. EU bank + Canadian bank +
  cyber-fraud spec) and let the operator switch between them via
  a sidebar selector.
  Trust model is **display-only multi-tenancy**: the dashboard
  runs the engine locally per selected tenant; whoever can launch
  the dashboard process sees every configured tenant. Real
  per-user authorization remains in the REST API path. The plan
  note for this PR was "API has it, dashboard doesn't" — surface
  parity, not isolation.
  New `load_tenants()` reads from `$AML_TENANTS_CONFIG` (env var
  override) → `<project>/dashboard_tenants.yaml` (default). Each
  tenant entry needs `id` + `spec_path`; optional `display_name`
  (falls back to id) + `jurisdiction`. When no config exists,
  loader returns a single `default` tenant pointing at the
  community-bank spec — preserves the previous single-spec
  behavior so existing launches keep working with no migration.
  Companion `resolve_tenant(id)` raises `TenantConfigError` on
  unknown ids and includes the available list in the error
  message — silent fallback would mask deployment misconfiguration.
  `state.py` keys its session cache on `(tenant_id, seed)` so
  switching tenants triggers a re-run without losing other
  tenants' previously-computed results during the session.
  `app.py` shows the tenant selector only when (a) >1 tenant is
  configured AND (b) the dashboard wasn't launched with an
  explicit CLI spec path — single-tenant deployments and
  `aml dashboard <spec.yaml>` invocations see no added UI noise.
  Selector switch triggers `st.rerun()`.
  `dashboard_tenants.example.yaml` ships 5 example tenants
  spanning all 4 jurisdictions; tests verify every example spec
  path resolves to a real file (no broken links on copy).
  All config validation produces `TenantConfigError` with
  actionable messages: empty list, missing `tenants:` key,
  non-mapping top level, duplicate ids, missing `id` /
  `spec_path` per entry, malformed YAML.
  26 new tests under `TestDefaultFallback`, `TestLoadTenants`,
  `TestErrorHandling`, `TestResolveTenant`, `TestEnvVarOverride`,
  `TestTenantConfigDataclass`, `TestBundledExample`. Total test
  count 826 → 852.

- **pacs.004 payment-return ingestion + return-reason mining library**
  (`data/iso20022/parser.py:Pacs004Parser`,
  `data/iso20022/sample_pacs004.xml`,
  `spec/library/iso20022_return_reasons.yaml`,
  `data/lists/iso20022_return_reason_codes.csv`). Round-5 PR #5 of 5
  — **closes the Round-5 ISO-20022 arc**. The **UK Payment Systems
  Regulator's APP-fraud reimbursement mandate** (effective Oct 2024,
  full effect Apr 2026) made return-reason mining material to
  issuer economics: every reimbursable claim that traces back to a
  missed mule signal at the sending PSP costs that PSP 50% of the
  reimbursement under the mandatory split. Mining return reasons
  per-originator stopped being optional. New `Pacs004Parser`
  consumes `<PmtRtr>` payloads (ISO 20022 PaymentReturn, pacs.004)
  and emits dicts on a **separate `txn_return` data contract** —
  rows do NOT mix into `txn` because the schemas don't overlap.
  Each row preserves: `return_id`, `original_uetr` (preferred join
  key back to credit transfers), `original_end_to_end_id`,
  `original_tx_id`, `amount`, `currency`, `returned_at`,
  `reason_code` (ExternalReturnReason1Code: AC03, AC04, AM05, MD07,
  FRAD, BE05, …), `reason_info` (free text), `originator_name` /
  `originator_country` and `beneficiary_name` /
  `beneficiary_country` extracted from `<OrgnlTxRef>`. Auto-detect
  dispatch now: pacs.004 → pain.001 → pacs.009 → pacs.008 fallback;
  pacs.004 must be checked first or it would silently fall through
  to the credit-transfer path and produce empty txn rows.
  New companion helpers split the mixed-directory case cleanly:
  - `load_iso20022_dir(dir)` — credit transfers only (pacs.008/009 +
    pain.001), filters out pacs.004. **Existing behavior preserved**
    (the `iso20022` source-type integration is unaffected).
  - `load_iso20022_returns_dir(dir)` — pacs.004 only. Operators
    point this at the same XML directory and get a clean
    `txn_return`-shaped row list, ready to load into a sibling
    DuckDB table.
  Bundled `sample_pacs004.xml` covers ROAMR LTD (a corporate
  originator) hitting **four returns in one week** with the
  canonical money-mule-probing reason mix (AC03 invalid-account,
  AC04 closed-account, MD07 deceased-payee, AM05 duplication) — all
  to CH beneficiaries. This is the textbook "originator is testing
  which mule accounts are still alive" pattern that snippet 1
  catches.
  New **`spec/library/iso20022_return_reasons.yaml`** ships **3
  reusable rule snippets** (sibling to PR #58's
  `iso20022_purpose_codes.yaml`, same copy-paste-not-include
  pattern that preserves the "every line written by a human"
  defensibility moat):
  - **`high_risk_return_burst_mule_probing`** (severity high, custom_sql
    on `txn_return`) — fires when a single originator hits ≥3 returns
    in 14 days with codes from the curated mule-signal set
    (AC03/AC04/AC06/AG01/AM05/BE05/BE06/FRAD/MD07/RR04). Cites UK PSR
    APP-fraud CRS, FATF Cyber-Enabled Fraud Feb 2026, FCA FG24/4.
  - **`corridor_return_rate_spike`** (severity medium, custom_sql
    joining `txn` + `txn_return`) — corridor-level abuse detection
    for originators with high outbound volume where absolute return
    counts wouldn't trigger snippet 1 but the rate (≥10% returned in
    the originator/beneficiary-country corridor with ≥10 sent) is
    anomalous. Cites Wolfsberg Feb 2026 correspondent-banking
    guidance + UK PSR CRS.
  - **`deceased_payee_returns_md07`** (severity high, custom_sql on
    `txn_return`) — multiple MD07 returns from one originator in
    90d is the **death-record-scraping fraud-ring tradecraft** signal.
    Cites FinCEN FIN-2023-Alert005 (identity-theft impersonation) and
    UK PSR CRS (reimbursement covers impersonation against deceased
    account-holders).
  New **`data/lists/iso20022_return_reason_codes.csv`** — 44
  ExternalReturnReason1Code rows with `description`, `risk_band`
  (low/medium/high), and `mule_signal` boolean classification. The
  `mule_signal=true` subset is the curated list that snippet 1 keys
  on; tests enforce the contract that every code cited in the
  snippet is flagged `mule_signal=true` in the CSV (no drift).
  36 new tests under `TestPacs004Parser` (4-row extraction +
  return_id / original_uetr / original_end_to_end_id / amount /
  currency / returned_at / reason_code / reason_info / originator
  pulled from `<OrgnlTxRef>` / beneficiary / msg_id propagation),
  `TestPacs004Robustness` (empty payload / malformed XML / missing
  reason / fallback to msg_id when no RtrId / fallback to
  IntrBkSttlmAmt when no RtrdIntrBkSttlmAmt / namespace-agnostic
  parsing across XSD versions), `TestAutoDetectDispatch` (pacs.004
  / pacs.008 / pain.001 routing through `parse_iso20022_xml`),
  `TestDirLoaders` (`load_iso20022_dir` filters out pacs.004 +
  `load_iso20022_returns_dir` returns only pacs.004 + the two
  loaders are disjoint over the same mixed directory),
  `TestLibraryYAML` (file exists / loads as list / every snippet
  validates as Pydantic Rule / pacs004 tag on every snippet / known
  snippet IDs present), `TestReturnReasonCSV` (file exists /
  required columns / cited codes classified / valid risk_band
  values / boolean-string `mule_signal` values / mule_signal codes
  align with snippet 1's hardcoded list / no duplicate codes).
  Total test count 740 → 792.

- **pain.001 corporate-batch ingestion**
  (`data/iso20022/parser.py:Pain001Parser`,
  `data/iso20022/sample_pain001.xml`). Round-5 PR #4 of 5 — extends
  PR #56's parser module. **Wolfsberg Group's Feb 2026
  correspondent-banking guidance** flagged corporate-banking AML as
  the surveillance gap: bulk pain.001 files (Customer Credit
  Transfer Initiation) often slip past per-transaction monitoring
  because the debtor + KYC context is shared at the file level
  rather than repeated per row. New `Pain001Parser` consumes
  `<CstmrCdtTrfInitn>` payloads and produces dicts conforming to
  the same `txn` data contract as pacs.008/009 — engine + every
  downstream rule type works unchanged. Per-row mapping mirrors
  PR #56 with two structural differences:
  - The **debtor block lives at the `<PmtInf>` level** (Payment
    Information group), not per `<CdtTrfTxInf>`. The parser
    propagates `customer_id` / `debtor_iban` / `debtor_country` /
    `debtor_bic` / `charge_bearer` / `requested_execution_date`
    from each parent `<PmtInf>` down to all child transfers in
    that group. A single corporate file can carry multiple
    `<PmtInf>` blocks with different debtors (e.g. multi-currency
    multi-account disbursements); each group's debtor is correctly
    isolated.
  - The amount lives in `<Amt>/<InstdAmt Ccy=...>` instead of
    `<IntrBkSttlmAmt>`; new `_extract_pain001_amount()` helper
    handles the difference.
  - **UETR is empty** on pain.001 rows (the message is
    customer-initiated; the FI assigns UETR when forwarding as
    pacs.008). Travel-rule validator (PR #57) treats missing UETR
    as informational, not a finding.
  Two new pain.001-specific extras preserved on every row:
  `payment_information_id` (operator-supplied batch id) and
  `requested_execution_date` (corporate's intended booking date,
  may differ from FI booking date). Auto-detect dispatch in
  `parse_iso20022_xml` now: pain.001 → pacs.009 → pacs.008
  fallback. The `iso20022` source type from PR #56 picks pain.001
  files up automatically — the directory walk + dispatcher already
  iterate every `*.xml` under `data_dir`.
  Bundled `sample_pain001.xml` covers ACME GMBH submitting one
  corporate batch with 2 `<PmtInf>` groups (different execution
  dates) carrying 4 transfers total: SUPP supplier payment to FR,
  SALA payroll, two INVS transfers to a CH offshore vehicle. This
  exercises shared-debtor propagation, multi-PmtInf grouping,
  three different purpose codes, and cross-border to non-EEA.
  29 new tests under `TestPain001Parser` (4-row extraction +
  shared-debtor + EndToEndId / amount / currency / purpose / BIC /
  IBAN / ReqdExctnDt / payment_information_id / charge-bearer
  inheritance / empty-UETR / msg_id / channel + direction
  constants / structured remittance), `TestEdgeCases` (minimal
  message / missing optionals / malformed XML / no PmtInf / PmtInf
  without transfers / multiple PmtInf with different debtors /
  namespace-agnostic / fallback txn_id), `TestAutoDetect` (pain.001
  dispatch), `TestMixedIngestionDir` (loads pain.001 alongside
  pacs.008 in the same dir), and `TestComposesWithTravelRule`
  (full-fields rows produce zero R.16 alerts; stripping
  beneficiary IBAN fires exactly one alert with
  `beneficiary_account` in `missing_fields`).
- **FATF R.16 Travel Rule field validator**
  (`models/travel_rule.py`, `examples/eu_bank/aml.yaml`). Round-5
  PR #2 of 5 — composes directly with PR #56 ISO 20022 ingestion.
  FATF Plenary February 2026 reiterated R.16 (revised June 2025)
  as a top-tier deficiency in MERs; EU Regulation 2023/1113
  ratified the implementation with full enforcement throughout
  2026. Without runtime field-completeness scoring, ingested
  pacs.008 traffic landed with no compliance verdict on whether
  the originator + beneficiary fields were actually present.
  This validator runs as a `python_ref` scorer
  (`aml_framework.models.travel_rule:validate_travel_rule`)
  reading the `txn` table's `debtor_*`, `counterparty_*`, `uetr`,
  and `purpose_code` columns the ISO 20022 parser writes
  (PR #56). For every wire it:
  - Flags **cross-border** rows (debtor country ≠ counterparty
    country; missing-country treated as cross-border per AML
    conservative default).
  - Filters to rows **above the per-currency de minimis**
    threshold (FATF R.16 minimum is USD/EUR 1,000; built-in
    table covers 8 majors with `JPY=100k`, `CNY=7k`, etc.;
    operator override via `AML_TRAVEL_RULE_THRESHOLDS=USD=500,GBP=900`).
  - Checks **originator completeness** (name + account/IBAN +
    address-OR-national-id-OR-DOB-POB) and **beneficiary
    completeness** (name + account). OR-logic across alternate
    columns lets a customer-resolver populate any one of them.
  - Emits one alert per offending row with a structured
    `missing_fields` list, an `is_cross_border: true` flag, the
    UETR + purpose code propagated for downstream traceability,
    and a severity hint (`critical` if amount ≥ 10× the
    threshold; `high` otherwise).
  Schema-tolerant — runs against the older 7-column synthetic
  `txn` schema and against the new ISO-20022-extended schema
  alike (missing columns are coerced to NULL in the SELECT and
  treated as absent during field-completeness checking).
  Wired into `examples/eu_bank/aml.yaml` as the canonical
  `travel_rule_completeness` rule (cites FATF R.16 + EU Reg
  2023/1113 in `regulation_refs`); `aml validate` confirms the
  6-rule shape; `aml run` against the bundled pacs.008 sample
  produces zero alerts (the sample is fully compliant) but
  flags any row where the operator removes a field. 29 new
  tests under `TestThresholdHelpers` (defaults + env overrides
  + NaN/zero filtering), `TestCrossBorder`, `TestMissingFields`,
  `TestValidateTravelRule` (threshold gating, channel filter,
  severity scaling, multiple-missing-fields, one-alert-per-row),
  `TestSchemaTolerance` (minimal 7-col schema; missing txn
  table → empty), and `TestPythonRefIntegration` (end-to-end
  through `run_spec` with a built-in-line spec).
- **ISO 20022 purpose-code typology library**
  (`spec/library/iso20022_purpose_codes.yaml`,
  `data/lists/iso20022_high_risk_purpose_codes.csv`). Round-5 PR #3
  of 5. SWIFT's MX-only cutover (2025-11-22) replaced the legacy
  free-text "purpose of payment" string with the structured
  ExternalPurpose1Code enum (~150 codes). That enum unlocks
  typology rules that simply weren't expressible before — distinguishing
  "INVS misuse in a fake-investment scam" from "CHAR donation routed
  via shell-charity" cleanly. Library v1 ships **4 reusable rule
  snippets** (copy-pasteable, not auto-included — preserves the
  "every line of the spec was written by a human" defensibility
  story):
  1. **`invs_velocity_investment_scam`** — `aggregation_window`
     detecting INVS purpose-code velocity (FATF Feb 2026 names INVS
     as the canonical pig-butchering payout marker). Ships with a
     `tuning_grid` for count + sum_amount sweeps.
  2. **`char_gift_burst_shell_charity`** — `aggregation_window`
     for CHAR/GIFT clustering (shell-charity / romance-scam payout).
  3. **`deri_from_retail_mandate_mismatch`** — `custom_sql` joining
     txn.purpose_code='DERI' against customer.business_activity
     (MiFID II Art. 16 mandate-suitability + AMLD6 Art. 18a EDD).
  4. **`trad_to_high_risk_jurisdiction_tbml`** — `custom_sql` for
     TRAD-purpose payments to FATF black/grey-list countries
     (early-warning rule for the upcoming Round-7 #2 TBML spec).
  Reference data `iso20022_high_risk_purpose_codes.csv` ships 28
  ISO 20022 ExternalPurpose1Code values with risk_band classification
  (low/medium/high) and typology mapping; operators read it via
  the dashboard or for reporting. Wired into `examples/eu_bank/aml.yaml`
  as a working demo (Snippet #1 INVS velocity); the EU spec's `txn`
  data contract gained `purpose_code` (nullable) + `counterparty_country`
  (nullable) so the rule executes without crashing on synthetic data
  (rule produces zero alerts on synthetic since purpose_code is NULL,
  and fires correctly when fed real pacs.008 data via PR #56). 16 new
  tests under `TestLibraryYAML` (snippet validity, every snippet must
  be a Pydantic-valid Rule, all carry the iso20022 tag, all 4 known
  IDs present), `TestHighRiskCSV` (schema, every cited code present,
  valid risk_band values, no duplicates), `TestEUBankWiring` (INVS
  rule loaded, purpose_code column declared, tuning_grid present),
  and `TestEndToEnd` (rule fires on planted INVS positives;
  below-threshold yields zero alerts; synthetic data degrades
  gracefully with no crash).
- **ISO 20022 payment-message ingestion** (`data/iso20022/`).
  Round-5 PR #1 of 5. SWIFT completed its MX-only cutover on
  **2025-11-22** (CBPR+ coexistence ended); FedNow/RTP/SEPA Instant
  volumes crossed inflection in Q1 2026. Without pacs.008/pacs.009
  ingestion the framework was unusable on real correspondent
  traffic. New parsers `Pacs008Parser` (customer credit transfer)
  and `Pacs009Parser` (FI credit transfer) consume XML messages
  and produce dicts conforming to the existing `txn` data contract
  — the engine + every downstream rule type works unchanged.
  Per-transaction extraction:
    * `txn_id` — UETR if present, else EndToEndId, else `MsgId-N`
    * `customer_id` — Debtor name (best-effort; production setups
      wire to a customer-id resolver)
    * `amount` / `currency` — `IntrBkSttlmAmt` (Decimal-coerced)
    * `channel` = "wire", `direction` = "out"
    * `booked_at` — `IntrBkSttlmDt` parsed
    * `counterparty_name` / `_country` / `_account` — Creditor block
  Plus travel-rule + audit fields preserved for Round-5 #2's
  validator: `uetr`, `purpose_code`, `debtor_iban`, `debtor_bic`,
  `creditor_bic`, `instructing_agent`, `instructed_agent`,
  `charge_bearer`, `structured_remittance`, `debtor_country`,
  `msg_kind`, `msg_id`. Namespace-agnostic — the same parser
  handles the official `urn:iso:std:iso:20022:tech:xsd:pacs.008.001.13`
  schema or any bank-internal variant. New `iso20022` source type
  in `data/sources.py:resolve_source` recursively walks an XML
  directory; CLI: `aml run SPEC --data-source iso20022 --data-dir
  ./pacs008-files/`. Bundled `sample_pacs008.xml` (3 transactions
  across two debtor banks, mix of UETR/non-UETR + multiple purpose
  codes incl. GDDS, CHAR, INVS) lets operators run the layer
  end-to-end without external feeds. Foundation for Round-5 #2
  (FATF R.16 travel-rule field validator), #3 (purpose-code
  typology library), #4 (pain.001 corporate ingestion), #5
  (pacs.004 return-reason mining), Round-7 TBML, Round-8 RTP/FedNow
  fraud. Implementation note in module docstring: ET.Element
  evaluates falsy when it has no children — bug-trap during
  development; explicit `is None` checks throughout the BIC/IBAN
  extractor path. 34 new tests under `TestPacs008Parser`,
  `TestEdgeCases`, `TestPacs009Parser`, `TestAutoDetect`,
  `TestLoadDirectory`, `TestResolveSource` cover bundled-sample
  field extraction (UETR / IBAN / BIC / purpose / charge-bearer /
  remittance / country), txn_id fallback chain (UETR → EndToEndId
  → `MsgId-N`), namespace-agnostic parsing, malformed XML →
  empty, missing optional fields default cleanly, pacs.009
  shape, auto-detect dispatch, recursive directory walk
  (skipping non-XML), and end-to-end through `resolve_source`.
- **Counterparty-VASP attribution layer** (`vasp/` package,
  `data/lists/sample_walletlabels.csv`). Round-4 PR #4 of 4 — the
  **dark-horse winner** of the Round-4 research scan. Closes the
  gap between "block this OFAC-listed wallet" (already covered by
  `list_match` against `sanctioned_wallets.csv`) and "score the
  counterparty of every crypto transfer based on its full
  attribution profile" — the high-margin Chainalysis / TRM Labs
  / ComplyAdvantage paid capability. **OFAC's January 2026
  designation of UK-registered Zedcex/Zedxion** (tens of billions
  in IRGC-linked flows) and the **Tornado Cash delisting
  (March 2025)** moved the field from "block this address" to
  "score this counterparty's attribution profile" — single-address
  blocklists are no longer sufficient.
  Three abstractions:
  - **`VaspAttribution`** — frozen dataclass with `address`,
    `cluster_name`, `tier` (tier_1/tier_2/tier_3/mixer/ransomware/
    darknet/sanctioned/unknown), `jurisdiction`, `source`, `flags`
    (free-form indicators like `iran_nexus`,
    `pig_butchering_nexus`), and `confidence` (commercial feeds
    can override).
  - **`VaspAttributionStore`** — in-memory address → attribution
    lookup with case-insensitive normalisation, by_tier filter,
    addresses_in_cluster reverse index, last-write-wins on
    duplicates. Production swaps in Redis/Postgres behind the
    same interface.
  - **`enrich_transactions(txns, store)`** — pure function that
    annotates each txn with a `counterparty_vasp` block. Source
    txns are NOT mutated (returns new dicts). Unattributed
    counterparties get `counterparty_vasp: None` so downstream
    rules can treat "unknown" as a distinct case.
  Two adapters in v1 — same `name + load(path) → list[VaspAttribution]`
  shape as the `sanctions/` adapters from PR #44:
  - **`OFACCryptoAddressesSource`** — parses OFAC's text-format
    crypto bundle (`XBT 1addr (Entity)`, `ETH 0xaddr (Entity)`,
    etc) covering 10 supported chains.
  - **`WalletLabelsSource`** — parses the de-facto-standard
    `walletlabels.csv` schema (address, label, category,
    jurisdiction, optional flags) used by Etherscan,
    walletexplorer.com cluster exports, etc.
  Bundled `sample_walletlabels.csv` ships with 6 placeholder
  entries (Coinbase tier_1, Tornado Cash mixer, Zedcex sanctioned,
  Huione sanctioned with `pig_butchering_nexus` flag composing
  with PR #54, a P2P swap tier_3, and a LockBit ransomware
  cluster) so operators can run the layer end-to-end without
  external feeds. **Public-data only** by design — production
  VASP de-risking layers commercial enrichment on top via the
  same interface; the engine doesn't care which provider
  populated the attribution.
  27 new tests under `TestOFACCryptoParser`, `TestWalletLabelsParser`,
  `TestVaspAttributionStore`, `TestEnrichTransactions`,
  `TestLoadIntoStore`, and `TestEndToEndComposition` cover all
  10 supported chains, entity-in-parens parsing, blank/comment
  tolerance, category-to-tier mapping, jurisdiction normalisation,
  flag splitting, case-insensitive address lookup, last-write-wins
  semantics, by_tier filtering, source-txn immutability, address-
  field override, multi-source bulk-load, and end-to-end
  "filter to sanctioned counterparty" demonstration that mirrors
  the shape a `list_match` rule would take.
- **Cyber-enabled fraud / pig-butchering example spec**
  (`examples/cyber_enabled_fraud/aml.yaml`,
  `data/lists/pig_butchering_nexus.csv`). Round-4 PR #3 of 4. New
  typology-focused example spec demonstrating detection of
  pig-butchering / authorised-push-payment fraud — the single
  fastest-growing cyber-enabled fraud typology of 2025-2026 (UK
  40% of all crime; Singapore +61% in two years; FBI IC3 reports
  $5.8 B in US losses 2024). Composes existing primitives, no
  engine changes:
  - `pig_butchering_payout_fan` — `network_pattern` rule (PR #49)
    detecting outbound cluster convergence on crypto on-ramps
    (component_size ≥ 3 inside 2 hops). Catches the classic
    victim → mule → exchange → cash-out shape even when the
    customer doesn't realise it.
  - `ramp_up_then_drain` — `aggregation_window` rule modelling
    the FinCEN advisory pattern: ≥3 priming outbound transfers
    (<$500) to a new beneficiary inside 14 days. Ships with a
    `tuning_grid` so MLROs can sweep the count + sum_amount
    thresholds (PR #50).
  - `pig_butchering_nexus_screening` — `list_match` rule against
    bundled `pig_butchering_nexus.csv` seeded with FinCEN
    Section 311 designations (Huione Group + subsidiaries).
  Citations: FATF Cyber-Enabled Fraud paper (Feb 2026), FinCEN
  FIN-2023-Alert005 (SAR Advisory Key Term: PIG BUTCHERING),
  FinCEN Section 311 Huione (May 2025), 31 CFR § 1020.320 (BSA
  SAR), 31 CFR § 1010.658 (Section 311 special measures). The
  spec composes naturally with PR #45 narrative drafter
  (auto-cite FATF/FinCEN), PR #46 pKYC (new-beneficiary trigger),
  PR #49 explainability (Mermaid subgraph in the STR), PR #43/48
  goAML/AMLA exporters, PR #50 Tuning Lab. No other open-source
  AML framework ships a pig-butchering rule pack today. 9 new
  tests under `TestCyberEnabledFraudSpec` cover spec validation,
  three-logic-type composition, severity routing, `tuning_grid`
  declaration on `ramp_up_then_drain`, FATF + FinCEN
  regulation-ref coverage, bundled-list existence with Huione
  cite, `str_filing` workflow queue + `fincen_sar` form presence,
  and end-to-end run on synthetic data (zero-positives by design
  — synthetic generator doesn't plant pig-butchering shapes; the
  spec must still execute cleanly against the example dataset).
- **Effectiveness Evidence Pack** (`generators/effectiveness.py`,
  `cli.py:effectiveness-pack`, `Rule.aml_priority` spec field).
  Round-4 PR #1 of 2 (paired with the upcoming MRM bundle for
  SR 26-2). FinCEN's **2026-04-07 NPRM** ("Reform of the AML/CFT
  Programs Requirements") moves examiners from "existence" to
  "effectiveness" standards — every BSA-covered institution will
  need to *prove* program effectiveness against the FinCEN
  AML/CFT priorities. This generator builds that proof from
  artifacts the framework already produces. Output is a single
  structured JSON document mapped to the four NPRM pillars:
  - **Risk-assessment alignment** — counts rules with
    `regulation_refs`, severity distribution.
  - **AML/CFT priority coverage** — uses the new
    `Rule.aml_priority` enum field to bucket rules by FinCEN
    priority (corruption, cybercrime, terrorist_financing, fraud,
    transnational_criminal_organization, drug_trafficking,
    human_trafficking, proliferation_financing, other); flags
    unmapped rules as gaps requiring MLRO classification.
  - **Control output quality** — alert volume, false-positive
    proxy (closed_no_action / total dispositions from
    `decisions.jsonl`), narrative-review acceptance rate,
    `tuning_run` event count, RED metric count.
  - **Feedback-loop evidence** — `pkyc_review` count, threshold
    `tuning_run` count, narrative action mix, STR escalation count.
  Every payload also carries an `audit_trail_anchor` block
  (spec_content_hash + decisions_hash + as_of + run_dir) so an
  examiner can independently verify nothing was rewritten between
  the run and the pack. Also ships `render_effectiveness_markdown()`
  which produces a one-page board-ready Markdown rendering with
  ✅/⚠️/❌ icons per finding. Same determinism contract as
  `goaml_xml.py`/`amla_str.py` — same inputs → same JSON bytes.
  CLI:
  ```
  aml effectiveness-pack examples/canadian_schedule_i_bank/aml.yaml \
    --out pack.json --markdown-out pack.md
  ```
  25 new tests cover schema envelope, byte-determinism, gap/satisfied/
  warning status routing, priority bucketing, FP proxy math, narrative
  acceptance rate, tuning-run satisfied-vs-warning logic, RED-metric
  counting, Markdown rendering of pillars + audit anchor, end-to-end
  run-dir round-trip against the bundled CA spec, and Pydantic enum
  validation on the new field.
- **MRM bundle (SR 26-2 / OCC Bulletin 2026-13)**
  (`generators/mrm.py`, `cli.py:mrm-bundle`, `Rule.model_tier`
  + `Rule.validation_cadence_months` spec fields). Round-4 PR #2
  of 2 — pairs with PR #52 Effectiveness Pack.
  The Federal Reserve, FDIC, and OCC formally rescinded SR 11-7
  on **2026-04-17** and replaced it with **OCC Bulletin 2026-13 /
  SR 26-2**, a more risk-based, principles-driven model-risk-
  management framework that explicitly re-confirms AML transaction-
  monitoring rules and sanctions-screening tools meet the "model"
  definition. Banks have a 12-month implementation window. This
  generator emits the per-rule MRM dossier the bank's second-line
  model-validation team needs:
  1. **Inventory** — id, name, severity, tier, cadence,
     evaluation_mode, classification status (explicit vs defaulted).
  2. **Conceptual soundness** — auto-generated narrative + structured
     logic block + regulation_refs (the model is documented from
     the spec, not hand-written by the validator).
  3. **Implementation** — engine version, code path the rule runs
     through, spec content hash, evaluation mode.
  4. **Validation evidence** — pulls every `tuning_run` event for
     this rule from `decisions.jsonl` (so `aml tune --audit-run-dir
     <run>` becomes the bank's auditable validation evidence). When
     no tuning runs exist the dossier prints a one-liner pointing
     the validator at the right command.
  5. **Ongoing monitoring** — alert count this run, cadence months,
     next-validation-due date (cadence ahead of as_of).
  6. **Audit-trail anchor** — spec_content_hash + decisions_hash +
     as_of + run_dir.
  Each rule produces a Markdown document + JSON sidecar. A spec-wide
  `inventory.json` aggregates every rule's tier + cadence +
  classification status (sorted high → medium → low). Defaults:
  `model_tier` defaults to `"low"` with `tier_classification_status:
  "defaulted_to_low"` so the second-line sees where they need to
  classify explicitly; `validation_cadence_months` defaults by tier
  (high=12, medium=18, low=24).
  Pairs with `generators/effectiveness.py` (PR #52): Effectiveness
  Pack speaks to the first line + senior management ("does the
  programme work?"); MRM bundle speaks to the second-line model-
  validation team ("how was each rule validated?"). Different
  audiences, different review paths — intentionally **not** bundled
  into one PR.
  CLI:
  ```
  aml mrm-bundle examples/canadian_schedule_i_bank/aml.yaml \
    --out-dir mrm/  # one Markdown + JSON per rule + inventory.json
  aml mrm-bundle examples/canadian_schedule_i_bank/aml.yaml \
    --rule structuring_cash_deposits --out-dir mrm/  # single rule
  ```
  28 new tests under `TestSpecFields`, `TestTierCadenceResolution`,
  `TestDossierSections`, `TestInventory`, `TestRendering`,
  `TestRunDirRoundTrip`, and `TestCadenceTable` cover spec field
  validation (invalid tier rejected, cadence bounds enforced),
  tier defaulting + classification status reporting, default-cadence
  table, dossier section composition (logic capture, regulation
  refs, validation evidence routing by rule_id), Markdown rendering
  (guidance header, defaulted-to-low warning, validation evidence
  display), spec-wide inventory aggregation (by_tier + by_status
  counters, sort order), and end-to-end run-dir round-trip against
  the bundled CA spec (10 dossier files + inventory written).
- **Tuning Lab Streamlit page** (`dashboard/pages/23_Tuning_Lab.py` +
  `dashboard/tuning_state.py`): UI surface for `aml tune` (PR #50). MLRO
  picks a tunable rule, optionally uploads a labels CSV
  (`customer_id,is_true_positive`) for precision/recall scoring, and
  the page renders the per-scenario table + a precision/recall scatter
  (Plotly bubble chart sized by alert count, coloured by F1) when
  labels are present. Best-F1 scenario gets called out automatically.
  The "promote a scenario" panel renders a YAML spec patch (rule
  fragment with patched fields only) the operator can download and
  merge into `aml.yaml` to promote the candidate threshold; a
  `# Spec patch produced by the Tuning Lab` header reminds the user
  to re-run `aml validate` after merging. The page also writes a
  `tuning_run` event to the current session's run dir whenever a
  sweep is executed (toggle in the sidebar) — every threshold
  consideration is part of the audit trail. Page mapped into
  `audience.py` for `vp`, `director`, `manager`, `pm` personas. Round-4
  PR #1 — closes the "no UI for the new CLI" gap that PR #47 closed
  for narratives + pkyc. 15 new tests under `TestParseLabelsCSV`,
  `TestRulesWithTuningGrid`, `TestScenariosToTable`, `TestBestScenario`,
  `TestRenderSpecPatch`, and `TestEndToEnd` cover label parsing
  (truthy/falsy variants, missing column, empty rows), tunable-rule
  filtering, table flattening with and without metric columns, best-by
  metric ranking, YAML round-trip of the spec patch, and an
  end-to-end sweep → table → patch composition against the bundled
  Canadian Schedule I example. None of them import streamlit.
- **Tuning Lab — threshold sweep with shadow diff + precision/recall**
  (`engine/tuning.py`, `cli.py:tune`, `Rule.tuning_grid` spec field).
  Closes Round-3 plan (4 of 4 PRs shipped). Operators tune AML rule
  thresholds today by guesswork plus quarterly reviews; the Tuning
  Lab makes it cheap and defensible. Declare a `tuning_grid` on a
  rule (additive, optional spec field — engine ignores it at runtime,
  no breaking change), then `aml tune SPEC --rule RULE_ID` sweeps
  every parameter combination over a fixed dataset and reports
  per-scenario alert-count delta vs the production thresholds plus
  added/removed customer-id sets (shadow diff). When the operator
  passes `--labels labels.csv` (columns `customer_id,is_true_positive`)
  every scenario also gets precision / recall / F1 scored against the
  labels and the CLI surfaces the best-F1 scenario.
  Same dataset + same seed across the grid → apples-to-apples — the
  determinism contract that backs `test_run_is_reproducible` extends
  to the sweep. The audit ledger gets a new `Event.TUNING_RUN` event
  appended to the target run's `decisions.jsonl` (when
  `--audit-run-dir` is passed) so any threshold change has a
  documented decision trail. Internal mechanics: clones the rule
  via Pydantic `model_copy(update=...)` with deep-copied dict patches
  (no mutation of the source spec); reuses the engine's `_execute_*`
  helpers so any new rule logic type added to the engine works in
  the tuner without changes here. CLI:
  ```
  aml tune examples/canadian_schedule_i_bank/aml.yaml \
    --rule structuring_cash_deposits \
    --labels labels.csv --out tuning.json \
    --audit-run-dir .artifacts/run-20260427T141428Z
  ```
  The Canadian Schedule I example spec now ships with a `tuning_grid`
  on the `structuring_cash_deposits` rule (count × sum_amount sweep)
  so `make demo` can show the feature without spec edits. 25 new
  tests under `TestGridCombinations`, `TestSetByPath`, `TestMetrics`,
  `TestSweepRule`, `TestAuditIntegration`, `TestTuningRun`, and
  `TestSpecDeclaredGrid` cover Cartesian expansion, deep-path
  patching against a frozen rule, original-spec immutability,
  precision/recall/F1 edge cases (no predictions, no positives,
  no labels), baseline alignment with `run_spec`, monotonic
  alert-count vs threshold, audit-event emission, and end-to-end
  spec-declared grid with synthetic data.
- **Network-pattern alert explainability** (`engine/explain.py`,
  runner subgraph capture, queue page integration). Each
  `network_pattern` alert now carries the actual matched
  subgraph in `alert["subgraph"]`: nodes (with hop distance from
  the seed), undirected edges (with linking attribute + weight),
  and a SHA-256 `topology_hash` that's identical for two alerts
  on the same shape of subgraph (cluster key for duplicate
  detections — analysts can collapse 50 customers caught in one
  ring instead of triaging each independently). The new
  `engine/explain.py` provides `explain_network_alert(alert) →
  ExplainPayload` (pure function, no IO) plus `to_mermaid(payload)`
  for dashboard rendering. The Analyst Review Queue page (PR #47)
  now renders the matched subgraph as a Mermaid graph for any
  network_pattern case, with a one-line summary
  (`Pattern 'component_size' fired on C0001: 3 entity(ies)
  reachable within 2 hop(s), 2 unique counterpart(ies). Linking
  attributes: device_id×1, phone×1.`) and the topology hash
  prefix as an audit anchor. Round-3 PR #4 of 4 — the **dark-horse
  winner** of the Round-3 research scan: graph alerts are
  notoriously hard to defend in front of regulators
  ("the recursive CTE matched a 4-hop ring"); shipping this gives
  the framework an answer to "how is this not a black box?" that
  no other open-source AML project has. The runner enrichment is
  backward-compatible: alerts now carry an extra `subgraph` field
  but the existing 5 `TestNetworkPattern` tests still pass
  unchanged. 20 new tests under `TestExplainNetworkAlert`,
  `TestToMermaid`, `TestExplainPayloadModel`,
  `TestRunnerSubgraphCapture`, `TestDecimalHandling` cover happy
  path / missing subgraph raise / Mermaid escaping / render cap /
  seed fallback / triangle component round-trip / topology hash
  determinism across seeds in the same component / DuckDB Decimal
  coercion.
- **AMLA harmonised STR profile** (`generators/amla_str.py`,
  `cli.py:export-amla-str`): emits an AMLA RTS-aligned JSON
  payload from a finalised run directory. The EU's Anti-Money
  Laundering Authority (AMLA) is finalising a single harmonised
  SAR/STR template across the bloc — the Regulatory Technical
  Standards (RTS) for the SAR template have a delivery deadline
  of **2026-07-10**. This generator targets the February 2026
  consultation draft so EU obliged entities have a day-zero
  adapter the moment the RTS ratifies. Maps the framework's
  primitives to AMLA fields: `rule_id` + `tags` →
  `amla_typology_codes` (Annex II placeholder set: STR-001
  Structuring … STR-008 Virtual Asset Layering),
  `regulation_refs` → `indicators[].source_regulation`,
  customer → `subject` (natural_person vs legal_entity branch
  with optional `lei` + `beneficial_owner_chain`),
  cross-border counterparty → `cross_border_indicator`. Every
  payload carries a prominent `_draft_warning` field plus a
  `conformance` block listing which AMLA-mandatory fields the
  spec successfully populated and which need analyst fill-in
  (so auditors get one-shot view of what's automated vs manual).
  Same determinism contract as `goaml_xml.py` — same inputs +
  same `submission_date` → identical JSON bytes. CLI:
  ```
  aml export-amla-str spec.yaml --lei 529900T8BM49AURSDO55 \
    --sector CREDIT_INSTITUTION --out amla_str.json
  ```
  Round-3 PR #2 of 4. Sources for the RTS draft cited in
  module docstring; 26 new tests under `TestTypologyMapping`,
  `TestBuildReport`, `TestPayload`, and `TestRunDirRoundTrip`
  cover typology hint matching, natural-person vs legal-entity
  subject branches, beneficial-ownership pass-through, cross-
  border indicator computation, draft-warning emission,
  conformance counting (populated vs unmapped), byte-determinism,
  and end-to-end payload generation against the EU bank + crypto
  VASP example specs.
- **Analyst Review Queue dashboard page**
  (`dashboard/pages/22_Analyst_Review_Queue.py` +
  `dashboard/queue_state.py`): a triage view that composes the new
  `narratives/` and `pkyc/` packages so analysts can review draft
  STR/SAR text + active pKYC triggers + recalculated risk ratings
  in one place — instead of reading JSON files. Per-case actions
  (Accept / Amend / Reject / Escalate-to-STR) write into the
  existing `AuditLedger` via two new event types
  (`Event.NARRATIVE_REVIEW`, `Event.PKYC_REVIEW`); the append-only
  hash chain means every queue action is permanently part of the
  run's audit trail. Filtering by severity, "only with pKYC
  triggers", and "only with rating changes" keeps the page
  responsive for large case loads (50-row render cap with
  filter-to-narrow guidance). Page is mapped into `audience.py`
  for `analyst` and `manager` personas. Round-3 PR #1 of 4 — closes
  the "no UI surface" gap that made PR #45 + PR #46 feel half-shipped.
  18 new tests under `TestBuildQueueRows`, `TestActionMapping`,
  `TestRecordDecision`, `TestAuditChainIntegration`, and
  `TestEndToEndWithRealRun` cover queue composition, narrative
  attachment, country-risk + pattern trigger routing, rating-change
  detection, audit-ledger hash-chain integration, and a
  finalised-run round-trip — none of them import streamlit.
- **pKYC trigger engine** (`pkyc/` package): Perpetual Know Your
  Customer — events trigger re-review instead of the calendar.
  Five built-in detectors: `SanctionsHitDetector` (consumes
  `SyncResult.added` from PR #44 — only newly-added sanctions
  entries fire, since pre-existing entries were already screened
  at onboarding), `AdverseMediaDetector`, `CountryRiskDetector`
  (FATF black/grey lists), `TransactionPatternDetector` (alert
  count over lookback window crosses threshold), `StaleKYCDetector`
  (calendar fallback with risk-rating-keyed thresholds: critical
  180d, high 365d, medium 730d, low 1095d). Each detector is **pure**
  — same `ScanContext` in → same triggers out — so callers can A/B
  detector configurations without surprise. The `RiskRecalculator`
  composes triggers into a new rating (one critical → critical;
  ≥1 high → bump one rung capped at high; ≥2 mediums → bump one
  rung) so every escalation has an auditable trigger trail. The
  scan engine is side-effect free: it returns a `TriggerScan` with
  `triggers` + `rating_changes`; the caller decides whether to
  persist back to source. CLI:
  ```
  aml pkyc-scan SPEC --high-risk-countries RU,KP,IR \
    --sanctions-added-file ofac-delta.json \
    --alert-threshold 3
  ```
  Composes with PR #44 (sanctions feeds): when a daily
  `sanctions-sync` produces a `SyncResult` with new entries, feed
  it into `pkyc-scan` and any of your customers matching a brand-new
  designation gets flagged for escalation **on the same business day**
  — no waiting for the next calendar review. 37 new tests cover
  trigger model validation, each detector's match logic +
  case-insensitive matching + duplicate-name handling + severity
  override, recalculator escalation ladder + rung-capping, scan
  aggregation, JSON serialisation round-trip, custom-detector
  selection, and end-to-end composition with the sanctions package
  cache.
- **Narrative drafter with pluggable LLM backends** (`narratives/`
  package): structured STR/SAR drafting with three backends in v1 —
  `TemplateBackend` (deterministic, dependency-free, default;
  wraps the existing `generators/narrative.py` text), `OllamaBackend`
  (local-first, calls a running Ollama server with `format=json` so
  PII never leaves the host), and `OpenAIBackend` (opt-in, requires
  `OPENAI_API_KEY`, refuses to instantiate without it). All backends
  produce a `DraftedNarrative` Pydantic model with structured fields:
  `narrative_text`, `key_findings`, `citations` (each tagged with
  `rule_id` so analysts can verify the citation links back to a
  regulation reference the rule actually declared — not text the
  model invented), `recommended_action`
  (`file_str|close_no_action|investigate_further`), and `confidence`
  ∈ [0,1]. The Ollama prompt explicitly instructs the model to
  cite **only** from the provided regulation_refs; hallucinated
  citations are the worst failure mode for a regulator-facing
  artifact. Backend HTTP IO is isolated to a single `_call_*`
  function per backend so unit tests patch one symbol and run
  network-free. Failures (server down, malformed JSON, schema
  mismatch) raise `NarrativeError` so callers can decide between
  fallback to template or surfacing to the analyst. CLI:
  ```
  aml draft-narrative SPEC CASE_ID --backend template|ollama|openai
  ```
  29 new tests cover model validation (`extra="forbid"`, frozen,
  confidence range, action enum), template determinism + severity
  routing, mocked Ollama happy-path / non-JSON / empty / schema
  violations, OpenAI key gating + happy path, factory dispatch, and
  run-dir round-trip with txn-window filtering.
- **Sanctions feed adapters** (`sanctions/` package): pluggable
  upstream-feed parsers + content cache that keep `data/lists/*.csv`
  fresh without operator scripting. Three adapters ship in v1:
  `OFACAdvancedXMLSource` (OFAC SDN Advanced XML),
  `EUConsolidatedSource` (EU FSF consolidated XML), and
  `ComplyAdvantageWebhookSource` (ComplyAdvantage Monitor webhook
  payloads, with HMAC-SHA256 signature verification — no live API
  call, since the webhook delivery model is push-based). Each adapter
  splits cleanly into `fetch(url) → bytes` (only IO surface) and
  `parse(payload) → list[SanctionEntry]` so unit tests run
  network-free. `SanctionsCache` writes a canonical CSV
  (rows sorted) and a sidecar `.cache/<name>.meta.json` with
  SHA-256 + row count + fetched_at; re-syncing the same payload is a
  no-op (`unchanged=True`). Otherwise `SyncResult` reports `added` /
  `removed` deltas vs the previous on-disk content so operators can
  preview before merging into production lists. CLI:
  ```
  aml sanctions-sync ofac --from-file sdn_advanced.xml
  aml sanctions-sync eu  --from-file euConsol.xml
  ```
  Closes the loop with `list_match` rules — refreshed CSV is consumed
  by the engine on next run with no spec change. 31 new tests under
  `TestOFACParser`, `TestEUParser`, `TestComplyAdvantageParser`,
  `TestSanctionsCache`, `TestSyncOrchestrator`,
  `TestCSVCompatibleWithEngine` cover XML parsing, party-type
  mapping, country precedence, alias collection, JSON parsing, HMAC
  verify accept/reject paths, idempotent re-pull, delta-diff, and
  engine-loader compatibility.
- **goAML 5.0.2 XML exporter** (`generators/goaml_xml.py`,
  `cli.py:export-goaml`): emit UNODC-format STR/SAR XML from a finalised
  run directory. One `<report>` per case, batched under a `<reports>`
  root. Maps the framework's primitives to goAML in the obvious way:
  `rule_id` → `<report_indicators>/<indicator>`, `regulation_refs` →
  `<reason>`, `customer` → `<t_person>` under `<t_from_my_client>`,
  transactions in the alert window → `<transaction>`, channel → goAML
  funds code (cash/wire/crypto → K/A/X). Currency is auto-derived from
  `program.jurisdiction` (CA→CAD, US→USD, EU→EUR, UK→GBP). Output is
  byte-deterministic for fixed inputs — cases sort by `(rule_id,
  case_id)`; transactions sort by `(booked_at, txn_id)` — so the same
  spec + same run + same `submission_date` produces identical XML
  bytes. CLI:
  ```
  aml export-goaml examples/canadian_schedule_i_bank/aml.yaml \
    --out goaml.xml --report-code STR --rentity-id 12345
  ```
  goAML is the de-facto FIU reporting standard accepted by 60+ FIUs;
  the EU AMLA ITS draft (due July 2026) extends this same schema, so
  AMLA-specific fields will land as deltas on this exporter rather than
  as a rewrite. PII is never persisted in the audit ledger — the
  exporter re-resolves customer + txn data through the spec's data
  source at export time. 14 new tests under `TestGoAMLExporter` cover
  root shape, header fields, currency-by-jurisdiction, transaction
  filtering by customer + window, indicator/tag emission, regulation
  reference inclusion, byte-determinism, run-dir round-trip, missing
  `cases/` raises, funds-code mapping, and `additional_info` content.
- **`rule.evaluation_mode` field** (`spec/models.py`,
  `schema/aml-spec.schema.json`): each rule can now declare
  `batch | streaming | both` (default `batch`). v1 engine still executes
  batch only — the field is metadata that records institution intent so an
  operator can route to a streaming runner at deployment time. Lays
  groundwork for the Kafka/Kinesis evaluator (research scan #2). 5 new
  tests under `TestEvaluationMode` confirm default, accepted values,
  rejected invalid value, and that setting `streaming` does not change
  the run output (back-compat invariant).
- **Crypto VASP example spec** (`examples/crypto_vasp/aml.yaml`): minimal AML
  spec for a Virtual Asset Service Provider. Demonstrates the framework's
  crypto coverage with four rules: stablecoin layering velocity (48h
  window, $20k aggregate), sanctioned-wallet screening (`list_match` against
  bundled `sanctioned_wallets.csv`), nested-wallet ring detection
  (`network_pattern` over `resolved_entity_link`), and a single-day swap
  threshold mirroring LVCTR. Built around TRM Labs' 2026 Crypto Crime
  Report finding that stablecoins were ~84% of fraud-scheme inflows in
  2025 with hold times collapsing under 48h. 3 new tests under
  `TestCryptoVASPSpec` lock the spec shape and bundled wallet list.
- **Entity-resolution layer** (`engine/entity_resolution.py`): runtime
  builds a `resolved_entity` view + `resolved_entity_link` table inside
  the engine's DuckDB. Linking attributes (`phone`, `email`, `device_id`,
  `address`, `tax_id`, `wallet_address`) are recognized when present on
  the customer contract — pairs of customers sharing a non-null value
  appear as edges with attribute + weight. v1 uses customer_id as the
  resolved entity; the table is the substrate for the upcoming
  `network_pattern` rule type. Wired into the runner so every spec gets it
  for free; no spec changes required. Production deployments swap in a
  real ER service (Senzing, Quantexa) by overriding `resolve_entities`.
- 5 new tests under `TestEntityResolution` cover: empty-spec stub, shared
  phone, shared device_id, NULL-doesn't-link semantics, view shape.
- **`network_pattern` rule type** (`engine/runner.py`, `spec/models.py`,
  `schema/aml-spec.schema.json`): 5th rule logic type. Walks the
  entity-resolution graph (`resolved_entity_link`) via DuckDB recursive
  CTE up to `max_hops` away from each customer and flags those whose
  ego-network satisfies a `having` clause. Two patterns supported in v1:
  `component_size` (mule herd / nested-account ring) and
  `counterparty_count` (hub-and-spoke / synthetic-identity rings).
  Spec example:
  ```yaml
  logic:
    type: network_pattern
    pattern: component_size
    max_hops: 2
    having: { component_size: { gte: 3 } }
  ```
- 5 new tests under `TestNetworkPattern` cover three-customer ring,
  isolated customer non-fire, two-customer pair, no-links, and
  hub-and-spoke counterparty-count pattern.

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
- **`paths.py` — single source for `PROJECT_ROOT`, `PACKAGE_ROOT`,
  `SCHEMA_PATH`, `REFERENCE_LISTS_DIR`.** `Path(__file__).resolve().parents[3]`
  was repeated in `spec/loader.py`, `dashboard/state.py`, and
  `api/main.py` with a brittle index that breaks if the package gets
  nested deeper. `engine/runner.py:_load_reference_list` carried its own
  `parents[1]` for `data/lists`. All four now import from one module.
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
