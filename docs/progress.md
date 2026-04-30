# Project Progress

Snapshot of where the AML Open Framework is as of 2026-04-29. This document is a fact-based audit of what's shipped, not a roadmap or marketing piece. For "what's next?" see [`getting-started.md`](getting-started.md) and the [Changelog](../CHANGELOG.md).

---

## At a Glance

| Metric | Round 6 (2026-04-27) | Round 7 closed | Dashboard plan closed (2026-04-29) |
|---|---|---|---|
| Source code | 19,642 LOC across 18 modules | + ~2,500 LOC (compliance/, metrics/outcomes, generators/audit_pack, data/psd3) | + ~700 LOC (dashboard helpers + integrations) |
| Tests | 991 | + ~110 | 1,161 passing |
| Test files | 34 | 39 | 43 |
| Example specs | 7 | 9 (+ trade_based_ml + uk_app_fraud) | 9 |
| Unique regulation citations | 61+ | ~75+ | ~75+ |
| Dashboard pages | 24 | 24 (integration deferred) | 24 (every Round-6/7 module surfaced) |
| Merged PRs (cumulative) | 18 (#46–#73) | + #74–#79 | + #80–#87 (8-PR dashboard plan) |

---

## Module Surface

```
src/aml_framework/
├── api/              FastAPI REST layer (JWT auth, multi-tenant DB, rate limiting)
├── cases/            Investigation aggregator, SLA timer, STR bundling (Round 6)
├── dashboard/        24-page Streamlit web app (mobile-responsive, multi-tenant)
├── data/             Synthetic generator + 8 source loaders + ISO 20022 parser
│   ├── iso20022/     pacs.008, pacs.009, pain.001, pacs.004 ingestion (Round 5)
│   └── lists/        Sanctions, adverse media, sanctioned wallets, purpose codes
├── engine/           Rule executor on DuckDB, audit ledger with SHA-256 hash chain
├── generators/       SQL, DAG stubs, control matrix, STR narratives, board PDF,
│                     goAML XML, AMLA STR, MRM bundle, effectiveness pack
├── integrations/     Jira, Slack/Teams, SIEM/CEF connectors
├── metrics/          Metric evaluation engine + RAG bands + audience routing
├── models/           ML scoring callables for python_ref rules + travel-rule validator
├── narratives/       LLM-backed narrative drafting (Ollama, OpenAI backends)
├── pkyc/             Perpetual KYC trigger engine
├── sanctions/        OFAC SDN refresh + fuzzy match
├── spec/             JSON Schema + Pydantic validation + reusable rule library
└── vasp/             Public-data VASP attribution (Chainalysis alternative)
```

---

## Round-by-Round Delivery

### Round 5 — Payment Rails Ingestion (5 PRs, ~16 days)

Goal: ingest the messages banks actually move money with, after SWIFT's MX-only cutover (2025-11-22).

| PR | Feature | Driving signal |
|---|---|---|
| #56 | ISO 20022 `pacs.008` + `pacs.009` ingestion adapter | SWIFT MX-only cutover |
| #57 | FATF R.16 Travel Rule field validator (`python_ref` callable) | FATF Feb 2026 plenary deficiency call-out |
| #58 | ISO 20022 purpose-code typology library (4 reusable snippets) | ExternalPurpose1Code now mandatory |
| #59 | `pain.001` corporate-batch ingestion | Wolfsberg Feb 2026 correspondent-banking guidance |
| #60 | `pacs.004` payment-return + return-reason mining library (3 snippets) | UK PSR APP-fraud reimbursement (Apr 2026 full effect) |

**Result**: framework can natively consume every major ISO 20022 message type. Travel-rule completeness is automated. Two reusable spec-library files ship 7 typology rule snippets keyed to FATF / FinCEN / UK PSR / Wolfsberg guidance.

### Round 6 — Case Management as First-Class Surface (5 PRs, ~17 days)

Goal: make investigation (not alert) the unit of analyst work, per FinCEN's 2024 effectiveness rule.

| PR | Feature | Driving signal |
|---|---|---|
| #61 | Investigation aggregator (`cases/aggregator.py`) | FinCEN NPRM measures effectiveness per investigation |
| #62 | Multi-tenant dashboard surfacing (sidebar selector) | API had it; dashboard didn't |
| #63 | SLA timer + escalation engine (`cases/sla.py`) | FCA Mar 2026 Dear CEO letter on SAR backlogs |
| #64 | Case-to-STR auto-bundling (`cases/str_bundle.py`) | Wolfsberg Feb 2026 "submission-ready packages" |
| #65 | Investigations dashboard page #24 | Operator surface for the above |

**Result**: cases now aggregate into investigations with deterministic IDs. Live SLA tracking surfaces backlog state per-queue. Self-contained STR ZIPs bundle narrative + goAML XML + Mermaid diagrams + manifest hash. New dashboard page consolidates the workflow.

### Workflow Polish (4 PRs)

| PR | Feature |
|---|---|
| #67 | README refactor 582 → 123 lines + Getting Started guide + Dashboard Tour + Jurisdictions doc |
| #69 | `aml --help` typer/click compatibility fix; crypto_vasp doc gap |
| #70 | Mobile-responsive dashboard overlay (closes #66) |
| #71 | Workflow audit: executive font scale + 4 pages made interactive + missing pages registered |
| #72 | Synthetic data enriched with ISO 20022 fields + planted INVS positive |

**Result**: new-user onboarding path is 15 minutes. Mobile viewports work. Executive personas (SVP/CTO/CCO/VP/Director) get auto-scaled fonts. Default `aml run --seed 42` demo now exercises all Round 5/6 features.

### Round 7 — Research-driven defensive layer (5 PRs, ~21 days)

Goal: ship the top-5 features ranked by impact ÷ effort in the [2026-04 competitive positioning research](research/2026-04-competitive-positioning.md). All five anchored to a 2026 regulatory clock the research surfaced as load-bearing.

| PR | Feature | Driving signal |
|---|---|---|
| #74 | Regulatory-change diff watcher (`compliance/regwatch.py`) | FinCEN BOI Mar 2025 narrowing + April 2026 NPRM 12-month tail |
| #75 | AMLA STR/RTS effectiveness telemetry pack (`metrics/outcomes.py`) | AMLA RTS due 2026-07-10 + FinCEN NPRM enumerates same metrics |
| #76 | TBML + UK APP-fraud example specs | FATF Feb 2026 plenary + PSR Apr 2026 full-effect reimbursement |
| #77 | PSD3 / Verification-of-Payee adapter (DRAFT) | PSD3/PSR Council/Parliament agreement end-Q2 2026; VoP applies +24 months |
| #78 | FINTRAC pre-examination audit pack (`generators/audit_pack.py`) | FINTRAC January 2026 examination manual update |

**Result**: framework now has a defensive layer that sits *above* the spec — drift detection against silently-changing regulator pages, regulator-format effectiveness JSON, jurisdiction-templated examination evidence packs. This is the layer commercial vendors don't ship because they own the rule library themselves; the framework needs it precisely because it doesn't.

**Cross-feature integration** (closed in Dashboard Workflow & Design plan, 2026-04-28):
- Dashboard page surfacing the outcomes funnel ✅ Phase B-2
- Dashboard panel for regwatch drift findings ✅ Phase B-2
- One-click audit-pack download from Audit & Evidence ✅ Phase B-3
- VoP outcomes panel on Sanctions Screening ✅ Phase B-3

### Dashboard Workflow & Design plan (8 PRs, 2026-04-27 → 2026-04-28)

Goal: ensure proper workflow + design across the dashboard. Audit identified 5 hidden modules, broken cross-page navigation, muddled persona arcs, and crash-prone empty-state behavior.

| PR | Phase | Feature |
|---|---|---|
| #80 | A | Cross-cutting helpers: `link_to_page`, `read_param`, `consume_param`, `severity_color`, `sla_band_color`, `empty_state` |
| #81 | B-1 | SLA timer + STR-bundle download on case-facing pages (#4, #21, #17) |
| #82 | B-2 | Effectiveness funnel on Executive Dashboard + regulation-drift panel on Audit & Evidence |
| #83 | B-3 | FINTRAC audit-pack download on Audit & Evidence + VoP outcomes on Sanctions Screening |
| #84 | C | Cross-page drill-downs / deep links — Alert Queue + Network Explorer + Customer 360 + Executive |
| #85 | D | Persona workflow rebalance — every persona ≤8 pages, coherent task arcs |
| #86 | E | Empty-state defenses on engine-side pages (#5, #10, #11) + design consistency test guards |
| #87 | E follow-up | `risk_color()` resolver + 7 pages migrated off inline color dicts; test ALLOWED set drained |

**Result**: every Round-6/7 module is now reachable from the dashboard (was the original Phase B goal). Cross-entity drill-downs eliminate the audit's worst dead-ends (~20-30s saved per drill, dozens per shift). Three pages that crashed on degenerate specs now degrade gracefully. Color/SLA palette has a single source of truth — any new inline color dict fails CI. Tests grew 1089 → 1161 across the 8 PRs.

---

## What the Framework Does Today

### For the policy author (CCO / MLRO)
- Authors a versioned `aml.yaml` — every rule cites a specific regulation
- Two-layer validation (JSON Schema + Pydantic cross-references)
- Reusable rule snippet library (`spec/library/`) for ISO 20022 typologies
- Reviewable diff between spec versions (`aml diff`)

### For the data engineer
- Generates SQL, DAG stubs, and control matrix from spec
- 8 supported data sources: synthetic, CSV, Parquet, DuckDB, S3, GCS, Snowflake, BigQuery
- Native ISO 20022 ingestion (pacs.008/009/pain.001/pacs.004)
- Schema validation at load time

### For the analyst (L1/L2)
- 24-page web dashboard with persona-filtered navigation
- Investigation-level review (not just alerts)
- Per-case live SLA + escalation recommendations
- Network-pattern explainability with Mermaid diagrams
- One-click STR submission bundle

### For the auditor / regulator
- Append-only decisions ledger with SHA-256 hash chain
- Reproducible runs (same spec + data + seed → identical hashes)
- Regulator-ready evidence ZIP (`aml export`)
- goAML 5.0.2 XML and AMLA RTS JSON exports

### For the ML modeler
- `python_ref` rule type with security gate (callables restricted to `aml_framework.models.*`)
- MRM bundle generator (SR 26-2 / OCC Bulletin 2026-13 dossiers)
- Tuning Lab — threshold sweep with shadow diff + precision/recall
- Effectiveness Evidence Pack (FinCEN April 2026 NPRM artifact)

### For the operations team
- Multi-tenant dashboard (single process, multiple programs)
- Mobile-responsive layout
- REST API with JWT/OIDC auth, rate limiting, run persistence
- Integrations: Jira, Slack/Teams, SIEM/CEF
- Docker + Helm chart for K8s deployment

---

## Shipped Capabilities by Regulatory Regime

| Regulator / regime | What's covered |
|---|---|
| **FinCEN BSA** (US) | 6-pillar mapping including the April 2026 proposed 6th pillar; SAR/CTR exports; investigation-aggregation per the 2024 effectiveness rule |
| **FinCEN April 2026 NPRM** | Effectiveness Evidence Pack generator (`aml effectiveness-pack`) |
| **OFAC** | Fuzzy + exact name screening; SDN list refresh from upstream XML |
| **FINTRAC + OSFI** (CA) | PCMLTFA section-level citations; STR/LCTR/EFTR; OSFI B-8 alignment; TD case-study patterns spec |
| **AMLD6 + EBA** (EU) | Article-level citations; AMLA RTS JSON draft (effective July 2026); 5-year retention |
| **FCA + POCA + PSR** (UK) | UK SAR via NCA; PSR APP-fraud reimbursement signals (return-reason mining); FCA Mar 2026 SAR-backlog response |
| **FATF** | R.16 Travel Rule validator; R.15-16 crypto adaptations (`crypto_vasp` spec); Feb 2026 Cyber-Enabled Fraud typologies |
| **Wolfsberg** | Feb 2026 correspondent-banking gaps (pain.001 ingestion, submission-ready STR packages) |
| **SR 26-2 / OCC 2026-13** | MRM bundle generator for python_ref models |

---

## Test Coverage

```
test_engine.py                  108  Engine, audit ledger, hash chain, all 5 rule types
test_iso20022.py                 34  pacs.008/009 parsing
test_pain001.py                  29  Corporate batch ingestion
test_pacs004.py                  36  Payment-return ingestion + library
test_iso20022_purpose_codes.py   16  Purpose-code library + planted positive
test_travel_rule.py              29  FATF R.16 validator
test_cases_aggregator.py         34  Investigation grouping (3 strategies)
test_cases_sla.py                25  SLA classification + escalation + backlog
test_cases_str_bundle.py         23  Per-investigation ZIP determinism
test_dashboard_workflows.py      15  Audience map + executive scale + page registration
test_dashboard_tenants.py        26  Multi-tenant config validation
test_dashboard_mobile_css.py     10  Mobile responsive overlay
test_e2e_dashboard.py            30  Playwright — every page renders
test_e2e_dashboard_mobile.py      9  Mobile viewports (375/414/768)
test_dashboard_investigations    9   Investigations page wiring
test_docs_links.py               19  Link rot prevention
test_api.py                      54  FastAPI auth, runs, validation, rate limiting
test_data_sources.py             37  All 8 source types
test_generators.py               26  All export formats
test_metrics.py                  30  Metric evaluation + RAG + audience
test_integrations.py             24  Jira, Slack/Teams, SIEM/CEF
test_spec.py                     28  Spec validation + EU/UK runs + AMLD6 alignment
test_performance.py               2  10k+ row engine throughput
… plus 19 other test files       … 
```

Total (post Round 7 + dashboard plan): 1,161 tests passing, 43 test files.

Dashboard-plan tests added (2026-04-27 → 2026-04-28):
```
test_dashboard_components_helpers.py   21  Phase A — 6 helpers + namespace tests
test_dashboard_sla_integration.py      18  Phase B-1 — SLA on 3 pages
test_dashboard_outcomes_panel.py       13  Phase B-2 — funnel + regwatch
test_dashboard_audit_pack_button.py    11  Phase B-3 — FINTRAC + VoP panel
test_dashboard_drill_downs.py          17  Phase C — deep-link wiring
test_dashboard_design_consistency.py   10  Phase E — page_header + empty_state + resolvers
```

---

## What's NOT in the Framework (by design)

These are documented "won't ship" decisions, not gaps:

- **Generative AI rule-authoring** (English → YAML rule). Would destroy the "human-readable spec written by a human" moat that's the framework's whole differentiation.
- **Native graph DB backend** (Neo4j / TigerGraph). DuckDB-with-graph-views is fast enough for FI-scale datasets, and "one binary, one DuckDB file" deployability is the moat.
- **Alert-scoring ML model in-tree**. Would erode the deterministic re-run guarantee that the MRM bundle (PR #53) builds on. We document the `python_ref` seam; institutions ship their own model.

See `memory/project_round5to9_plan.md` (private) for the full "three new traps" rationale.

---

## Open Items

- Issue #66 — closed 2026-04-27 (PR #70 mobile-responsive)
- Issue #68 — **in progress** (2026-04-29 docs-sweep PR open). The mobile half
  was satisfied by `#66` closed (PR #70). The docs-sweep half is now in progress:
  static site stats corrected (test count, competitive-positioning scope/date),
  Round&nbsp;7 features marked as shipped in competitive-positioning.html, and
  unshipped PR references removed from process-pain.html. Remaining: walk
  `getting-started.md` from a clean checkout, reconcile `jurisdictions.md`
  against `examples/`, open per-drift PRs.
- No other tracked issues open as of this snapshot

## Round 8 / 9 — Remaining Planned Work

The deep-research-agent's 5-round plan (in `memory/project_round5to9_plan.md`) is partially shipped — regwatch (8.3) shipped as Round 7 PR #74, FINTRAC audit-pack (9.1) as Round 7 PR #78, UK APP-fraud spec (8.1) as Round 7 PR #76. Remaining items, with the original engineer-day estimates:

| Round | Item | Estimate | Status |
|---|---|---|---|
| 8.2 | RTP/FedNow push-fraud detector pack | 3d | not started |
| 8.4 | Fraud-AML unified case linkage | 3d | partial (cyber_enabled_fraud spec exists) |
| 8.5 | Beneficial Ownership (BOI) workflow page #26 | 3d | not started |
| 9.2 | Open Compliance API draft (`api/openapi-compliance.yaml`) | 3d | not started |
| 9.3 | Guided demo CLI (`aml demo`) | 3d | not started |
| 9.4 | Synthetic data quality upgrade for new specs | 3d | partial |
| 9.5 | Cross-border information-sharing sandbox (FATF R.18) | 5d | not started |

~20 engineer-days of focused work remaining — each item warrants its own scope confirmation before implementation.

---

## Documentation Index

Every doc has a single-line "use when" hook in [`README.md`](../README.md). The full set:

- `README.md` — hub-style entry point with documentation map
- `docs/getting-started.md` — 15-min onboarding path
- `docs/architecture.md` — reference design
- `docs/dashboard-tour.md` — all 24 pages organized by workflow
- `docs/jurisdictions.md` — US / CA / EU / UK / crypto / cyber-fraud specs
- `docs/personas.md` — role-based workflows
- `docs/spec-reference.md` — field-by-field `aml.yaml` guide
- `docs/api-reference.md` — REST endpoint catalogue
- `docs/audit-evidence.md` — evidence bundle specification
- `docs/metrics-framework.md` — metric types, RAG, audience routing
- `docs/regulator-mapping.md` — coverage matrix
- `docs/deployment.md` — Docker + Helm
- `docs/case-studies/` — TD 2024 enforcement walkthrough
- `docs/progress.md` — this file
